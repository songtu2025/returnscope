from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.testclient import TestClient
from test_classification_result_pool import _publish, _seed_result_context
from test_dashboard_versions import _create_dashboard
from test_task_planning import (
    _add_resolved_product_version,
    _create_task,
    _database_with_inputs,
)

from web_backend.agent_runner_parent_result import ParentResultMixin
from web_backend.classification_result_service import ClassificationResultService
from web_backend.dashboard_service import DashboardService
from web_backend.routers.task_segment_routes import register_segment_control_routes
from web_backend.task_execution.legacy_export import LegacyResultExportMixin
from web_backend.task_execution.parent_refresh_state import _parent_refresh_state
from web_backend.task_service import TaskRevisionConflict, TaskService
from web_backend.worker import TaskWorker


def test_deleted_listing_keeps_published_result_and_can_restore(tmp_path: Path):
    context = _seed_result_context(tmp_path)
    version = _publish(context)
    service = TaskService(context.database)
    with context.database.transaction() as connection:
        connection.execute(
            "UPDATE task_segments SET status='completed', progress_current=progress_total"
        )
    before = service.get(context.task_id)
    key = before["segments"][0]["segment_key"]
    result_before = ClassificationResultService(context.database).get(
        version["version_id"]
    )
    dashboards = DashboardService(context.database)
    _, dashboard = _create_dashboard(dashboards, version["version_id"])
    dashboard_before = dashboards.records(
        dashboard["id"], dashboard["version"]["version_id"]
    )
    deleted = service.segment_action(
        context.task_id, key, "delete", "user-1", before["revision"]
    )
    assert deleted["segments"][0]["deleted_at"]
    assert deleted["status"] == "empty"
    assert deleted["progress_total"] == 0
    assert service.list()[0]["listing_count"] == 0
    assert service.list()[0]["segments"] == []
    assert (
        dashboards.records(dashboard["id"], dashboard["version"]["version_id"])
        == dashboard_before
    )
    assert (
        ClassificationResultService(context.database).get(version["version_id"])
        == result_before
    )
    with pytest.raises(ValueError, match="已删除"):
        service.segment_action(
            context.task_id, key, "resume", "user-1", deleted["revision"]
        )
    with pytest.raises(TaskRevisionConflict):
        service.segment_action(
            context.task_id, key, "restore", "user-1", before["revision"]
        )
    restored = service.segment_action(
        context.task_id, key, "restore", "user-1", deleted["revision"]
    )
    assert restored["segments"][0]["deleted_at"] is None
    assert restored["segments"][0]["status"] == "completed"
    assert restored["status"] == "completed"
    assert restored["progress_total"] == before["segments"][0]["progress_total"]
    assert (
        ClassificationResultService(context.database).get(version["version_id"])
        == result_before
    )


def test_cancel_delete_restore_never_queues_deleted_listing(tmp_path: Path):
    database, _, _ = _database_with_inputs(tmp_path)
    task = _create_task(database, "run_ready")
    service = TaskService(database)
    key = task["segments"][0]["segment_key"]
    cancelled = service.segment_action(
        task["id"], key, "cancel", "user-1", task["revision"], "合成取消"
    )
    deleted = service.segment_action(
        task["id"], key, "delete", "user-1", cancelled["revision"]
    )
    worker = TaskWorker(database, object(), concurrency=1)
    assert worker._claim_next_segment() is None
    restored = service.segment_action(
        task["id"], key, "restore", "user-1", deleted["revision"]
    )
    assert restored["segments"][0]["status"] == "paused"
    assert worker._claim_next_segment() is None
    resumed = service.segment_action(
        task["id"], key, "resume", "user-1", restored["revision"]
    )
    assert resumed["segments"][0]["status"] == "queued"
    assert worker._claim_next_segment()[0] == task["id"]


def test_running_listing_must_stop_before_deletion(tmp_path: Path):
    database, _, _ = _database_with_inputs(tmp_path)
    task = _create_task(database, "run_ready")
    worker = TaskWorker(database, object(), concurrency=1)
    claimed = worker._claim_next_segment()
    assert claimed is not None
    service = TaskService(database)
    running = service.get(task["id"])
    key = running["segments"][0]["segment_key"]
    removing = service.segment_action(
        task["id"], key, "delete", "user-1", running["revision"]
    )
    assert removing["segments"][0]["removal_requested_at"]
    assert removing["segments"][0]["deleted_at"] is None
    with pytest.raises(ValueError, match="正在移除"):
        service.segment_action(
            task["id"], key, "resume", "user-1", removing["revision"]
        )
    from web_backend.tasks.recycle_state import finish_pending_removals

    with database.transaction() as connection:
        connection.execute("UPDATE task_segments SET status='paused'")
        finish_pending_removals(connection, task["id"])
    removed = service.get(task["id"])["segments"][0]
    assert removed["deleted_at"]
    assert removed["removal_requested_at"] is None


def test_replan_keeps_removed_listing_and_only_queues_other_listing(tmp_path: Path):
    database, _, products = _database_with_inputs(tmp_path)
    task = _create_task(database, "run_ready")
    service = TaskService(database)
    key = task["segments"][0]["segment_key"]
    cancelled = service.segment_action(
        task["id"], key, "cancel", "user-1", task["revision"], "合成取消"
    )
    deleted = service.segment_action(
        task["id"], key, "delete", "user-1", cancelled["revision"]
    )
    with database.transaction() as connection:
        connection.execute(
            "UPDATE tasks SET status='blocked' WHERE id=?", (task["id"],)
        )
    product_version = _add_resolved_product_version(database, products)
    plan = service.replan_preflight(task["id"], product_version)
    replanned = service.replan(
        task["id"],
        "user-1",
        product_version,
        deleted["revision"],
        plan["plan_hash"],
        "run_ready",
        "合成补充品类",
    )
    removed = next(
        segment for segment in replanned["segments"] if segment["segment_key"] == key
    )
    assert removed["deleted_at"] == deleted["segments"][0]["deleted_at"]
    assert removed["status"] == "cancelled"
    claim = TaskWorker(database, object(), concurrency=1)._claim_next_segment()
    assert claim is not None
    assert claim[1] != removed["id"]


def test_stale_parent_refresh_cannot_overwrite_deleted_listing_state(tmp_path: Path):
    database, _, _ = _database_with_inputs(tmp_path)
    task = _create_task(database, "run_ready")
    service = TaskService(database)
    key = task["segments"][0]["segment_key"]
    cancelled = service.segment_action(
        task["id"], key, "cancel", "user-1", task["revision"], "合成取消"
    )
    state = _parent_refresh_state(
        task, task["segments"], ParentResultMixin._parent_status_text
    )
    deleted = service.segment_action(
        task["id"], key, "delete", "user-1", cancelled["revision"]
    )
    runner = ParentResultMixin()
    runner.database = database
    runner._persist_parent_refresh(task["id"], task, state)
    runner._record_parent_result_error(
        task["id"], "合成旧错误", "partial", task["revision"]
    )
    current = service.get(task["id"])
    assert current["revision"] == deleted["revision"]
    assert current["status"] == "empty"
    assert current["progress_total"] == 0
    assert current["error"] is None


def test_removal_migration_is_repeatable_and_checks_checksum(tmp_path: Path):
    database, _, _ = _database_with_inputs(tmp_path)
    database.upgrade_schema()
    database.validate_production_schema()
    with database.transaction() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM app_migrations WHERE migration_id='20261013_listing_soft_delete'"
            ).fetchone()[0]
            == 1
        )
        connection.execute(
            "UPDATE app_migrations SET checksum='invalid' WHERE migration_id='20261013_listing_soft_delete'"
        )
    with pytest.raises(RuntimeError, match="迁移校验失败"):
        database.upgrade_schema()


def test_parent_export_cannot_restore_stale_file_after_deletion(tmp_path, monkeypatch):
    database, _, _ = _database_with_inputs(tmp_path)
    task = _create_task(database, "run_ready")
    service = TaskService(database)
    key = task["segments"][0]["segment_key"]
    cancelled = service.segment_action(
        task["id"], key, "cancel", "user-1", task["revision"], "合成取消"
    )
    loader = ParentResultMixin()
    loader.database = database
    data = SimpleNamespace(results={}, dataset=None, taxonomy=None)

    def delete_during_export(*_args):
        service.segment_action(
            task["id"], key, "delete", "user-1", cancelled["revision"]
        )
        return {}

    runner = SimpleNamespace(
        _load_task=loader._load_task,
        _completed_parent_data=lambda *_args: data,
        _parent_export_metrics=delete_during_export,
        _write_checkpoint=lambda *_args: None,
        settings=SimpleNamespace(data_dir=tmp_path),
        database=database,
    )
    monkeypatch.setattr(
        "web_backend.task_execution.legacy_export.export_results",
        lambda **_kwargs: None,
    )
    LegacyResultExportMixin._build_parent_result(runner, task["id"], None, "cancelled")
    assert service.get(task["id"])["result_file_path"] is None


def test_listing_removal_http_rejects_active_stale_and_anonymous_requests(
    tmp_path: Path,
):
    database, _, _ = _database_with_inputs(tmp_path)
    task = _create_task(database, "run_ready")
    service = TaskService(database)
    authenticated = True

    def user():
        if not authenticated:
            raise HTTPException(status_code=401, detail="请登录")
        return {"id": "user-1", "is_admin": False}

    app = FastAPI()
    router = APIRouter()
    register_segment_control_routes(router, service, user)
    app.include_router(router)
    client = TestClient(app)
    base = f"/api/tasks/{task['id']}/segments/{task['segments'][0]['segment_key']}"
    cancelled = client.post(
        base + "/cancel",
        json={"expected_revision": task["revision"], "note": "合成取消"},
    )
    assert cancelled.status_code == 200
    assert (
        client.post(
            base + "/delete", json={"expected_revision": task["revision"]}
        ).status_code
        == 409
    )
    deleted = client.post(
        base + "/delete", json={"expected_revision": cancelled.json()["revision"]}
    )
    assert deleted.status_code == 200
    authenticated = False
    assert (
        client.post(
            base + "/restore", json={"expected_revision": deleted.json()["revision"]}
        ).status_code
        == 401
    )
