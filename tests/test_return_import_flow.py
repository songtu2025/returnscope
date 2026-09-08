from __future__ import annotations

import shutil
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
from return_semantics.data import PRODUCT_COLUMNS, RETURN_COLUMNS, RETURN_STORE_COLUMN
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
    assert inspection["suggested_name"] == "SENWAYZON US 退货数据"
    assert inspection["matches"] == []

    one_off = service.import_returns(
        source_path=source,
        original_name=source.name,
        content_type="text/csv",
        mode="analyze_only",
        actor_id="user-1",
    )
    assert one_off["dataset"]["usage_scope"] == "task_input"
    assert one_off["dataset"]["source_name"] == "SENWAYZON US 退货数据"
    assert service.list("returns", "managed")
    assert one_off["dataset"]["id"] not in {
        item["id"] for item in service.list("returns", "managed")
    }

    repeated = service.inspect_return_import(source, source.name)
    assert repeated["duplicate"]["version_id"] == one_off["version_id"]


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
    original = dataset_service_module.read_return_csv
    observed: list[int | None] = []

    def tracking_read(path, usecols=None, nrows=None):
        observed.append(nrows)
        return original(path, usecols=usecols, nrows=nrows)

    monkeypatch.setattr(dataset_service_module, "read_return_csv", tracking_read)
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

    original_add_version = service.add_version
    first_attempt_barrier = threading.Barrier(2)
    synchronized_threads: set[int] = set()
    synchronized_threads_lock = threading.Lock()

    def synchronized_add_version(**kwargs):
        thread_id = threading.get_ident()
        with synchronized_threads_lock:
            should_wait = thread_id not in synchronized_threads
            synchronized_threads.add(thread_id)
        if should_wait:
            first_attempt_barrier.wait(timeout=5)
        return original_add_version(**kwargs)

    monkeypatch.setattr(service, "add_version", synchronized_add_version)

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
