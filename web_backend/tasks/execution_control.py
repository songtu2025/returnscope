from __future__ import annotations

from collections.abc import Callable
from typing import Any

from web_backend.common import json_text
from web_backend.database import Database
from web_backend.security import utc_now
from web_backend.task_contracts import TaskRevisionConflict


class TaskExecutionControlMixin:
    _insert_audit: Callable[..., None]
    database: Database
    get: Callable[..., dict[str, Any] | None]

    def pause(
        self,
        task_id: str,
        actor_id: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            task = connection.execute(
                "SELECT status, stage, revision FROM tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
            if task is None:
                raise ValueError("任务不存在")
            if int(task["revision"]) != expected_revision:
                raise TaskRevisionConflict("任务已被他人修改，请刷新后重试")
            if task["status"] not in {"queued", "running"}:
                raise ValueError("当前任务不能暂停")
            connection.execute(
                """
                UPDATE task_segments
                SET status = 'paused', requested_action = NULL,
                    revision = revision + 1
                WHERE task_id = ? AND status IN ('queued', 'retry_pending')
                """,
                (task_id,),
            )
            running_count = connection.execute(
                """
                UPDATE task_segments
                SET requested_action = 'pause', revision = revision + 1
                WHERE task_id = ? AND status = 'running'
                """,
                (task_id,),
            ).rowcount
            status = "running" if running_count else "paused"
            stage = "正在暂停" if running_count else "已暂停"
            connection.execute(
                """
                UPDATE tasks
                SET pause_requested = 1, status = ?, stage = ?,
                    message = '等待运行中的 Listing 保存检查点',
                    revision = revision + 1, heartbeat_at = ?
                WHERE id = ? AND revision = ?
                """,
                (status, stage, now, task_id, expected_revision),
            )
            event_data: dict[str, Any] = {
                "before": {"status": task["status"], "stage": task["stage"]},
                "after": {"status": status, "stage": stage},
            }
            connection.execute(
                """
                INSERT INTO task_events(
                    task_id, event_type, stage, message, actor_id,
                    data_json, created_at
                ) VALUES (?, 'pause', ?, '用户暂停全部未完成 Listing', ?, ?, ?)
                """,
                (task_id, stage, actor_id, json_text(event_data), now),
            )
            self._insert_audit(
                connection,
                task_id,
                "pause",
                actor_id,
                event_data["before"],
                event_data["after"],
                now,
            )
        return self.get(task_id) or {}

    def resume(
        self,
        task_id: str,
        actor_id: str,
        expected_revision: int,
        note: str,
    ) -> dict[str, Any]:
        clean_note = note.strip()
        if not clean_note:
            raise ValueError("请填写继续执行原因")
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            task = connection.execute(
                "SELECT status, stage, revision FROM tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
            if task is None:
                raise ValueError("任务不存在")
            if int(task["revision"]) != expected_revision:
                raise TaskRevisionConflict("任务已被他人修改，请刷新后重试")
            if task["status"] not in {"paused", "cancelled"}:
                raise ValueError("仅已暂停或已取消任务可以继续执行")
            source_status = str(task["status"])
            resumable = connection.execute(
                """
                SELECT COUNT(*) AS count FROM task_segments
                WHERE task_id = ?
                  AND status IN (
                      'cancelled', 'not_started', 'running',
                      'queued', 'retry_pending', 'paused'
                  )
                """,
                (task_id,),
            ).fetchone()
            if resumable is None or int(resumable["count"]) == 0:
                raise ValueError("当前任务没有未完成片段")
            connection.execute(
                """
                UPDATE task_segments
                SET status = CASE
                        WHEN status IN ('cancelled', 'running') THEN 'retry_pending'
                        ELSE 'queued'
                    END,
                    progress_current = CASE
                        WHEN status IN ('cancelled', 'running') THEN 0
                        ELSE progress_current
                    END,
                    error = NULL, requested_action = NULL,
                    started_at = NULL, completed_at = NULL,
                    revision = revision + 1
                WHERE task_id = ?
                  AND status IN (
                      'cancelled', 'not_started', 'running',
                      'queued', 'retry_pending', 'paused'
                  )
                """,
                (task_id,),
            )
            connection.execute(
                """
                UPDATE tasks
                SET status = 'queued', stage = '等待继续执行',
                    message = '未完成片段已重新排队', error = NULL,
                    cancel_requested = 0, pause_requested = 0, completed_at = NULL,
                    revision = revision + 1, heartbeat_at = ?
                WHERE id = ? AND revision = ?
                """,
                (now, task_id, expected_revision),
            )
            event_data: dict[str, Any] = {
                "before": {"status": source_status, "stage": task["stage"]},
                "after": {"status": "queued", "stage": "等待继续执行"},
                "note": clean_note,
            }
            connection.execute(
                """
                INSERT INTO task_events(
                    task_id, event_type, stage, message, actor_id,
                    data_json, created_at
                ) VALUES (?, 'resumed', '等待继续执行',
                          '用户继续执行未完成片段', ?, ?, ?)
                """,
                (task_id, actor_id, json_text(event_data), now),
            )
            self._insert_audit(
                connection,
                task_id,
                "resume",
                actor_id,
                event_data["before"],
                event_data["after"] | {"note": clean_note},
                now,
            )
        return self.get(task_id) or {}
