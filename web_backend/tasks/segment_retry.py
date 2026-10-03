from __future__ import annotations

from collections.abc import Callable
from typing import Any

from web_backend.classification_result_queries import system_rerun_count
from web_backend.common import json_text, json_value
from web_backend.database import Database
from web_backend.security import utc_now
from web_backend.task_contracts import (
    TaskRevisionConflict,
)


def _retry_system_failure_count(connection: Any, segment: Any) -> int:
    if (
        segment["status"] != "completed_with_errors"
        or segment["result_version_id"] is None
    ):
        return 0
    count = system_rerun_count(connection, str(segment["result_version_id"]))
    if not count:
        raise ValueError("该片段只有业务复核项，请通过复核批次生成新版本")
    return count


class TaskSegmentRetryMixin:
    _insert_audit: Callable[..., None]
    database: Database
    get: Callable[..., dict[str, Any] | None]

    def retry_segment(
        self,
        task_id: str,
        segment_key: str,
        actor_id: str,
        expected_revision: int,
        reason: str,
    ) -> dict[str, Any]:
        clean_reason = reason.strip()
        if not clean_reason:
            raise ValueError("请填写片段重试原因")
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            task = connection.execute(
                "SELECT revision, status, snapshot_json FROM tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
            if task is None:
                raise ValueError("任务不存在")
            if int(task["revision"]) != expected_revision:
                raise TaskRevisionConflict("任务已被他人修改，请刷新后重试")
            segment = connection.execute(
                """
                SELECT * FROM task_segments
                WHERE task_id = ? AND segment_key = ?
                """,
                (task_id, segment_key),
            ).fetchone()
            if segment is None:
                raise ValueError("任务片段不存在")
            if segment["agent_key"] == "unknown" or segment["status"] == "blocked":
                raise ValueError("未知品类仍未解决，不能直接重试")
            allowed = {"failed", "completed_with_errors", "not_started"}
            if segment["status"] not in allowed:
                raise ValueError("该片段当前状态不允许重试")
            system_failure_count = _retry_system_failure_count(connection, segment)
            if segment["status"] == "not_started":
                snapshot = json_value(task["snapshot_json"], {})
                policy = snapshot.get("execution_plan", {}).get(
                    "unresolved_policy",
                    "block_all",
                )
                blocked_exists = connection.execute(
                    """
                    SELECT 1 FROM task_segments
                    WHERE task_id = ? AND status = 'blocked' LIMIT 1
                    """,
                    (task_id,),
                ).fetchone()
                if policy == "block_all" and blocked_exists is not None:
                    raise ValueError("当前策略仍阻断全部片段，请先重新规划")
            connection.execute(
                """
                UPDATE task_segments
                SET status = 'retry_pending', progress_current = 0,
                    error = NULL, requested_action = NULL,
                    started_at = NULL, completed_at = NULL,
                    retry_count = retry_count + 1, revision = revision + 1
                WHERE id = ?
                """,
                (segment["id"],),
            )
            connection.execute(
                """
                UPDATE tasks
                SET status = CASE WHEN status = 'running' THEN status ELSE 'queued' END,
                    stage = '等待重试',
                    message = '任务片段已重新排队', error = NULL,
                    cancel_requested = 0, pause_requested = 0,
                    completed_at = NULL, revision = revision + 1,
                    heartbeat_at = ?
                WHERE id = ? AND revision = ?
                """,
                (now, task_id, expected_revision),
            )
            event_data = {
                "segment_key": segment_key,
                "agent_key": segment["agent_key"],
                "before_status": segment["status"],
                "after_status": "retry_pending",
                "reason": clean_reason,
                "retry_scope": (
                    "system_failures_only" if system_failure_count else "full_segment"
                ),
                "system_rerun_count": system_failure_count,
            }
            connection.execute(
                """
                INSERT INTO task_events(
                    task_id, event_type, stage, message, actor_id,
                    data_json, created_at
                ) VALUES (?, 'segment_retry', '等待重试',
                          '任务片段已重新排队', ?, ?, ?)
                """,
                (task_id, actor_id, json_text(event_data), now),
            )
            self._insert_audit(
                connection,
                task_id,
                "segment_retry",
                actor_id,
                {
                    "segment_key": segment_key,
                    "status": segment["status"],
                },
                {
                    "segment_key": segment_key,
                    "status": "retry_pending",
                    "reason": clean_reason,
                    "retry_scope": event_data["retry_scope"],
                    "system_rerun_count": system_failure_count,
                },
                now,
            )
        return self.get(task_id) or {}
