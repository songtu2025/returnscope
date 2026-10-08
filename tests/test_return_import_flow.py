from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_classification_result_pool import _seed_result_context

import web_backend.datasets.preview as dataset_preview_module
from return_semantics.data import (
    PRODUCT_COLUMNS,
    RETURN_COLUMNS,
    RETURN_STORE_COLUMN,
    SOURCE_ORIGIN_COLUMN,
    _prepare_return_records,
)
from web_backend.dataset_service import DatasetService
from web_backend.routers.datasets import create_dataset_router


def _return_row(order_id: str, comment: str) -> dict[str, str]:
    values = {column: "" for column in RETURN_COLUMNS}
    values.update(
        {
            "return-date": "2026-08-20",
            "order-id": order_id,
            "sku": "SKU-1",
            "product-name": "测试商品",
            "quantity": "1",
            "reason": "OTHER",
            "customer-comments": comment,
            RETURN_STORE_COLUMN: "SENWAYZON:US",
        }
    )
    return values


def _write_returns(path: Path, rows: list[dict[str, str]]) -> None:
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")


def _write_returns_xlsx(path: Path, rows: list[dict[str, str]]) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame([{"说明": "退货导入文件"}]).to_excel(
            writer,
            sheet_name="说明",
            index=False,
        )
        pd.DataFrame(rows).to_excel(
            writer,
            sheet_name="退货明细",
            index=False,
        )


def test_return_loader_preserves_optional_source_origin_id(tmp_path: Path) -> None:
    source = tmp_path / "returns.csv"
    row = _return_row("ORDER-1", "偏小")
    row[SOURCE_ORIGIN_COLUMN] = "12345"
    _write_returns(source, [row])

    records = _prepare_return_records(source)

    assert records.loc[0, SOURCE_ORIGIN_COLUMN] == "12345"


def _create_task_input(
    service: DatasetService,
    source: Path,
) -> dict[str, object]:
    return service.create(
        name="测试退货数据",
        kind="returns",
        description="",
        source_path=source,
        original_name=source.name,
        content_type="text/csv",
        change_note="首次导入",
        actor_id="user-1",
    )


def _database_counts(database) -> dict[str, int]:
    tables = ("datasets", "dataset_versions", "dataset_imports", "audit_logs")
    with database.connect() as connection:
        return {
            table: int(
                connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            )
            for table in tables
        }


def _fail_import_audit(database) -> None:
    with database.transaction(immediate=True) as connection:
        connection.execute(
            """
            CREATE TRIGGER fail_import_return_audit
            BEFORE INSERT ON audit_logs
            WHEN NEW.action = 'import_returns'
            BEGIN
                SELECT RAISE(ABORT, 'injected import audit failure');
            END
            """
        )


def _assert_stored_files_exist(database) -> None:
    with database.connect() as connection:
        version_paths = connection.execute(
            "SELECT file_path FROM dataset_versions"
        ).fetchall()
        import_paths = connection.execute(
            "SELECT raw_file_path FROM dataset_imports"
        ).fetchall()
    assert all(Path(str(row[0])).is_file() for row in version_paths)
    assert all(Path(str(row[0])).is_file() for row in import_paths)


def _synchronize_first_import_commits(service, monkeypatch) -> None:
    original_commit = service._commit_return_import
    first_attempt_barrier = threading.Barrier(2)
    synchronized_threads: set[int] = set()
    synchronized_threads_lock = threading.Lock()

    def synchronized_commit(**kwargs):
        thread_id = threading.get_ident()
        with synchronized_threads_lock:
            should_wait = thread_id not in synchronized_threads
            synchronized_threads.add(thread_id)
        if should_wait:
            first_attempt_barrier.wait(timeout=5)
        return original_commit(**kwargs)

    monkeypatch.setattr(service, "_commit_return_import", synchronized_commit)


def test_inspect_route_removes_temporary_file_after_unexpected_error(
    tmp_path: Path,
) -> None:
    class FailingDatasetService:
        def inspect_return_import(self, *_args, **_kwargs):
            raise RuntimeError("解析器异常")

    app = FastAPI()
    app.include_router(
        create_dataset_router(
            dataset_service=FailingDatasetService(),
            settings=SimpleNamespace(data_dir=tmp_path),
            current_user=lambda: {"id": "user-1"},
        )
    )

    with TestClient(app) as client, pytest.raises(RuntimeError, match="解析器异常"):
        client.post(
            "/api/return-imports/inspect",
            files={"file": ("returns.csv", b"a,b\n1,2", "text/csv")},
        )

    temporary_dir = tmp_path / "tmp" / "dataset-imports"
    assert not temporary_dir.exists() or not any(temporary_dir.iterdir())


def _write_products(path: Path) -> None:
    rows = [
        {
            PRODUCT_COLUMNS[0]: "MSKU-1",
            PRODUCT_COLUMNS[1]: "SENWAYZON:US",
            PRODUCT_COLUMNS[2]: "LISTING-1",
            "品类A": "眼镜",
            "品类B": "太阳镜",
            "产品名称": "测试商品",
            "SKU": "SKU-1",
        },
        {
            PRODUCT_COLUMNS[0]: "MSKU-2",
            PRODUCT_COLUMNS[1]: "SENWAYZON:US",
            PRODUCT_COLUMNS[2]: "LISTING-2",
            "品类A": "手套",
            "品类B": "",
            "产品名称": "测试手套",
            "SKU": "SKU-2",
        },
    ]
    pd.DataFrame(rows).to_excel(path, sheet_name="产品信息汇总表", index=False)


def test_product_preview_uses_rebuildable_derived_csv(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    source = tmp_path / "products.xlsx"
    _write_products(source)

    created = service.create(
        name="商品信息",
        kind="products",
        description="",
        source_path=source,
        original_name=source.name,
        content_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        change_note="首次导入",
        actor_id="user-1",
    )
    digest = created["versions"][0]["sha256"]
    preview_path = tmp_path / "cache" / "dataset-previews" / f"{digest}.csv"

    assert preview_path.exists()
    assert service.preview_rows(str(created["id"]))["facets"]["categories"] == [
        "手套",
        "眼镜 > 太阳镜",
    ]
    preview_path.unlink()
    rebuilt = service.preview_rows(str(created["id"]), query="MSKU-1")
    assert rebuilt["total"] == 1
    assert preview_path.exists()


def test_staged_return_import_enforces_owner_retry_and_single_use(
    tmp_path: Path,
) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    source = tmp_path / "staged.csv"
    _write_returns(source, [_return_row("O-1", "偏小")])
    inspection = service.inspect_return_import(
        source,
        source.name,
        actor_id="user-1",
    )
    inspection_id = str(inspection["inspection_id"])

    try:
        service.import_staged_returns(
            inspection_id=inspection_id,
            actor_id="user-2",
            mode="analyze_only",
        )
    except ValueError as exc:
        assert "无权" in str(exc)
    else:
        raise AssertionError("必须拒绝其他用户的检查记录")

    try:
        service.import_staged_returns(
            inspection_id=inspection_id,
            actor_id="user-1",
            mode="invalid",
        )
    except ValueError as exc:
        assert "仅支持" in str(exc)
    else:
        raise AssertionError("无效导入应失败")
    assert source.exists()

    result = service.import_staged_returns(
        inspection_id=inspection_id,
        actor_id="user-1",
        mode="analyze_only",
    )
    assert result["summary"]["imported_row_count"] == 1
    assert not source.exists()
    try:
        service.import_staged_returns(
            inspection_id=inspection_id,
            actor_id="user-1",
            mode="analyze_only",
        )
    except ValueError as exc:
        assert "过期" in str(exc)
    else:
        raise AssertionError("已导入的检查记录不能重复使用")


def test_staged_cleanup_keeps_expired_import_while_processing(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    source = tmp_path / "processing.csv"
    _write_returns(source, [_return_row("O-1", "偏小")])
    inspection = service.inspect_return_import(
        source,
        source.name,
        actor_id="user-1",
    )
    inspection_id = str(inspection["inspection_id"])
    with context.database.transaction(immediate=True) as connection:
        connection.execute(
            """
            UPDATE dataset_import_staging
            SET expires_at = '2000-01-01T00:00:00+00:00',
                consumed_at = '2026-09-07T00:00:00+00:00'
            WHERE id = ?
            """,
            (inspection_id,),
        )

    service._cleanup_staged_imports()

    with context.database.connect() as connection:
        staged = connection.execute(
            "SELECT id FROM dataset_import_staging WHERE id = ?",
            (inspection_id,),
        ).fetchone()
    assert staged is not None
    assert source.exists()


@pytest.mark.parametrize("failure", ["staging_row", "source_file"])
def test_successful_staged_import_logs_cleanup_failure_without_payload(
    tmp_path: Path, monkeypatch, caplog, failure: str
) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    source = tmp_path / "SYNTHETIC-cleanup.csv"
    _write_returns(source, [_return_row("SYNTHETIC-ORDER", "SYNTHETIC-COMMENT")])
    inspection = service.inspect_return_import(source, source.name, actor_id="user-1")
    if failure == "staging_row":
        with context.database.transaction() as connection:
            connection.execute(
                """
                CREATE TRIGGER fail_staging_cleanup
                BEFORE DELETE ON dataset_import_staging
                BEGIN
                    SELECT RAISE(ABORT, 'SYNTHETIC-CONFIDENTIAL');
                END
                """
            )
    else:
        original_unlink = Path.unlink

        def fail_source_unlink(path, *args, **kwargs):
            if path == source:
                raise OSError("SYNTHETIC-CONFIDENTIAL")
            return original_unlink(path, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", fail_source_unlink)
    result = service.import_staged_returns(
        inspection_id=str(inspection["inspection_id"]),
        actor_id="user-1",
        mode="analyze_only",
    )
    assert result["summary"]["imported_row_count"] == 1
    assert service.version_file(str(result["dataset"]["id"])) is not None
    records = [
        item
        for item in caplog.records
        if item.name == "web_backend.dataset_return_import"
    ]
    assert len(records) == 1
    assert "error_type=" in records[0].getMessage()
    assert records[0].exc_info is None
    assert "SYNTHETIC-CONFIDENTIAL" not in caplog.text
    assert str(source) not in caplog.text


def test_import_source_directory_cleanup_logs_only_error_type(
    tmp_path: Path, caplog
) -> None:
    directory = tmp_path / "SYNTHETIC-import"
    directory.mkdir()
    source = directory / "source.csv"
    source.write_text("SYNTHETIC-DATA", encoding="utf-8")
    extra = directory / "SYNTHETIC-CONFIDENTIAL"
    extra.write_text("SYNTHETIC-EXTRA", encoding="utf-8")
    DatasetService._cleanup_import_source(source)
    assert not source.exists()
    assert extra.exists()
    records = [
        item
        for item in caplog.records
        if item.name == "web_backend.dataset_return_versions"
    ]
    assert len(records) == 1
    assert records[0].getMessage() == "导入归档目录清理失败: error_type=OSError"
    assert records[0].exc_info is None
    assert "SYNTHETIC-CONFIDENTIAL" not in caplog.text
    assert str(directory) not in caplog.text


def test_import_source_file_cleanup_keeps_unlink_failure(
    monkeypatch, tmp_path: Path, caplog
) -> None:
    source = tmp_path / "SYNTHETIC-source.csv"

    def fail_unlink(*_args, **_kwargs):
        raise OSError("SYNTHETIC-UNLINK")

    monkeypatch.setattr(Path, "unlink", fail_unlink)
    with pytest.raises(OSError, match="SYNTHETIC-UNLINK"):
        DatasetService._cleanup_import_source(source)
    assert not caplog.records


def test_return_import_recognizes_identity_and_separates_task_input(
    tmp_path: Path,
) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    source = tmp_path / "senwayzon-us.csv"
    _write_returns(
        source,
        [_return_row("O-1", "偏小"), _return_row("O-2", "不够保暖")],
    )

    inspection = service.inspect_return_import(source, source.name)
    assert inspection["source_key"] == "SENWAYZON:US"
    assert inspection["suggested_name"] == "SENWAYZON US 用户反馈数据"
    assert "matches" not in inspection

    one_off = service.import_returns(
        source_path=source,
        original_name=source.name,
        content_type="text/csv",
        mode="analyze_only",
        actor_id="user-1",
    )
    assert one_off["dataset"]["usage_scope"] == "task_input"
    assert one_off["dataset"]["source_name"] == "SENWAYZON US 用户反馈数据"
    assert not service.list("returns", "managed")
    assert one_off["dataset"]["id"] not in {
        item["id"] for item in service.list("returns", "managed")
    }

    repeated = service.inspect_return_import(source, source.name)
    assert repeated["duplicate"]["version_id"] == one_off["version_id"]


def test_return_xlsx_import_uses_matching_sheet(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    source = tmp_path / "senwayzon-us.xlsx"
    _write_returns_xlsx(source, [_return_row("O-1", "偏小")])

    inspection = service.inspect_return_import(source, source.name)
    result = service.import_returns(
        source_path=source,
        original_name=source.name,
        content_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        mode="analyze_only",
        actor_id="user-1",
        _inspection=inspection,
    )
    preview = service.preview_rows(str(result["dataset"]["id"]))

    assert inspection["row_count"] == 1
    assert inspection["stores"] == ["SENWAYZON:US"]
    assert preview["records"][0]["order-id"] == "O-1"
    assert service.version_file(str(result["dataset"]["id"]))["original_name"] == (
        source.name
    )


def test_return_import_does_not_fill_missing_store(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    source = tmp_path / "missing-store.csv"
    row = _return_row("O-1", "偏小")
    row[RETURN_STORE_COLUMN] = ""
    _write_returns(source, [row])

    inspection = service.inspect_return_import(source, source.name)

    assert inspection["stores"] == []
    assert inspection["source_key"] == ""
    assert inspection["quality"]["missing_store_rows"] == 1
    before = service.list("returns")
    with pytest.raises(ValueError, match="缺少店铺/站点"):
        service.import_returns(
            source_path=source,
            original_name=source.name,
            content_type="text/csv",
            mode="analyze_only",
            actor_id="user-1",
        )
    assert service.list("returns") == before


def test_return_preview_reads_only_requested_prefix(
    tmp_path: Path,
    monkeypatch,
) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    source = tmp_path / "bounded.csv"
    _write_returns(
        source,
        [_return_row(f"O-{index}", "偏小") for index in range(20)],
    )
    created = _create_task_input(service, source)
    original = dataset_preview_module.read_return_file
    observed: list[int | None] = []

    def tracking_read(path, usecols=None, nrows=None):
        observed.append(nrows)
        return original(path, usecols=usecols, nrows=nrows)

    monkeypatch.setattr(dataset_preview_module, "read_return_file", tracking_read)
    preview = service.preview_rows(str(created["id"]), offset=5, limit=2)

    assert observed == [7]
    assert preview["source_total"] == 20
    assert [record["_row_index"] for record in preview["records"]] == [5, 6]


@pytest.mark.parametrize("mode", ["analyze_only"])
def test_new_return_import_rolls_back_when_audit_insert_fails(
    tmp_path: Path,
    mode: str,
) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    source = tmp_path / f"{mode}.csv"
    _write_returns(source, [_return_row("O-1", "偏小")])
    before = _database_counts(context.database)
    _fail_import_audit(context.database)

    with pytest.raises(sqlite3.IntegrityError, match="injected import audit failure"):
        service.import_returns(
            source_path=source,
            original_name=source.name,
            content_type="text/csv",
            mode=mode,
            actor_id="user-1",
        )

    assert _database_counts(context.database) == before
    assert not any((tmp_path / "imports").rglob("source.csv"))
    _assert_stored_files_exist(context.database)


def test_return_import_preserves_audit_actions_and_file_references(
    tmp_path: Path,
) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    initial = tmp_path / "initial.csv"
    appended = tmp_path / "appended.csv"
    replaced = tmp_path / "replaced.csv"
    _write_returns(initial, [_return_row("O-1", "偏小")])
    _write_returns(appended, [_return_row("O-2", "不够保暖")])
    _write_returns(replaced, [_return_row("O-3", "抓握不好")])

    created = service.import_returns(
        source_path=initial,
        original_name=initial.name,
        content_type="text/csv",
        mode="analyze_only",
        actor_id="user-1",
    )
    dataset_id = str(created["dataset"]["id"])
    with context.database.connect() as connection:
        audit_rows = connection.execute(
            """
            SELECT action, after_json FROM audit_logs
            WHERE entity_type = 'dataset' AND entity_id = ?
            ORDER BY rowid
            """,
            (dataset_id,),
        ).fetchall()
    assert [row["action"] for row in audit_rows] == [
        "add_version",
        "create",
        "import_returns",
    ]
    import_audits = [
        json.loads(row["after_json"])
        for row in audit_rows
        if row["action"] == "import_returns"
    ]
    assert [item["mode"] for item in import_audits] == [
        "analyze_only",
    ]
    assert all(
        set(item)
        == {
            "import_id",
            "mode",
            "version_id",
            "raw_sha256",
            "imported_row_count",
            "skipped_row_count",
        }
        for item in import_audits
    )
    _assert_stored_files_exist(context.database)


@pytest.mark.parametrize("mode", ["analyze_only"])
def test_staged_retry_after_response_failure_is_idempotent(
    tmp_path: Path,
    monkeypatch,
    mode: str,
) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    source = tmp_path / f"staged-{mode}.csv"
    _write_returns(source, [_return_row("O-2", "不够保暖")])
    inspection = service.inspect_return_import(
        source,
        source.name,
        actor_id="user-1",
    )
    inspection_id = str(inspection["inspection_id"])
    raw_sha256 = str(inspection["raw_sha256"])
    original_get = service.get
    failed = False

    def fail_first_get_after_commit(*args, **kwargs):
        nonlocal failed
        with context.database.connect() as connection:
            committed = connection.execute(
                "SELECT 1 FROM dataset_imports WHERE raw_sha256 = ? LIMIT 1",
                (raw_sha256,),
            ).fetchone()
        if committed is not None and not failed:
            failed = True
            raise RuntimeError("injected response failure")
        return original_get(*args, **kwargs)

    monkeypatch.setattr(service, "get", fail_first_get_after_commit)
    with pytest.raises(RuntimeError, match="injected response failure"):
        service.import_staged_returns(
            inspection_id=inspection_id,
            actor_id="user-1",
            mode=mode,
        )

    with context.database.connect() as connection:
        committed_import = dict(
            connection.execute(
                """
                SELECT id, dataset_id, resulting_version_id, raw_file_path,
                       raw_sha256
                FROM dataset_imports WHERE raw_sha256 = ?
                """,
                (raw_sha256,),
            ).fetchone()
        )
        staging = connection.execute(
            "SELECT consumed_at FROM dataset_import_staging WHERE id = ?",
            (inspection_id,),
        ).fetchone()
    assert staging["consumed_at"] is None
    assert Path(committed_import["raw_file_path"]).is_file()
    counts_after_commit = _database_counts(context.database)

    retried = service.import_staged_returns(
        inspection_id=inspection_id,
        actor_id="user-1",
        mode=mode,
    )

    assert retried["duplicate"] is True
    assert retried["version_id"] == committed_import["resulting_version_id"]
    assert retried["dataset"]["id"] == committed_import["dataset_id"]
    assert _database_counts(context.database) == counts_after_commit
    with context.database.connect() as connection:
        persisted_imports = connection.execute(
            """
            SELECT id, raw_file_path FROM dataset_imports
            WHERE raw_sha256 = ?
            """,
            (raw_sha256,),
        ).fetchall()
        assert (
            connection.execute(
                "SELECT 1 FROM dataset_import_staging WHERE id = ?",
                (inspection_id,),
            ).fetchone()
            is None
        )
    assert len(persisted_imports) == 1
    assert persisted_imports[0]["id"] == committed_import["id"]
    assert persisted_imports[0]["raw_file_path"] == committed_import["raw_file_path"]
    assert Path(str(persisted_imports[0]["raw_file_path"])).is_file()


def test_authoritative_duplicate_check_reuses_legacy_version(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    source = tmp_path / "legacy-duplicate.csv"
    _write_returns(source, [_return_row("O-1", "偏小")])
    stale_inspection = service.inspect_return_import(source, source.name)
    created = _create_task_input(service, source)
    before = _database_counts(context.database)

    result = service.import_returns(
        source_path=source,
        original_name=source.name,
        content_type="text/csv",
        mode="analyze_only",
        actor_id="user-1",
        _inspection=stale_inspection,
    )

    assert result["duplicate"] is True
    assert result["version_id"] == created["versions"][0]["id"]
    assert _database_counts(context.database) == before


def test_return_import_copy_failure_cleans_unique_source_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    source = tmp_path / "copy-failure.csv"
    _write_returns(source, [_return_row("O-1", "偏小")])
    before = _database_counts(context.database)
    original_copy = shutil.copy2

    def failing_copy(source_path, destination, *args, **kwargs):
        destination_path = Path(destination)
        if "imports" in destination_path.parts:
            destination_path.write_bytes(b"partial")
            raise OSError("injected copy failure")
        return original_copy(source_path, destination, *args, **kwargs)

    monkeypatch.setattr(shutil, "copy2", failing_copy)
    with pytest.raises(OSError, match="injected copy failure"):
        service.import_returns(
            source_path=source,
            original_name=source.name,
            content_type="text/csv",
            mode="analyze_only",
            actor_id="user-1",
        )

    assert _database_counts(context.database) == before
    assert not any((tmp_path / "imports").rglob("*"))


def test_blob_copy_failure_removes_temporary_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    source = tmp_path / "blob-failure.csv"
    _write_returns(source, [_return_row("O-1", "偏小")])
    digest = hashlib.sha256(source.read_bytes()).hexdigest()

    def failing_copy(_source, destination, *_args, **_kwargs):
        Path(destination).write_bytes(b"partial")
        raise OSError("injected blob copy failure")

    monkeypatch.setattr(shutil, "copy2", failing_copy)
    with pytest.raises(OSError, match="injected blob copy failure"):
        service._ensure_blob(source, digest)

    blob_dir = tmp_path / "uploads" / "blobs"
    assert not (blob_dir / f"{digest}.csv").exists()
    assert not list(blob_dir.glob(f"{digest}.csv.blob_*"))


def test_concurrent_blob_writes_publish_complete_content(
    tmp_path: Path,
    monkeypatch,
) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    source = tmp_path / "shared-blob.csv"
    _write_returns(
        source,
        [_return_row(f"O-{index}", f"问题-{index}") for index in range(100)],
    )
    content = source.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    destination = service._blob_path(digest, source.suffix)
    original_copy = shutil.copy2
    both_copied = threading.Barrier(3)
    publish_gate = threading.Event()

    def synchronized_copy(source_path, temporary, *args, **kwargs):
        result = original_copy(source_path, temporary, *args, **kwargs)
        both_copied.wait(timeout=10)
        if not publish_gate.wait(timeout=10):
            raise TimeoutError("等待发布 Blob 超时")
        return result

    monkeypatch.setattr(shutil, "copy2", synchronized_copy)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(service._ensure_blob, source, digest) for _ in range(2)
        ]
        both_copied.wait(timeout=10)
        try:
            assert not destination.exists()
            temporary_paths = list(
                destination.parent.glob(f"{destination.name}.blob_*")
            )
            assert len(temporary_paths) == 2
            assert all(path.read_bytes() == content for path in temporary_paths)
        finally:
            publish_gate.set()
        paths = [future.result(timeout=10) for future in futures]

    assert paths[0] == paths[1]
    assert paths[0].read_bytes() == content
    assert hashlib.sha256(paths[0].read_bytes()).hexdigest() == digest
    assert not list(paths[0].parent.glob(f"{paths[0].name}.blob_*"))


@pytest.mark.parametrize("mode", ["create", "append", "replace"])
def test_retired_import_modes_cannot_write(tmp_path: Path, mode: str) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    before = _database_counts(context.database)
    with pytest.raises(ValueError, match="长期数据源导入已下线"):
        service.import_returns(
            source_path=tmp_path / "unused.csv",
            original_name="unused.csv",
            content_type="text/csv",
            mode=mode,
            actor_id="user-1",
        )
    assert _database_counts(context.database) == before


def test_same_file_never_reuses_managed_source(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    source = tmp_path / "managed.csv"
    _write_returns(source, [_return_row("O-1", "合成反馈")])
    old = _create_task_input(service, source)
    with context.database.transaction() as connection:
        connection.execute(
            "UPDATE datasets SET usage_scope = 'managed' WHERE id = ?", (old["id"],)
        )
    inspection = service.inspect_return_import(source, source.name)
    assert inspection["duplicate"] is None
    result = service.import_returns(
        source_path=source,
        original_name=source.name,
        content_type="text/csv",
        mode="analyze_only",
        actor_id="user-1",
        _inspection=inspection,
    )
    assert result["dataset"]["id"] != old["id"]
    assert result["dataset"]["usage_scope"] == "task_input"
    assert result["duplicate"] is False


def test_transaction_rechecks_lifecycle_after_inspection(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    source = tmp_path / "changed-scope.csv"
    _write_returns(source, [_return_row("O-1", "合成反馈")])
    old = _create_task_input(service, source)
    stale = service.inspect_return_import(source, source.name)
    assert stale["duplicate"] is not None
    with context.database.transaction() as connection:
        connection.execute(
            "UPDATE datasets SET usage_scope = 'managed' WHERE id = ?", (old["id"],)
        )
    result = service.import_returns(
        source_path=source,
        original_name=source.name,
        content_type="text/csv",
        mode="analyze_only",
        actor_id="user-1",
        _inspection=stale,
    )
    assert result["dataset"]["id"] != old["id"]


def test_concurrent_task_uploads_deduplicate_inside_transaction(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    source = tmp_path / "parallel.csv"
    _write_returns(source, [_return_row("O-1", "合成反馈")])
    inspection = service.inspect_return_import(source, source.name)

    def upload():
        return service.import_returns(
            source_path=source,
            original_name=source.name,
            content_type="text/csv",
            mode="analyze_only",
            actor_id="user-1",
            _inspection=inspection,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: upload(), range(2)))
    assert len({result["version_id"] for result in results}) == 1
    assert sum(result["duplicate"] for result in results) == 1
