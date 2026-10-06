from unittest.mock import Mock

import pytest

from web_backend.task_execution.parent_refresh_state import _parent_refresh_state


def _segment(status, **changes):
    return {
        "agent_key": "footwear",
        "status": status,
        "progress_current": 3,
        "progress_total": 4,
        "model_failures": 0,
        "error": None,
        **changes,
    }


@pytest.mark.parametrize(
    "statuses, expected",
    [
        ([], ("blocked", True, False)),
        (["completed"], ("completed", True, True)),
        (["completed_with_errors"], ("partial", True, True)),
        (["completed", "queued"], ("queued", False, True)),
        (["cancelled"], ("cancelled", True, False)),
        (["failed"], ("blocked", True, False)),
        (["paused"], ("paused", False, False)),
        (["running"], ("running", False, False)),
    ],
)
def test_parent_progress_terminal_and_deliverable_exclude_unknown(statuses, expected):
    segments = [_segment(status) for status in statuses]
    segments.append(
        _segment(
            "completed", agent_key="unknown", progress_current=999, progress_total=1000
        )
    )
    callback = Mock(return_value=("状态阶段", "状态提示"))
    result = _parent_refresh_state(
        {"cancel_requested": False, "pause_requested": False}, segments, callback
    )
    assert (result.status, result.terminal, result.has_deliverable) == expected
    assert (result.current, result.total, result.percent) == (
        3 * len(statuses),
        4 * len(statuses),
        75.0 if statuses else 0,
    )
    callback.assert_called_once_with(expected[0], 0)


@pytest.mark.parametrize(
    "flags, status, expected",
    [
        ((1, 1), "queued", "cancelled"),
        ((0, 1), "queued", "paused"),
        ((1, 1), "running", "running"),
        ((1, 0), "running", "running"),
    ],
)
def test_parent_cancel_pause_priority_keeps_running_segments(flags, status, expected):
    task = {"cancel_requested": flags[0], "pause_requested": flags[1]}
    result = _parent_refresh_state(
        task, [_segment(status)], lambda *_: ("阶段", "提示")
    )
    assert result.status == expected


@pytest.mark.parametrize("failures", [4, 5, 6])
@pytest.mark.parametrize("running", [False, True])
def test_parent_model_failure_display_boundary(failures, running):
    callback = Mock(return_value=("普通阶段", "普通提示"))
    segments = [_segment("paused", model_failures=failures, error="合成失败")]
    if running:
        segments.append(_segment("running"))
    result = _parent_refresh_state(
        {"cancel_requested": False, "pause_requested": True}, segments, callback
    )
    if failures < 5:
        assert result.error is None and result.stage == "普通阶段"
        callback.assert_called_once()
    else:
        assert result.error == "合成失败" and result.stage == "模型服务异常"
        assert result.message == (
            "模型服务连续失败，正在保存其他运行中 Listing 的检查点"
            if running
            else "模型服务连续失败，任务已自动暂停；请检查连接后继续执行"
        )
        callback.assert_not_called()
