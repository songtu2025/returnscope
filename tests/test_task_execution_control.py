import pytest
from task_execution_helpers import (
    EVENT_FAILURE,
    audit_rows,
    fail_event_write,
    trace_queries,
    transaction_statements,
)
from test_task_detail_queries import _add_segment
from test_task_scheduling import _runtime

from web_backend.task_service import TaskRevisionConflict


@pytest.mark.parametrize("status", ["queued", "running"])
@pytest.mark.parametrize("has_running", [False, True])
def test_pause_preserves_history_and_transaction_budget(
    tmp_path, monkeypatch, status, has_running
):
    database, service, task = _runtime(tmp_path)
    with database.transaction() as connection:
        connection.execute("UPDATE tasks SET status = ?", (status,))
        if not has_running:
            connection.execute(
                "UPDATE task_segments SET status = 'completed' WHERE status = 'running'"
            )
    before = service.get(task["id"])
    queries = trace_queries(database, monkeypatch)
    result = service.pause(task["id"], "user-1", task["revision"])
    assert result["status"] == ("running" if has_running else "paused")
    assert result["stage"] == ("正在暂停" if has_running else "已暂停")
    assert result["pause_requested"]
    assert result["revision"] == task["revision"] + 1
    for old, new in zip(before["segments"], result["segments"], strict=True):
        if old["status"] in {"queued", "retry_pending"}:
            assert new["status"] == "paused"
        elif old["status"] == "running":
            assert new["requested_action"] == "pause"
        else:
            assert new == old
    statements = transaction_statements(queries)
    assert [sql.split()[0] for sql in statements] == [
        "SELECT",
        "UPDATE",
        "UPDATE",
        "UPDATE",
        "INSERT",
        "INSERT",
    ]
    event = service.events(task["id"])[-1]
    assert event["event_type"] == "pause"
    assert event["data"]["before"]["status"] == status


@pytest.mark.parametrize("status", ["paused", "cancelled"])
def test_resume_requeues_only_unfinished_segments(tmp_path, monkeypatch, status):
    database, service, task = _runtime(tmp_path)
    _add_segment(
        database, task["segments"][0]["id"], "extra-not_started", "not_started"
    )
    with database.transaction() as connection:
        connection.execute(
            "UPDATE tasks SET status = ?, pause_requested = 1", (status,)
        )
        connection.execute("UPDATE task_segments SET progress_current = 9")
    before = service.get(task["id"])
    queries = trace_queries(database, monkeypatch)
    result = service.resume(task["id"], "user-1", task["revision"], "  合成继续  ")
    assert result["status"] == "queued"
    assert not result["pause_requested"] and not result["cancel_requested"]
    assert result["revision"] == task["revision"] + 1
    for old, new in zip(before["segments"], result["segments"], strict=True):
        if old["status"] in {"running", "cancelled"}:
            assert new["status"] == "retry_pending" and new["progress_current"] == 0
        elif old["status"] in {"queued", "retry_pending", "paused", "not_started"}:
            assert new["status"] == "queued" and new["progress_current"] == 9
        else:
            assert new == old
    assert [sql.split()[0] for sql in transaction_statements(queries)] == [
        "SELECT",
        "SELECT",
        "UPDATE",
        "UPDATE",
        "INSERT",
        "INSERT",
    ]
    event = service.events(task["id"])[-1]
    assert event["event_type"] == "resumed"
    assert event["data"]["note"] == "合成继续"


@pytest.mark.parametrize("method", ["pause", "resume"])
@pytest.mark.parametrize("case", ["missing", "stale", "status"])
def test_control_rejects_in_original_priority_without_writes(tmp_path, method, case):
    _, service, task = _runtime(tmp_path)
    args = ["missing" if case == "missing" else task["id"], "user-1"]
    args.append(task["revision"] - 1 if case == "stale" else task["revision"])
    if method == "resume":
        args.append("合成继续")
    if case == "status" and method == "pause":
        with service.database.transaction() as connection:
            connection.execute("UPDATE tasks SET status = 'completed'")
        task = service.get(task["id"])
    messages = {
        "missing": "任务不存在",
        "stale": "任务已被他人修改",
        "status": "当前任务不能暂停" if method == "pause" else "仅已暂停或已取消",
    }
    error = TaskRevisionConflict if case == "stale" else ValueError
    with pytest.raises(error, match=messages[case]):
        getattr(service, method)(*args)
    assert service.get(task["id"]) == task


@pytest.mark.parametrize("method", ["pause", "resume"])
def test_control_event_failure_rolls_back_task_segments_and_audit(tmp_path, method):
    database, service, task = _runtime(tmp_path)
    if method == "resume":
        with database.transaction() as connection:
            connection.execute("UPDATE tasks SET status = 'paused'")
    before = service.get(task["id"])
    events = service.events(task["id"])
    audit = audit_rows(database)
    fail_event_write(database)
    args = [task["id"], "user-1", task["revision"]]
    if method == "resume":
        args.append("合成继续")
    with pytest.raises(EVENT_FAILURE, match="合成回滚"):
        getattr(service, method)(*args)
    assert service.get(task["id"]) == before
    assert service.events(task["id"]) == events
    assert audit_rows(database) == audit
