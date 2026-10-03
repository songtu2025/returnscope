from __future__ import annotations

from collections.abc import Callable
from typing import Any

from web_backend.common import json_text
from web_backend.database import Database
from web_backend.security import utc_now
from web_backend.task_contracts import (
    WAITING_SEGMENT_STATUSES,
    TaskRevisionConflict,
)
from web_backend.task_state import summarize_task_status
from web_backend.tasks.scheduling import TaskSchedulingMixin
from web_backend.tasks.segment_retry import TaskSegmentRetryMixin


class TaskSegmentOperationsMixin(TaskSchedulingMixin, TaskSegmentRetryMixin):
    _insert_audit: Callable[..., None]
    _status_text: Callable[..., tuple[str, str]]
    database: Database
    get: Callable[..., dict[str, Any] | None]

    def segment_action(
        self,
        task_id: str,
        segment_key: str,
        action: str,
        actor_id: str,
        expected_revision: int,
        note: str = "",
    ) -> dict[str, Any]:
        clean_note = self._validate_segment_action(action, note)
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            task, segment = self._segment_action_target(
                connection,
                task_id,
                segment_key,
                expected_revision,
            )

            before_status = str(segment["status"])
            after_status, requested_action = self._segment_action_transition(
                before_status,
                action,
            )

            connection.execute(
                """
                UPDATE task_segments
                SET status = ?, requested_action = ?,
                    completed_at = CASE WHEN ? = 'cancelled' THEN ? ELSE completed_at END,
                    revision = revision + 1
                WHERE id = ?
                """,
                (
                    after_status,
                    requested_action,
                    after_status,
                    now,
                    segment["id"],
                ),
            )
            statuses = [
                str(row["status"])
                for row in connection.execute(
                    "SELECT status FROM task_segments WHERE task_id = ?",
                    (task_id,),
                ).fetchall()
            ]
            task_status = summarize_task_status(statuses)
            stage, message = self._status_text(task_status)
            pause_requested = 0 if action == "resume" else int(task["pause_requested"])
            connection.execute(
                """
                UPDATE tasks
                SET status = ?, stage = ?, message = ?,
                    pause_requested = ?,
                    completed_at = CASE
                        WHEN ? IN ('completed', 'partial', 'cancelled', 'failed') THEN ?
                        ELSE NULL
                    END,
                    revision = revision + 1, heartbeat_at = ?
                WHERE id = ? AND revision = ?
                """,
                (
                    task_status,
                    stage,
                    message,
                    pause_requested,
                    task_status,
                    now,
                    now,
                    task_id,
                    expected_revision,
                ),
            )
            event_data = {
                "segment_key": segment_key,
                "before_status": before_status,
                "after_status": (
                    f"{action}_requested" if requested_action else after_status
                ),
                "note": clean_note,
            }
            connection.execute(
                """
                INSERT INTO task_events(
                    task_id, event_type, stage, message, actor_id,
                    data_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    f"segment_{action}",
                    stage,
                    {
                        "pause": "Listing 暂停请求已提交",
                        "resume": "Listing 已重新进入等待队列",
                        "cancel": "Listing 取消请求已提交",
                    }[action],
                    actor_id,
                    json_text(event_data),
                    now,
                ),
            )
            self._insert_audit(
                connection,
                task_id,
                f"segment_{action}",
                actor_id,
                {"segment_key": segment_key, "status": before_status},
                {
                    "segment_key": segment_key,
                    "status": event_data["after_status"],
                    "note": clean_note,
                },
                now,
            )
        return self.get(task_id) or {}

    @staticmethod
    def _validate_segment_action(action: str, note: str) -> str:
        if action not in {"pause", "resume", "cancel"}:
            raise ValueError("不支持的 Listing 操作")
        clean_note = note.strip()
        if action == "cancel" and not clean_note:
            raise ValueError("请填写取消原因")
        return clean_note

    def _segment_action_target(
        self,
        connection: Any,
        task_id: str,
        segment_key: str,
        expected_revision: int,
    ) -> tuple[Any, Any]:
        task = connection.execute(
            "SELECT revision, stage, pause_requested FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
        self._validate_task_revision(task, expected_revision)
        segment = connection.execute(
            """
            SELECT id, status, requested_action, agent_key
            FROM task_segments
            WHERE task_id = ? AND segment_key = ?
            """,
            (task_id, segment_key),
        ).fetchone()
        if segment is None:
            raise ValueError("Listing 片段不存在")
        if segment["agent_key"] == "unknown" or segment["status"] == "blocked":
            raise ValueError("未配置品类不会进入 Listing 执行队列")
        return task, segment

    @staticmethod
    def _validate_task_revision(task: Any, expected_revision: int) -> None:
        if task is None:
            raise ValueError("任务不存在")
        if int(task["revision"]) != expected_revision:
            raise TaskRevisionConflict("任务已被他人修改，请刷新后重试")

    @staticmethod
    def _segment_action_transition(
        before_status: str,
        action: str,
    ) -> tuple[str, str | None]:
        if action == "pause":
            if before_status in WAITING_SEGMENT_STATUSES:
                return "paused", None
            if before_status == "running":
                return "running", "pause"
            raise ValueError("当前状态不能暂停")
        if action == "resume":
            if before_status != "paused":
                raise ValueError("仅已暂停的 Listing 可以继续")
            return "queued", None
        if before_status == "running":
            return "running", "cancel"
        if before_status in WAITING_SEGMENT_STATUSES | {"paused", "failed"}:
            return "cancelled", None
        raise ValueError("当前状态不能取消")
