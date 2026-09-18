from __future__ import annotations

from collections.abc import Callable
from typing import Any

from web_backend.classification_result_queries import system_rerun_count
from web_backend.common import json_text, json_value
from web_backend.database import Database
from web_backend.security import utc_now
from web_backend.task_contracts import (
    ACTIVE_STATUSES,
    SEGMENT_USER_LIMIT,
    WAITING_SEGMENT_STATUSES,
    TaskRevisionConflict,
)
from web_backend.task_state import summarize_task_status


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


class TaskSegmentOperationsMixin:
    database: Database
    get: Callable[..., dict[str, Any] | None]
    _insert_audit: Callable[..., None]
    _status_text: Callable[..., tuple[str, str]]

    def reorder_segments(
        self,
        task_id: str,
        actor_id: str,
        expected_revision: int,
        segment_keys: list[str],
    ) -> dict[str, Any]:
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            task = connection.execute(
                "SELECT revision, status, stage FROM tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
            if task is None:
                raise ValueError("任务不存在")
            if int(task["revision"]) != expected_revision:
                raise TaskRevisionConflict("任务已被他人修改，请刷新后重试")
            if task["status"] not in ACTIVE_STATUSES:
                raise ValueError("仅排队中或运行中的任务可以调整片段顺序")

            rows = connection.execute(
                """
                SELECT id, segment_key, status, execution_order
                FROM task_segments
                WHERE task_id = ?
                ORDER BY execution_order, segment_key
                """,
                (task_id,),
            ).fetchall()
            movable_statuses = {"queued", "retry_pending", "paused"}
            movable_keys = [
                str(row["segment_key"])
                for row in rows
                if row["status"] in movable_statuses
            ]
            if len(segment_keys) != len(set(segment_keys)) or set(segment_keys) != set(
                movable_keys
            ):
                raise TaskRevisionConflict("等待片段已经变化，请刷新后重新排序")
            if segment_keys == movable_keys:
                return self.get(task_id) or {}

            history_rows = [
                row
                for row in rows
                if row["status"] not in movable_statuses and row["status"] != "blocked"
            ]
            movable_by_key = {
                str(row["segment_key"]): row
                for row in rows
                if row["status"] in movable_statuses
            }
            blocked_rows = [row for row in rows if row["status"] == "blocked"]
            ordered_rows = (
                history_rows
                + [movable_by_key[segment_key] for segment_key in segment_keys]
                + blocked_rows
            )
            for position, row in enumerate(ordered_rows, start=1):
                connection.execute(
                    "UPDATE task_segments SET execution_order = ? WHERE id = ?",
                    (position, row["id"]),
                )
            connection.execute(
                "UPDATE tasks SET revision = revision + 1 WHERE id = ?",
                (task_id,),
            )
            event_data = {"before": movable_keys, "after": segment_keys}
            connection.execute(
                """
                INSERT INTO task_events(
                    task_id, event_type, stage, message, actor_id,
                    data_json, created_at
                ) VALUES (?, 'segments_reordered', ?, '用户调整了片段执行顺序', ?, ?, ?)
                """,
                (
                    task_id,
                    task["stage"],
                    actor_id,
                    json_text(event_data),
                    now,
                ),
            )
            self._insert_audit(
                connection,
                task_id,
                "reorder_segments",
                actor_id,
                {"segment_order": movable_keys},
                {"segment_order": segment_keys},
                now,
            )
        return self.get(task_id) or {}

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

    def set_parallelism(
        self,
        task_id: str,
        actor_id: str,
        expected_revision: int,
        max_parallel_segments: int,
    ) -> dict[str, Any]:
        if not 1 <= max_parallel_segments <= SEGMENT_USER_LIMIT:
            raise ValueError("Listing 并行数必须在 1 到 3 之间")
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            task = connection.execute(
                """
                SELECT revision, status, max_parallel_segments, stage
                FROM tasks WHERE id = ?
                """,
                (task_id,),
            ).fetchone()
            if task is None:
                raise ValueError("任务不存在")
            if int(task["revision"]) != expected_revision:
                raise TaskRevisionConflict("任务已被他人修改，请刷新后重试")
            if task["status"] not in ACTIVE_STATUSES:
                raise ValueError("仅排队中、运行中或已暂停的任务可以调整并行数")
            before_value = int(task["max_parallel_segments"])
            if before_value == max_parallel_segments:
                return self.get(task_id) or {}
            connection.execute(
                """
                UPDATE tasks
                SET max_parallel_segments = ?, revision = revision + 1
                WHERE id = ? AND revision = ?
                """,
                (max_parallel_segments, task_id, expected_revision),
            )
            event_data = {
                "before": {"max_parallel_segments": before_value},
                "after": {"max_parallel_segments": max_parallel_segments},
            }
            connection.execute(
                """
                INSERT INTO task_events(
                    task_id, event_type, stage, message, actor_id,
                    data_json, created_at
                ) VALUES (?, 'parallelism_changed', ?, 'Listing 并行数已调整', ?, ?, ?)
                """,
                (
                    task_id,
                    task["stage"],
                    actor_id,
                    json_text(event_data),
                    now,
                ),
            )
            self._insert_audit(
                connection,
                task_id,
                "parallelism_changed",
                actor_id,
                event_data["before"],
                event_data["after"],
                now,
            )
        return self.get(task_id) or {}

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
