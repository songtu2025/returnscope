import sqlite3

import pytest
from test_task_detail_queries import _add_segment
from test_task_planning import _create_task, _database_with_inputs

from web_backend.common import json_value
from web_backend.task_service import TaskRevisionConflict, TaskService


def _runtime(tmp_path):
    database, _, _ = _database_with_inputs(tmp_path)
    task = _create_task(database, "run_ready")
    source = next(x for x in task["segments"] if x["status"] == "queued")
    for status in (
        "queued",
        "retry_pending",
        "paused",
        "completed",
        "running",
        "cancelled",
        "failed",
    ):
        _add_segment(database, source["id"], "extra-" + status, status)
    return database, TaskService(database), TaskService(database).get(str(task["id"]))


def _waiting(task):
    return [
        x["segment_key"]
        for x in task["segments"]
        if x["status"] in {"queued", "retry_pending", "paused"}
    ]


def test_reorder_preserves_history_blocked_and_event_data(tmp_path):
    database, service, task = _runtime(tmp_path)
    before = _waiting(task)
    after = list(reversed(before))
    result = service.reorder_segments(task["id"], "user-1", task["revision"], after)
    history = [
        x["segment_key"]
        for x in task["segments"]
        if x["status"] not in {"queued", "retry_pending", "paused", "blocked"}
    ]
    blocked = [x["segment_key"] for x in task["segments"] if x["status"] == "blocked"]
    assert [x["segment_key"] for x in result["segments"]] == history + after + blocked
    assert [x["execution_order"] for x in result["segments"]] == list(
        range(1, len(result["segments"]) + 1)
    )
    assert result["revision"] == task["revision"] + 1
    with database.connect() as connection:
        event = connection.execute(
            "SELECT data_json FROM task_events WHERE event_type = 'segments_reordered'"
        ).fetchone()
    assert json_value(event["data_json"], {}) == {"before": before, "after": after}


def test_noop_reorder_has_no_status_event_or_revision_changes(tmp_path):
    database, service, task = _runtime(tmp_path)
    before_events = service.events(task["id"])
    result = service.reorder_segments(
        task["id"], "user-1", task["revision"], _waiting(task)
    )
    assert result == task
    assert service.events(task["id"]) == before_events


@pytest.mark.parametrize("kind", ["duplicate", "missing", "foreign", "stale"])
def test_reorder_rejects_changed_waiting_set_and_stale_revision(tmp_path, kind):
    _, service, task = _runtime(tmp_path)
    keys = _waiting(task)
    requested = keys + [keys[0]] if kind == "duplicate" else keys[:-1]
    if kind == "foreign":
        requested = keys[:-1] + ["foreign"]
    revision = task["revision"] - 1 if kind == "stale" else task["revision"]
    message = "任务已被他人修改" if kind == "stale" else "等待片段已经变化"
    with pytest.raises(TaskRevisionConflict, match=message):
        service.reorder_segments(task["id"], "user-1", revision, requested)
    assert service.get(task["id"]) == task


def test_reorder_event_failure_rolls_back_order_revision_and_audit(tmp_path):
    database, service, task = _runtime(tmp_path)
    with database.transaction() as connection:
        connection.execute(
            "CREATE TRIGGER reject_reorder BEFORE INSERT ON task_events WHEN NEW.event_type = 'segments_reordered' BEGIN SELECT RAISE(ABORT, '模拟排序事件失败'); END"
        )
        audits = connection.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError, match="模拟排序事件失败"):
        service.reorder_segments(
            task["id"], "user-1", task["revision"], list(reversed(_waiting(task)))
        )
    assert service.get(task["id"]) == task
    with database.connect() as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
            == audits
        )
