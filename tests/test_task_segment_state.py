import sqlite3

import pytest
from test_agent_runner_segment_outcomes import _state
from test_agent_runner_segment_outcomes import runtime as runtime

from web_backend.common import json_value


@pytest.mark.parametrize("status", ["running", "paused"])
@pytest.mark.parametrize("agent_key", ["footwear", "unknown"])
def test_progress_preserves_running_guard_unknown_scope_and_event(
    runtime, status, agent_key
):
    with runtime.seed.database.transaction() as connection:
        connection.execute(
            "UPDATE task_segments SET status = ?, agent_key = ? WHERE id = ?",
            (status, agent_key, runtime.seed.segment_id),
        )
    before = runtime.runner._load_segment(runtime.seed.segment_id)
    runtime.runner._update_segment_progress(
        runtime.seed.task_id, runtime.seed.segment_id, 4, 8
    )
    state = _state(runtime)
    segment = state["segments"][runtime.seed.segment_id]
    expected = (
        (4, 8)
        if status == "running"
        else (before["progress_current"], before["progress_total"])
    )
    assert (segment["progress_current"], segment["progress_total"]) == expected
    aggregate = (0, 0) if agent_key == "unknown" else expected
    assert (
        state["task"]["progress_current"],
        state["task"]["progress_total"],
    ) == aggregate
    assert state["task"]["progress_percent"] == (
        50 if status == "running" and agent_key != "unknown" else 0
    )
    event = state["events"][-1]
    assert event["event_type"] == "segment_progress"
    assert event["message"] == "Listing 已完成 4/8 组评论"
    assert json_value(event["data_json"], {}) == {"segment_id": runtime.seed.segment_id}


@pytest.mark.parametrize("status", ["running", "paused"])
def test_runtime_counters_are_monotonic_only_when_running(runtime, status):
    with runtime.seed.database.transaction() as connection:
        connection.execute(
            "UPDATE task_segments SET status = ? WHERE id = ?",
            (status, runtime.seed.segment_id),
        )
    runtime.runner._update_segment_runtime_metrics(runtime.seed.segment_id, 1, 8, 4)
    segment = runtime.runner._load_segment(runtime.seed.segment_id)
    assert tuple(
        segment[key] for key in ("model_calls", "cache_hits", "model_failures")
    ) == ((3, 8, 7) if status == "running" else (3, 5, 7))


@pytest.mark.parametrize("status", ["running", "paused"])
@pytest.mark.parametrize("count", [3, 4, 5])
def test_degraded_event_preserves_threshold_message_truncation_and_revisions(
    runtime, status, count
):
    with runtime.seed.database.transaction() as connection:
        connection.execute(
            "UPDATE task_segments SET status = ? WHERE id = ?",
            (status, runtime.seed.segment_id),
        )
    before = _state(runtime)
    error = "合成服务异常" * 150
    runtime.runner._record_model_degraded(
        runtime.seed.task_id, runtime.seed.segment_id, error, count
    )
    after = _state(runtime)
    segment = after["segments"][runtime.seed.segment_id]
    event = after["events"][-1]
    message = f"模型服务已连续失败 {count} 次，正在重试；达到 5 次将自动暂停"
    assert after["task"]["message"] == event["message"] == message
    assert after["task"]["revision"] == before["task"]["revision"] + 1
    assert segment["revision"] == before["segments"][runtime.seed.segment_id][
        "revision"
    ] + (status == "running")
    assert json_value(event["data_json"], {}) == {
        "segment_id": runtime.seed.segment_id,
        "consecutive_failures": count,
        "error": error[:500],
    }


@pytest.mark.parametrize("operation", ["progress", "degraded"])
def test_event_failure_rolls_back_progress_and_degradation(runtime, operation):
    with runtime.seed.database.transaction() as connection:
        connection.execute(
            "CREATE TRIGGER reject_state_event BEFORE INSERT ON task_events BEGIN SELECT RAISE(ABORT, '合成事件失败'); END"
        )
    before = _state(runtime)
    with pytest.raises(sqlite3.IntegrityError, match="合成事件失败"):
        if operation == "progress":
            runtime.runner._update_segment_progress(
                runtime.seed.task_id, runtime.seed.segment_id, 4, 8
            )
        else:
            runtime.runner._record_model_degraded(
                runtime.seed.task_id, runtime.seed.segment_id, "合成失败", 3
            )
    assert _state(runtime) == before
