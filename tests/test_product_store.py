"""覆盖产品入库的唯一性、原子性、迁移对账和文件退出在线读取。"""

import sqlite3
from pathlib import Path

import pandas as pd
import pytest
from database_migration_helpers import build_migration_settings

from web_backend.backup import create_backup, restore_backup
from web_backend.database import Database
from web_backend.dataset_files import DatasetRevisionConflict
from web_backend.dataset_service import DatasetService
from web_backend.datasets.product_backfill import (
    backfill_product_store,
    verify_product_artifacts,
)
from web_backend.datasets.product_store import load_product_frame, load_product_workbook
from web_backend.upgrade_database import upgrade_database


@pytest.fixture
def product_service(tmp_path):
    settings = build_migration_settings(tmp_path)
    settings.ensure_directories()
    database = Database(settings.database_path)
    database.initialize()
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO users(id,email,display_name,password_hash,created_at) "
            "VALUES ('user','test@example.invalid','测试','hash','2026-01-01')"
        )
    return DatasetService(database, settings)


def _import(service, rows=None):
    path = service.settings.data_dir / "source.xlsx"
    rows = (
        rows
        if rows is not None
        else [
            {"店铺/站点": " S:US ", "MSKU": "A", "Listing": "L", "扩展字段": "001"},
            {"店铺/站点": "S:UK", "MSKU": "A", "Listing": "L", "扩展字段": "002"},
        ]
    )
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame({"说明": ["保留工作表及其顺序"]}).to_excel(
            writer, sheet_name="说明", index=False
        )
        pd.DataFrame(rows).to_excel(writer, sheet_name="产品信息汇总表", index=False)
        pd.DataFrame().to_excel(writer, sheet_name="空白工作表", index=False)
    return service.create(
        "产品", "products", "", path, path.name, "application/xlsx", "", "user"
    )


def test_workbook_roundtrip_and_database_unique_constraint(product_service):
    service = product_service
    created = _import(service)
    version = created["versions"][0]
    path = Path(service.version_file(created["id"])["file_path"])
    workbook = load_product_workbook(service.database, path)
    assert list(workbook) == ["说明", "产品信息汇总表", "空白工作表"]
    assert workbook["产品信息汇总表"]["扩展字段"].tolist() == ["001", "002"]
    assert workbook["产品信息汇总表"]["店铺/站点"].tolist() == [" S:US ", "S:UK"]
    with service.database.transaction() as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO product_rows VALUES (?,99,'S:US','A','[]')",
                (version["sha256"],),
            )


@pytest.mark.parametrize("conflicting_listing", ["L", "OTHER"])
def test_duplicate_import_rejects_whole_dataset(product_service, conflicting_listing):
    service = product_service
    with pytest.raises(ValueError, match="重复数据.*2, 3"):
        _import(
            service,
            [
                {"店铺/站点": "S:US", "MSKU": " A ", "Listing": "L"},
                {"店铺/站点": " S:US ", "MSKU": "A", "Listing": conflicting_listing},
            ],
        )
    with service.database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM datasets").fetchone()[0] == 0
        assert (
            connection.execute("SELECT COUNT(*) FROM product_rows").fetchone()[0] == 0
        )


def test_edit_and_completion_use_database_and_preserve_old_snapshot(
    product_service, monkeypatch
):
    service = product_service
    created = _import(service)
    old_path = Path(service.version_file(created["id"])["file_path"])

    def no_excel(*args, **kwargs):
        raise AssertionError("已入库资料不应再解析 Excel")

    monkeypatch.setattr(pd, "read_excel", no_excel)
    assert service.preview_rows(created["id"])["total"] == 2
    updated = service.update_product_row(
        created["id"], 0, 1, {"扩展字段": "003"}, "", "user"
    )
    assert updated["current_version"] == 2
    assert load_product_frame(service.database, old_path)["扩展字段"].iloc[0] == "001"
    assert service.preview_rows(created["id"])["records"][0]["扩展字段"] == "003"
    service.complete_product_categories(
        created["id"],
        2,
        "S:US",
        [{"msku": "A", "listing": "L", "category_a": "鞋履", "category_b": "水鞋"}],
        "",
        "user",
    )
    assert service.preview_rows(created["id"])["records"][0]["品类B"] == "水鞋"
    with pytest.raises(DatasetRevisionConflict):
        service.update_product_row(
            created["id"], 0, 1, {"扩展字段": "旧修改"}, "", "user"
        )
    with pytest.raises(ValueError, match="必须唯一"):
        service.update_product_row(
            created["id"], 1, 3, {"店铺/站点": "S:US"}, "", "user"
        )
    assert service.get(created["id"])["current_version"] == 3


def test_backfill_is_idempotent_and_restore_keeps_post_cutover_edits(product_service):
    service = product_service
    created = _import(service)
    with service.database.transaction() as connection:
        connection.execute("DELETE FROM product_workbooks")
    with pytest.raises(RuntimeError, match="尚未入库"):
        service.database.validate_production_schema()
    stats = backfill_product_store(service.database)
    assert stats == {"workbooks": 1, "rows": 2}
    assert backfill_product_store(service.database) == stats
    service.database.validate_production_schema()
    service.update_product_row(
        created["id"], 0, 1, {"扩展字段": "切换后修改"}, "", "user"
    )
    assert verify_product_artifacts(service.database) == 1
    backup = create_backup(service.settings)
    service.update_product_row(
        created["id"], 0, 2, {"扩展字段": "后续修改"}, "", "user"
    )
    restore_backup(service.settings, backup)
    assert service.preview_rows(created["id"])["records"][0]["扩展字段"] == "切换后修改"


def test_explicit_upgrade_backfills_and_backup_restores_previous_schema(
    product_service,
):
    service = product_service
    created = _import(service)
    with service.database.transaction() as connection:
        connection.execute("DROP TABLE product_rows")
        connection.execute("DROP TABLE product_workbooks")
        connection.execute(
            "DELETE FROM app_migrations WHERE migration_id='20261017_product_rows'"
        )
    with pytest.raises(ValueError, match="必须停止"):
        upgrade_database(service.settings, app_stopped=False)
    backup = upgrade_database(service.settings, app_stopped=True)
    assert service.preview_rows(created["id"])["total"] == 2
    restore_backup(service.settings, backup)
    with service.database.connect() as connection:
        assert (
            connection.execute(
                "SELECT 1 FROM sqlite_master WHERE name='product_rows'"
            ).fetchone()
            is None
        )
    assert Path(service.version_file(created["id"])["file_path"]).exists()


def test_backfill_failure_rolls_back_entire_batch(product_service):
    service = product_service
    _import(service)
    second = _import(service, [{"店铺/站点": "OTHER", "MSKU": "B", "Listing": "B"}])
    Path(service.version_file(second["id"])["file_path"]).write_bytes(b"broken")
    with service.database.transaction() as connection:
        connection.execute("DELETE FROM product_workbooks")
    with pytest.raises(ValueError, match="摘要不一致"):
        backfill_product_store(service.database)
    with pytest.raises(ValueError):
        verify_product_artifacts(service.database)
    with service.database.connect() as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM product_rows").fetchone()[0] == 0
        )


def test_preflight_after_restart_never_parses_product_excel(tmp_path, monkeypatch):
    from test_task_planning import _database_with_inputs

    from web_backend import dataset_cache
    from web_backend.task_plan_service import TaskPlanService

    database, _, _ = _database_with_inputs(tmp_path)
    args = ("version-returns", "version-products", "SEEKWAY:US", "L1", "config-1")
    before = TaskPlanService(database).preflight(*args)
    dataset_cache._cache.clear()

    def no_excel(*args, **kwargs):
        raise AssertionError("任务规划不应读取产品 Excel")

    monkeypatch.setattr(pd, "read_excel", no_excel)
    after = TaskPlanService(Database(database.path)).preflight(*args)
    assert after == before


def test_backfill_includes_task_frozen_input(tmp_path):
    import json

    from test_task_planning import _create_task, _database_with_inputs

    from web_backend.dataset_files import _sha256_file
    from web_backend.datasets.product_store import save_product_workbook

    database, _, path = _database_with_inputs(tmp_path)
    digest = _sha256_file(path)
    with database.transaction() as connection:
        connection.execute(
            "UPDATE dataset_versions SET sha256=? WHERE id='version-products'",
            (digest,),
        )
        save_product_workbook(
            connection, digest, pd.read_excel(path, sheet_name=None, dtype=str)
        )
    task = _create_task(database, "run_ready")
    service = DatasetService(database, build_migration_settings(tmp_path))
    service.update_product_row(
        "dataset-products", 0, 1, {"Listing": "NEW"}, "", "user-1"
    )
    with database.connect() as connection:
        current_path = Path(
            connection.execute(
                "SELECT file_path FROM dataset_versions WHERE id='version-products'"
            ).fetchone()[0]
        )
        snapshot = connection.execute(
            "SELECT snapshot_json FROM tasks WHERE id=?", (task["id"],)
        ).fetchone()[0]
    assert json.loads(snapshot)["products"]["sha256"] == digest
    frozen_path = current_path.with_name(f"{digest}.xlsx")
    with database.transaction() as connection:
        connection.execute("DELETE FROM product_workbooks")
    assert backfill_product_store(database)["workbooks"] == 2
    assert load_product_frame(database, frozen_path)["Listing"].iloc[0] == "L1"
    assert load_product_frame(database, current_path)["Listing"].iloc[0] == "NEW"


def test_product_api_rejects_duplicate_and_stale_updates(product_service):
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient

    from web_backend.routers.datasets import create_dataset_router

    service = product_service
    created = _import(service)
    allowed = True

    def user():
        if not allowed:
            raise HTTPException(status_code=401)
        return {"id": "user"}

    app = FastAPI()
    app.include_router(create_dataset_router(service, service.settings, user))
    with TestClient(app) as client:
        endpoint = f"/api/datasets/{created['id']}/rows"
        payload = {
            "row_index": 1,
            "expected_version": 1,
            "changes": {"店铺/站点": "S:US"},
        }
        response = client.patch(endpoint, json=payload)
        assert response.status_code == 400
        assert "必须唯一" in response.json()["detail"]
        payload["changes"] = {"扩展字段": "修改"}
        assert client.patch(endpoint, json=payload).status_code == 200
        assert client.patch(endpoint, json=payload).status_code == 409
        allowed = False
        assert client.get(endpoint).status_code == 401
        assert client.patch(endpoint, json=payload).status_code == 401
    assert service.get(created["id"])["current_version"] == 2
