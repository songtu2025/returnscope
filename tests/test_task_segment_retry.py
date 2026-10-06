import pytest
from task_execution_helpers import (
    EVENT_FAILURE,
    audit_rows,
    fail_event_write,
    segment_rows,
    trace_queries,
    transaction_statements,
)
from test_task_detail_queries import _add_segment
from test_task_scheduling import _runtime

from web_backend.common import json_text
from web_backend.task_service import TaskRevisionConflict


@pytest.mark.parametrize("status", ["failed", "completed_with_errors", "not_started"])
@pytest.mark.parametrize("parent_status", ["running", "paused"])
def test_retry_preserves_scope_history_and_transaction_budget(
    tmp_path, monkeypatch, status, parent_status
):
    database, service, task = _runtime(tmp_path)
    target = next(
        segment for segment in task["segments"] if segment["status"] == "queued"
    )
    with database.transaction() as connection:
        connection.execute("UPDATE tasks SET status = ?", (parent_status,))
        connection.execute(
            "UPDATE task_segments SET status = ? WHERE id = ?", (status, target["id"])
        )
    before = service.get(task["id"])
    stored_before = segment_rows(database, task["id"])
    queries = trace_queries(database, monkeypatch)
    result = service.retry_segment(
        task["id"], target["segment_key"], "user-1", task["revision"], "  合成重试  "
    )
    assert result["status"] == ("running" if parent_status == "running" else "queued")
    assert result["revision"] == task["revision"] + 1
    stored_after = segment_rows(database, task["id"])
    for old, new in zip(before["segments"], result["segments"], strict=True):
        if old["id"] != target["id"]:
            assert stored_after[old["id"]] == stored_before[old["id"]]
        else:
            assert new["status"] == "retry_pending"
            assert new["retry_count"] == old["retry_count"] + 1
            assert new["progress_current"] == 0
    statements = transaction_statements(queries)
    assert [sql.split()[0] for sql in statements] == (
        ["SELECT"] * (3 if status == "not_started" else 2)
        + ["UPDATE", "UPDATE", "INSERT", "INSERT"]
    )
    data = service.events(task["id"])[-1]["data"]
    assert data["reason"] == "合成重试"
    assert data["retry_scope"] == "full_segment" and data["system_rerun_count"] == 0


@pytest.mark.parametrize("policy", [None, "block_all", "run_ready"])
@pytest.mark.parametrize("blocked", [False, True])
def test_unstarted_retry_preserves_unresolved_policy(tmp_path, policy, blocked):
    database, service, task = _runtime(tmp_path)
    target = next(
        segment for segment in task["segments"] if segment["status"] == "queued"
    )
    if blocked:
        _add_segment(database, target["id"], "synthetic-blocked", "blocked")
    with database.transaction() as connection:
        snapshot = (
            {} if policy is None else {"execution_plan": {"unresolved_policy": policy}}
        )
        connection.execute("UPDATE tasks SET snapshot_json = ?", (json_text(snapshot),))
        connection.execute(
            "UPDATE task_segments SET status = 'not_started' WHERE id = ?",
            (target["id"],),
        )
        if not blocked:
            connection.execute(
                "UPDATE task_segments SET status = 'failed' WHERE status = 'blocked'"
            )
    before = service.get(task["id"])
    args = (task["id"], target["segment_key"], "user-1", task["revision"], "合成重试")
    if blocked and policy in {None, "block_all"}:
        with pytest.raises(ValueError, match="当前策略仍阻断全部片段"):
            service.retry_segment(*args)
        assert service.get(task["id"]) == before
    else:
        result = service.retry_segment(*args)
        assert (
            next(item for item in result["segments"] if item["id"] == target["id"])[
                "status"
            ]
            == "retry_pending"
        )


@pytest.mark.parametrize(
    "case", ["blank", "missing", "stale", "segment", "unknown", "status"]
)
def test_retry_rejection_priority_has_no_writes(tmp_path, case):
    database, service, task = _runtime(tmp_path)
    target = next(
        segment for segment in task["segments"] if segment["status"] == "queued"
    )
    if case == "unknown":
        with database.transaction() as connection:
            connection.execute(
                "UPDATE task_segments SET agent_key = 'unknown' WHERE id = ?",
                (target["id"],),
            )
    before = service.get(task["id"])
    messages = {
        "blank": "请填写片段重试原因",
        "missing": "任务不存在",
        "stale": "任务已被他人修改",
        "segment": "任务片段不存在",
        "unknown": "未知品类仍未解决",
        "status": "该片段当前状态不允许重试",
    }
    error = TaskRevisionConflict if case == "stale" else ValueError
    with pytest.raises(error, match=messages[case]):
        service.retry_segment(
            "missing" if case in {"blank", "missing"} else task["id"],
            "missing" if case in {"stale", "segment"} else target["segment_key"],
            "user-1",
            task["revision"] - 1 if case == "stale" else task["revision"],
            " " if case == "blank" else "合成重试",
        )
    assert service.get(task["id"]) == before


def test_retry_event_failure_rolls_back_revision_retry_count_and_audit(tmp_path):
    database, service, task = _runtime(tmp_path)
    target = next(
        segment for segment in task["segments"] if segment["status"] == "failed"
    )
    events = service.events(task["id"])
    audit = audit_rows(database)
    fail_event_write(database)
    with pytest.raises(EVENT_FAILURE, match="合成回滚"):
        service.retry_segment(
            task["id"], target["segment_key"], "user-1", task["revision"], "合成重试"
        )
    assert service.get(task["id"]) == task
    assert service.events(task["id"]) == events
    assert audit_rows(database) == audit
