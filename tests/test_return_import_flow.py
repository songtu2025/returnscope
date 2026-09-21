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

import web_backend.dataset_service as dataset_service_module
from return_semantics.data import (
    PRODUCT_COLUMNS,
    RETURN_COLUMNS,
    RETURN_STORE_COLUMN,
    SOURCE_ORIGIN_COLUMN,
    _prepare_return_records,
    read_return_file,
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


def _create_managed_returns(
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
        assert "未知" in str(exc)
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
    assert inspection["matches"] == []

    one_off = service.import_returns(
        source_path=source,
        original_name=source.name,
        content_type="text/csv",
        mode="analyze_only",
        actor_id="user-1",
    )
    assert one_off["dataset"]["usage_scope"] == "task_input"
    assert one_off["dataset"]["source_name"] == "SENWAYZON US 用户反馈数据"
    assert service.list("returns", "managed")
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


def test_return_xlsx_append_creates_csv_snapshot(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    initial = tmp_path / "initial.csv"
    incoming = tmp_path / "incoming.xlsx"
    _write_returns(initial, [_return_row("O-1", "偏小")])
    _write_returns_xlsx(incoming, [_return_row("O-2", "不够保暖")])
    dataset_id = str(_create_managed_returns(service, initial)["id"])

    result = service.import_returns(
        source_path=incoming,
        original_name=incoming.name,
        content_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        mode="append",
        dataset_id=dataset_id,
        actor_id="user-1",
    )
    version = service.version_file(dataset_id)
    preview = service.preview_rows(dataset_id)

    assert result["summary"] == {"imported_row_count": 1, "skipped_row_count": 0}
    assert version["original_name"] == "incoming.csv"
    assert version["content_type"] == "text/csv"
    assert Path(str(version["file_path"])).suffix == ".csv"
    assert [record["order-id"] for record in preview["records"]] == ["O-1", "O-2"]


def test_return_xlsx_default_store_preserves_workbook(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    source = tmp_path / "missing-store.xlsx"
    row = _return_row("O-1", "偏小")
    row.pop(RETURN_STORE_COLUMN)
    _write_returns_xlsx(source, [row])

    created = service.create(
        name="测试退货数据",
        kind="returns",
        description="",
        source_path=source,
        original_name=source.name,
        content_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        change_note="首次导入",
        actor_id="user-1",
        default_store="SENWAYZON:US",
    )
    version = service.version_file(str(created["id"]))
    frame = read_return_file(Path(str(version["file_path"])))

    assert frame.iloc[0][RETURN_STORE_COLUMN] == "SENWAYZON:US"
    assert pd.ExcelFile(Path(str(version["file_path"]))).sheet_names == [
        "说明",
        "退货明细",
    ]


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
    created = _create_managed_returns(service, source)
    original = dataset_service_module.read_return_file
    observed: list[int | None] = []

    def tracking_read(path, usecols=None, nrows=None):
        observed.append(nrows)
        return original(path, usecols=usecols, nrows=nrows)

    monkeypatch.setattr(dataset_service_module, "read_return_file", tracking_read)
    preview = service.preview_rows(str(created["id"]), offset=5, limit=2)

    assert observed == [7]
    assert preview["source_total"] == 20
    assert [record["_row_index"] for record in preview["records"]] == [5, 6]


def test_return_import_appends_without_repeating_rows(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    first = tmp_path / "senwayzon-first.csv"
    second = tmp_path / "senwayzon-second.csv"
    first_rows = [_return_row("O-1", "偏小"), _return_row("O-2", "不够保暖")]
    _write_returns(first, first_rows)
    _write_returns(second, [first_rows[1], _return_row("O-3", "抓握不好")])

    created = service.import_returns(
        source_path=first,
        original_name=first.name,
        content_type="text/csv",
        mode="create",
        actor_id="user-1",
    )
    dataset_id = created["dataset"]["id"]
    inspection = service.inspect_return_import(second, second.name)
    assert [item["dataset_id"] for item in inspection["matches"]] == [dataset_id]

    appended = service.import_returns(
        source_path=second,
        original_name=second.name,
        content_type="text/csv",
        mode="append",
        dataset_id=dataset_id,
        actor_id="user-1",
    )
    assert appended["summary"] == {
        "imported_row_count": 1,
        "skipped_row_count": 1,
    }
    assert appended["dataset"]["row_count"] == 3
    assert appended["dataset"]["current_version"] == 2
    assert [item["mode"] for item in appended["dataset"]["imports"]] == [
        "append",
        "create",
    ]

    first_snapshot = service.preview_rows(dataset_id, limit=10, version=1)
    current_snapshot = service.preview_rows(dataset_id, limit=10)
    assert first_snapshot["version"] == 1
    assert first_snapshot["source_total"] == 2
    assert current_snapshot["version"] == 2
    assert current_snapshot["source_total"] == 3


@pytest.mark.parametrize("mode", ["create", "analyze_only"])
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


@pytest.mark.parametrize("mode", ["append", "replace"])
def test_existing_return_import_rolls_back_when_audit_insert_fails(
    tmp_path: Path,
    mode: str,
) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    initial = tmp_path / "initial.csv"
    incoming = tmp_path / f"{mode}.csv"
    _write_returns(initial, [_return_row("O-1", "偏小")])
    _write_returns(incoming, [_return_row("O-2", "不够保暖")])
    created = _create_managed_returns(service, initial)
    dataset_id = str(created["id"])
    before = _database_counts(context.database)
    before_version = int(created["current_version"])
    _fail_import_audit(context.database)

    with pytest.raises(sqlite3.IntegrityError, match="injected import audit failure"):
        service.import_returns(
            source_path=incoming,
            original_name=incoming.name,
            content_type="text/csv",
            mode=mode,
            dataset_id=dataset_id,
            actor_id="user-1",
        )

    assert _database_counts(context.database) == before
    assert service.get(dataset_id)["current_version"] == before_version
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
        mode="create",
        actor_id="user-1",
    )
    dataset_id = str(created["dataset"]["id"])
    for mode, source in (("append", appended), ("replace", replaced)):
        service.import_returns(
            source_path=source,
            original_name=source.name,
            content_type="text/csv",
            mode=mode,
            dataset_id=dataset_id,
            actor_id="user-1",
        )

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
        "add_version",
        "import_returns",
        "add_version",
        "import_returns",
    ]
    import_audits = [
        json.loads(row["after_json"])
        for row in audit_rows
        if row["action"] == "import_returns"
    ]
    assert [item["mode"] for item in import_audits] == [
        "create",
        "append",
        "replace",
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


def test_concurrent_return_appends_merge_from_latest_version(
    tmp_path: Path,
    monkeypatch,
) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    initial = tmp_path / "initial.csv"
    first_append = tmp_path / "first-append.csv"
    second_append = tmp_path / "second-append.csv"
    _write_returns(initial, [_return_row("O-1", "偏小")])
    _write_returns(first_append, [_return_row("O-2", "不够保暖")])
    _write_returns(second_append, [_return_row("O-3", "抓握不好")])
    created = _create_managed_returns(service, initial)
    dataset_id = str(created["id"])

    _synchronize_first_import_commits(service, monkeypatch)

    def append(source_path: Path) -> dict[str, object]:
        return service.import_returns(
            source_path=source_path,
            original_name=source_path.name,
            content_type="text/csv",
            mode="append",
            dataset_id=dataset_id,
            actor_id="user-1",
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(append, first_append),
            executor.submit(append, second_append),
        ]
        results = [future.result(timeout=10) for future in futures]

    current = service.preview_rows(dataset_id, limit=10)
    assert current["version"] == 3
    assert current["source_total"] == 3
    assert {record["order-id"] for record in current["records"]} == {
        "O-1",
        "O-2",
        "O-3",
    }
    assert [result["summary"] for result in results] == [
        {"imported_row_count": 1, "skipped_row_count": 0},
        {"imported_row_count": 1, "skipped_row_count": 0},
    ]
    imported = service.get(dataset_id)["imports"]
    append_version_ids = {
        item["resulting_version_id"] for item in imported if item["mode"] == "append"
    }
    assert len(append_version_ids) == 2


@pytest.mark.parametrize("mode", ["create", "append"])
def test_staged_retry_after_response_failure_is_idempotent(
    tmp_path: Path,
    monkeypatch,
    mode: str,
) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    dataset_id = ""
    if mode == "append":
        initial = tmp_path / "initial.csv"
        _write_returns(initial, [_return_row("O-1", "偏小")])
        dataset_id = str(_create_managed_returns(service, initial)["id"])
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
            dataset_id=dataset_id,
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
        dataset_id=dataset_id,
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


def test_concurrent_identical_appends_reuse_committed_import(
    tmp_path: Path,
    monkeypatch,
) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    initial = tmp_path / "initial.csv"
    incoming = tmp_path / "same-append.csv"
    _write_returns(initial, [_return_row("O-1", "偏小")])
    _write_returns(incoming, [_return_row("O-2", "不够保暖")])
    dataset_id = str(_create_managed_returns(service, initial)["id"])
    inspection = service.inspect_return_import(incoming, incoming.name)
    before = _database_counts(context.database)
    _synchronize_first_import_commits(service, monkeypatch)

    def append() -> dict[str, object]:
        return service.import_returns(
            source_path=incoming,
            original_name=incoming.name,
            content_type="text/csv",
            mode="append",
            dataset_id=dataset_id,
            actor_id="user-1",
            _inspection=inspection,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(append), executor.submit(append)]
        results = [future.result(timeout=10) for future in futures]

    with context.database.connect() as connection:
        imports = connection.execute(
            """
            SELECT resulting_version_id, raw_sha256, raw_file_path
            FROM dataset_imports WHERE dataset_id = ? AND mode = 'append'
            """,
            (dataset_id,),
        ).fetchall()
        audit_actions = connection.execute(
            """
            SELECT action FROM audit_logs
            WHERE entity_type = 'dataset' AND entity_id = ? ORDER BY rowid
            """,
            (dataset_id,),
        ).fetchall()
    assert len(imports) == 1
    assert imports[0]["raw_sha256"] == inspection["raw_sha256"]
    assert Path(str(imports[0]["raw_file_path"])).is_file()
    assert {result["version_id"] for result in results} == {
        imports[0]["resulting_version_id"]
    }
    assert sorted(result["duplicate"] for result in results) == [False, True]
    assert _database_counts(context.database) == {
        **before,
        "dataset_versions": before["dataset_versions"] + 1,
        "dataset_imports": before["dataset_imports"] + 1,
        "audit_logs": before["audit_logs"] + 2,
    }
    assert [row["action"] for row in audit_actions][-2:] == [
        "add_version",
        "import_returns",
    ]


def test_authoritative_duplicate_check_reuses_legacy_version(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    source = tmp_path / "legacy-duplicate.csv"
    _write_returns(source, [_return_row("O-1", "偏小")])
    stale_inspection = service.inspect_return_import(source, source.name)
    created = _create_managed_returns(service, source)
    dataset_id = str(created["id"])
    before = _database_counts(context.database)

    result = service.import_returns(
        source_path=source,
        original_name=source.name,
        content_type="text/csv",
        mode="append",
        dataset_id=dataset_id,
        actor_id="user-1",
        _inspection=stale_inspection,
    )

    assert result["duplicate"] is True
    assert result["version_id"] == created["versions"][0]["id"]
    assert _database_counts(context.database) == before


def test_concurrent_append_rechecks_source_key_inside_transaction(
    tmp_path: Path,
    monkeypatch,
) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    initial = tmp_path / "initial.csv"
    first = tmp_path / "first-store.csv"
    second = tmp_path / "second-store.csv"
    initial_row = _return_row("O-1", "偏小")
    initial_row[RETURN_STORE_COLUMN] = ""
    second_row = _return_row("O-3", "抓握不好")
    second_row[RETURN_STORE_COLUMN] = "OTHER:US"
    _write_returns(initial, [initial_row])
    _write_returns(first, [_return_row("O-2", "不够保暖")])
    _write_returns(second, [second_row])
    dataset_id = str(_create_managed_returns(service, initial)["id"])
    inspections = {
        source: service.inspect_return_import(source, source.name)
        for source in (first, second)
    }
    _synchronize_first_import_commits(service, monkeypatch)

    def append(source: Path) -> dict[str, object]:
        return service.import_returns(
            source_path=source,
            original_name=source.name,
            content_type="text/csv",
            mode="append",
            dataset_id=dataset_id,
            actor_id="user-1",
            _inspection=inspections[source],
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(append, source) for source in (first, second)]
        results = []
        errors = []
        for future in futures:
            try:
                results.append(future.result(timeout=10))
            except ValueError as exc:
                errors.append(exc)

    assert len(results) == 1
    assert len(errors) == 1
    assert str(errors[0]) == "上传文件与所选数据源的店铺/站点不一致"
    with context.database.connect() as connection:
        dataset = connection.execute(
            "SELECT current_version, source_key FROM datasets WHERE id = ?",
            (dataset_id,),
        ).fetchone()
        imports = connection.execute(
            "SELECT source_key FROM dataset_imports WHERE dataset_id = ?",
            (dataset_id,),
        ).fetchall()
    assert dataset["current_version"] == 2
    assert len(imports) == 1
    assert dataset["source_key"] == imports[0]["source_key"]


def test_return_import_copy_failure_cleans_unique_source_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    source = tmp_path / "copy-failure.csv"
    _write_returns(source, [_return_row("O-1", "偏小")])
    before = _database_counts(context.database)
    original_copy = dataset_service_module.shutil.copy2

    def failing_copy(source_path, destination, *args, **kwargs):
        destination_path = Path(destination)
        if "imports" in destination_path.parts:
            destination_path.write_bytes(b"partial")
            raise OSError("injected copy failure")
        return original_copy(source_path, destination, *args, **kwargs)

    monkeypatch.setattr(dataset_service_module.shutil, "copy2", failing_copy)
    with pytest.raises(OSError, match="injected copy failure"):
        service.import_returns(
            source_path=source,
            original_name=source.name,
            content_type="text/csv",
            mode="create",
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

    monkeypatch.setattr(dataset_service_module.shutil, "copy2", failing_copy)
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
    original_copy = dataset_service_module.shutil.copy2
    both_copied = threading.Barrier(3)
    publish_gate = threading.Event()

    def synchronized_copy(source_path, temporary, *args, **kwargs):
        result = original_copy(source_path, temporary, *args, **kwargs)
        both_copied.wait(timeout=10)
        if not publish_gate.wait(timeout=10):
            raise TimeoutError("等待发布 Blob 超时")
        return result

    monkeypatch.setattr(dataset_service_module.shutil, "copy2", synchronized_copy)

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


def test_dataset_versions_reuse_identical_blob(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    source = tmp_path / "same-content.csv"
    _write_returns(source, [_return_row("O-1", "偏小")])

    created = _create_managed_returns(service, source)
    service.add_version(
        dataset_id=str(created["id"]),
        source_path=source,
        original_name=source.name,
        content_type="text/csv",
        change_note="重复内容",
        actor_id="user-1",
    )

    with context.database.connect() as connection:
        rows = connection.execute(
            """
            SELECT file_path, sha256 FROM dataset_versions
            WHERE dataset_id = ? ORDER BY version
            """,
            (created["id"],),
        ).fetchall()

    assert len(rows) == 2
    assert rows[0]["file_path"] == rows[1]["file_path"]
    assert rows[0]["sha256"] == rows[1]["sha256"]
    assert Path(str(rows[0]["file_path"])).parent.name == "blobs"


def test_storage_cleanup_deduplicates_legacy_files(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    source = tmp_path / "duplicate.csv"
    _write_returns(source, [_return_row("O-1", "偏小")])
    created = _create_managed_returns(service, source)
    service.add_version(
        dataset_id=str(created["id"]),
        source_path=source,
        original_name=source.name,
        content_type="text/csv",
        change_note="重复内容",
        actor_id="user-1",
    )

    with context.database.connect() as connection:
        rows = connection.execute(
            """
            SELECT id, file_path FROM dataset_versions
            WHERE dataset_id = ? ORDER BY version
            """,
            (created["id"],),
        ).fetchall()
    legacy_dir = tmp_path / "uploads" / "legacy"
    legacy_dir.mkdir(parents=True)
    legacy_paths = [legacy_dir / "v1.csv", legacy_dir / "v2.csv"]
    for row, legacy_path in zip(rows, legacy_paths, strict=True):
        shutil.copy2(str(row["file_path"]), legacy_path)
        with context.database.transaction(immediate=True) as connection:
            connection.execute(
                "UPDATE dataset_versions SET file_path = ? WHERE id = ?",
                (str(legacy_path), row["id"]),
            )

    before = service.storage_summary([str(created["id"])])
    result = service.cleanup_storage(
        dataset_ids=[str(created["id"])],
        retention_days=30,
        retain_latest=2,
        actor_id="user-1",
    )

    assert before["duplicate_groups"] == 1
    assert before["dedup_reclaimable_bytes"] == source.stat().st_size
    assert result["deduplicated_files"] == 2
    assert result["pruned_versions"] == 0
    assert result["freed_bytes"] == source.stat().st_size * 2
    assert all(not path.exists() for path in legacy_paths)
    with context.database.connect() as connection:
        stored_paths = connection.execute(
            """
            SELECT DISTINCT file_path FROM dataset_versions
            WHERE dataset_id = ?
            """,
            (created["id"],),
        ).fetchall()
    assert len(stored_paths) == 1
    assert Path(str(stored_paths[0]["file_path"])).exists()


def test_storage_cleanup_protects_current_and_referenced_versions(
    tmp_path: Path,
) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    source = tmp_path / "retention.csv"
    _write_returns(source, [_return_row("O-1", "偏小")])
    created = _create_managed_returns(service, source)
    dataset_id = str(created["id"])
    for version in range(2, 5):
        _write_returns(source, [_return_row(f"O-{version}", f"问题-{version}")])
        service.add_version(
            dataset_id=dataset_id,
            source_path=source,
            original_name=source.name,
            content_type="text/csv",
            change_note=f"版本 {version}",
            actor_id="user-1",
        )

    with context.database.transaction(immediate=True) as connection:
        versions = connection.execute(
            """
            SELECT id, version FROM dataset_versions
            WHERE dataset_id = ? ORDER BY version
            """,
            (dataset_id,),
        ).fetchall()
        version_ids = {int(row["version"]): str(row["id"]) for row in versions}
        connection.execute(
            """
            UPDATE dataset_versions SET created_at = '2000-01-01T00:00:00+00:00'
            WHERE dataset_id = ?
            """,
            (dataset_id,),
        )
        connection.execute(
            "UPDATE tasks SET dataset_version_id = ? WHERE id = 'task-1'",
            (version_ids[3],),
        )

    before = service.storage_summary(
        [dataset_id],
        retention_days=30,
        retain_latest=1,
    )
    result = service.cleanup_storage(
        dataset_ids=[dataset_id],
        retention_days=30,
        retain_latest=1,
        actor_id="user-1",
    )

    assert before["expired_versions"] == 2
    assert result["pruned_versions"] == 2
    with context.database.connect() as connection:
        remaining = connection.execute(
            """
            SELECT version FROM dataset_versions
            WHERE dataset_id = ? ORDER BY version
            """,
            (dataset_id,),
        ).fetchall()
    assert [int(row["version"]) for row in remaining] == [3, 4]
    assert result["after"]["task_referenced_versions"] == 1
