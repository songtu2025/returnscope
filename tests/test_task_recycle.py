from pathlib import Path

import pytest
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.testclient import TestClient
from test_classification_result_pool import _publish, _seed_result_context
from test_dashboard_versions import _create_dashboard
from test_task_planning import _create_task, _database_with_inputs

from web_backend.classification_result_service import ClassificationResultService
from web_backend.dashboard_service import DashboardService
from web_backend.routers.task_recycle_routes import register_task_recycle_routes
from web_backend.task_execution.segment_state import SegmentStateMixin
from web_backend.task_service import TaskService


def test_purge_keeps_result_dashboard_and_provenance(tmp_path: Path):
    context = _seed_result_context(tmp_path)
    version = _publish(context)
    service = TaskService(context.database, data_dir=tmp_path)
    results = ClassificationResultService(context.database)
    dashboards = DashboardService(context.database)
    _, dashboard = _create_dashboard(dashboards, version["version_id"])
    result_before = results.get(version["version_id"])
    records_before = dashboards.records(
        dashboard["id"], dashboard["version"]["version_id"]
    )
    with context.database.transaction() as connection:
        connection.execute("UPDATE task_segments SET status='completed'")
    task = service.get(context.task_id)
    segment = task["segments"][0]
    folder = tmp_path / "results" / task["id"] / "segments"
    folder.mkdir(parents=True)
    checkpoint = folder / f"{segment['id']}-classifications.json"
    checkpoint.write_text("{}")
    temporary_checkpoint = checkpoint.with_suffix(".json.tmp")
    temporary_checkpoint.write_text("interrupted-write")
    old_export = folder / f"{segment['id']}-analysis-v1.xlsx"
    old_export.write_bytes(b"synthetic")
    unrelated = folder / "other-analysis-v1.xlsx"
    unrelated.write_bytes(b"retained")
    # 合成发布器的路径不属于运行目录，替换为本测试的执行项产物。
    with context.database.transaction() as connection:
        connection.execute(
            "UPDATE task_segments SET result_json_path=?,result_file_path=? WHERE id=?",
            (str(checkpoint), str(old_export), segment["id"]),
        )
    removed = service.segment_action(
        task["id"], segment["segment_key"], "delete", "user-1", task["revision"]
    )
    assert service.recycle.listings()["total"] == 1
    service.segment_action(
        task["id"], segment["segment_key"], "purge", "user-1", removed["revision"]
    )
    assert not checkpoint.exists() and not old_export.exists()
    assert not temporary_checkpoint.exists()
    assert unrelated.exists()
    assert service.recycle.listings()["total"] == 0
    assert service.get(task["id"])["segments"] == []
    assert results.get(version["version_id"]) == result_before
    assert (
        dashboards.records(dashboard["id"], dashboard["version"]["version_id"])
        == records_before
    )
    with context.database.connect() as connection:
        assert connection.execute(
            "SELECT id FROM task_segments WHERE id=?", (segment["id"],)
        ).fetchone()
        assert not list(connection.execute("PRAGMA foreign_key_check"))
    with pytest.raises(ValueError, match="永久删除"):
        current = service.get(task["id"])
        service.segment_action(
            task["id"], segment["segment_key"], "restore", "user-1", current["revision"]
        )


def test_recycled_queued_listing_restores_paused_and_progress_stays_excluded(
    tmp_path: Path,
):
    database, _, _ = _database_with_inputs(tmp_path)
    task = _create_task(database, "run_ready")
    service = TaskService(database)
    segment = task["segments"][0]
    removed = service.segment_action(
        task["id"], segment["segment_key"], "delete", "user-1", task["revision"]
    )
    progress = SegmentStateMixin()
    progress.database = database
    progress._update_segment_progress(task["id"], segment["id"], 1, 2)
    assert service.get(task["id"])["progress_total"] == 0
    restored = service.segment_action(
        task["id"], segment["segment_key"], "restore", "user-1", removed["revision"]
    )
    assert restored["segments"][0]["status"] == "paused"
    assert restored["status"] == "paused"


def test_recycle_api_auth_search_and_page_bounds(tmp_path: Path):
    database, _, _ = _database_with_inputs(tmp_path)
    task = _create_task(database, "run_ready")
    service = TaskService(database)
    service.segment_action(
        task["id"],
        task["segments"][0]["segment_key"],
        "delete",
        "user-1",
        task["revision"],
    )
    authenticated = True

    def user():
        if not authenticated:
            raise HTTPException(401)
        return {"id": "user-1"}

    app = FastAPI()
    router = APIRouter()
    register_task_recycle_routes(router, service, user)
    app.include_router(router)
    client = TestClient(app)
    assert client.get("/api/tasks/recycle").json()["total"] == 1
    assert client.get("/api/tasks/recycle?q=no-match").json()["total"] == 0
    assert client.get("/api/tasks/recycle?page_size=101").status_code == 422
    authenticated = False
    assert client.get("/api/tasks/recycle").status_code == 401


def test_purge_cleanup_failure_stays_recoverable(tmp_path: Path, monkeypatch):
    database, _, _ = _database_with_inputs(tmp_path)
    task = _create_task(database, "run_ready")
    service = TaskService(database, data_dir=tmp_path)
    segment = task["segments"][0]
    removed = service.segment_action(
        task["id"], segment["segment_key"], "delete", "user-1", task["revision"]
    )
    folder = tmp_path / "results" / task["id"] / "segments"
    folder.mkdir(parents=True)
    checkpoint = folder / f"{segment['id']}-classifications.json"
    checkpoint.write_text("synthetic-checkpoint")
    with database.transaction() as connection:
        connection.execute(
            "UPDATE task_segments SET result_json_path=? WHERE id=?",
            (str(checkpoint), segment["id"]),
        )

    def partial_cleanup(*_):
        checkpoint.unlink()
        return ["synthetic-failure"]

    monkeypatch.setattr(
        "web_backend.tasks.recycle.remove_cleanup_files", partial_cleanup
    )
    with pytest.raises(ValueError, match="清理未完成"):
        service.segment_action(
            task["id"], segment["segment_key"], "purge", "user-1", removed["revision"]
        )
    assert service.recycle.listings()["total"] == 1
    assert checkpoint.read_text() == "synthetic-checkpoint"


def test_pending_removal_survives_worker_restart(tmp_path: Path):
    from web_backend.worker import TaskWorker

    database, _, _ = _database_with_inputs(tmp_path)
    task = _create_task(database, "run_ready")
    worker = TaskWorker(database, object(), concurrency=1)
    worker._claim_next_segment()
    service = TaskService(database)
    task = service.get(task["id"])
    service.segment_action(
        task["id"],
        task["segments"][0]["segment_key"],
        "delete",
        "user-1",
        task["revision"],
    )
    worker._recover_interrupted_segments()
    current = service.get(task["id"])
    assert current["status"] == "empty"
    assert current["progress_total"] == 0
    assert current["segments"][0]["deleted_at"]
    assert worker._claim_next_segment() is None


@pytest.mark.parametrize("outcome", ["completed", "failed"])
def test_removal_finishes_when_execution_wins_race(tmp_path: Path, outcome: str):
    from web_backend.tasks.recycle_state import finish_pending_removals
    from web_backend.worker import TaskWorker

    database, _, _ = _database_with_inputs(tmp_path)
    task = _create_task(database, "run_ready")
    TaskWorker(database, object(), concurrency=1)._claim_next_segment()
    service = TaskService(database)
    task = service.get(task["id"])
    service.segment_action(
        task["id"],
        task["segments"][0]["segment_key"],
        "delete",
        "user-1",
        task["revision"],
    )
    with database.transaction() as connection:
        connection.execute(
            "UPDATE task_segments SET status=?,requested_action=NULL", (outcome,)
        )
        finish_pending_removals(connection, task["id"])
    assert service.recycle.listings()["total"] == 1
    assert service.recycle.listings()["items"][0]["status"] == outcome


def test_recycle_migration_validates_and_rolls_back(tmp_path: Path):
    database, _, _ = _database_with_inputs(tmp_path)
    database.upgrade_schema()
    database.validate_production_schema()
    with database.transaction() as connection:
        connection.execute(
            "UPDATE app_migrations SET checksum='invalid' WHERE migration_id='20261014_listing_recycle'"
        )
    with pytest.raises(RuntimeError, match="回收站迁移校验失败"):
        database.upgrade_schema()


def test_save_failure_leaves_listing_visible_and_retryable(tmp_path: Path):
    from web_backend.tasks.recycle_state import fail_pending_removal
    from web_backend.worker import TaskWorker

    database, _, _ = _database_with_inputs(tmp_path)
    task = _create_task(database, "run_ready")
    TaskWorker(database, object(), concurrency=1)._claim_next_segment()
    service = TaskService(database)
    task = service.get(task["id"])
    segment = task["segments"][0]
    service.segment_action(
        task["id"], segment["segment_key"], "delete", "user-1", task["revision"]
    )
    assert fail_pending_removal(database, segment["id"])
    failed = service.get(task["id"])
    assert failed["segments"][0]["deleted_at"] is None
    assert failed["segments"][0]["removal_requested_at"] is None
    assert "移除未完成" in failed["segments"][0]["error"]
    assert service.recycle.listings()["total"] == 0
    service.segment_action(
        task["id"], segment["segment_key"], "delete", "user-1", failed["revision"]
    )
    assert service.recycle.listings()["total"] == 1
