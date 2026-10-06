"""根据片段运行状态计算父任务状态与进度，不执行持久化。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from web_backend.task_contracts import FINAL_STATUSES
from web_backend.task_execution.contracts import COMPLETED_SEGMENT_STATUSES
from web_backend.task_state import summarize_task_status

_MODEL_FAILURE_DISPLAY_THRESHOLD = 5


@dataclass(frozen=True)
class _ParentRefreshState:
    status: str
    stage: str
    message: str
    error: str | None
    current: int
    total: int
    percent: float
    terminal: bool
    has_deliverable: bool


def _parent_refresh_state(
    task: dict[str, Any],
    segments: list[dict[str, Any]],
    status_text: Callable[[str, int], tuple[str, str]],
) -> _ParentRefreshState:
    executable = [segment for segment in segments if segment["agent_key"] != "unknown"]
    parent_status, stage, message, parent_error = _parent_status_details(
        task, executable, status_text
    )
    current = sum(int(segment["progress_current"]) for segment in executable)
    total = sum(int(segment["progress_total"]) for segment in executable)
    percent = round(current / total * 100, 2) if total else 0
    terminal = parent_status in FINAL_STATUSES
    has_deliverable = any(
        segment["status"] in COMPLETED_SEGMENT_STATUSES for segment in executable
    )
    return _ParentRefreshState(
        status=parent_status,
        stage=stage,
        message=message,
        error=parent_error,
        current=current,
        total=total,
        percent=percent,
        terminal=terminal,
        has_deliverable=has_deliverable,
    )


def _parent_status_details(
    task: dict[str, Any],
    executable: list[dict[str, Any]],
    status_text: Callable[[str, int], tuple[str, str]],
) -> tuple[str, str, str, str | None]:
    statuses = [str(segment["status"]) for segment in executable]
    has_running = "running" in statuses
    if task["cancel_requested"] and not has_running:
        parent_status = "cancelled"
    elif task["pause_requested"] and not has_running:
        parent_status = "paused"
    else:
        parent_status = summarize_task_status(statuses)
    degraded_segment = next(
        (
            segment
            for segment in executable
            if int(segment.get("model_failures") or 0)
            >= _MODEL_FAILURE_DISPLAY_THRESHOLD
            and segment.get("error")
        ),
        None,
    )
    if degraded_segment is not None and task["pause_requested"]:
        stage = "模型服务异常"
        message = (
            "模型服务连续失败，正在保存其他运行中 Listing 的检查点"
            if has_running
            else "模型服务连续失败，任务已自动暂停；请检查连接后继续执行"
        )
        parent_error = str(degraded_segment["error"])
    else:
        stage, message = status_text(parent_status, 0)
        parent_error = None
    return parent_status, stage, message, parent_error
