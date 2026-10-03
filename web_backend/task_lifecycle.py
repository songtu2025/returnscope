from __future__ import annotations

from collections.abc import Callable
from typing import Any

from web_backend.common import add_audit, json_text
from web_backend.database import Database
from web_backend.security import utc_now
from web_backend.task_contracts import FINAL_STATUSES, TaskRevisionConflict
from web_backend.tasks.execution_control import TaskExecutionControlMixin
from web_backend.tasks.history import TaskHistoryMixin


class TaskLifecycleMixin(TaskHistoryMixin, TaskExecutionControlMixin):
    database: Database
    get: Callable[..., dict[str, Any] | None]

    def cancel(
        self,
        task_id: str,
        actor_id: str,
        note: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        clean_note = note.strip()
        if not clean_note:
            raise ValueError("请填写取消原因")
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute(
                "SELECT status, stage, revision FROM tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
            if row is None:
                raise ValueError("任务不存在")
            if int(row["revision"]) != expected_revision:
                raise TaskRevisionConflict("任务已被他人修改，请刷新后重试")
            if row["status"] in FINAL_STATUSES:
                raise ValueError("任务已经结束")
            now = utc_now()
            connection.execute(
                """
                UPDATE task_segments
                SET status = 'cancelled', requested_action = NULL,
                    completed_at = ?, revision = revision + 1
                WHERE task_id = ?
                  AND status IN ('queued', 'retry_pending', 'paused',
                                 'failed', 'not_started')
                """,
                (now, task_id),
            )
            running_count = connection.execute(
                """
                UPDATE task_segments
                SET requested_action = 'cancel', revision = revision + 1
                WHERE task_id = ? AND status = 'running'
                """,
                (task_id,),
            ).rowcount
            status = "running" if running_count else "cancelled"
            stage = "正在取消" if running_count else "已取消"
            completed_at = None if running_count else now
            connection.execute(
                """
                UPDATE tasks
                SET cancel_requested = 1, pause_requested = 0,
                    status = ?, stage = ?, message = '正在取消未完成 Listing',
                    completed_at = COALESCE(?, completed_at), revision = revision + 1
                WHERE id = ?
                """,
                (status, stage, completed_at, task_id),
            )
            connection.execute(
                """
                INSERT INTO task_events(
                    task_id, event_type, stage, message, actor_id,
                    data_json, created_at
                ) VALUES (?, 'cancel', ?, '用户请求取消任务', ?, ?, ?)
                """,
                (
                    task_id,
                    stage,
                    actor_id,
                    json_text(
                        {
                            "before": {
                                "status": row["status"],
                                "stage": row["stage"],
                            },
                            "after": {"status": status, "stage": stage},
                            "note": clean_note,
                        }
                    ),
                    now,
                ),
            )
        add_audit(
            self.database,
            "task",
            task_id,
            "cancel",
            actor_id,
            before={"status": row["status"], "stage": row["stage"]},
            after={"status": status, "stage": stage, "note": clean_note},
        )
        return self.get(task_id) or {}

    def rename(
        self,
        task_id: str,
        title: str,
        note: str,
        expected_revision: int,
        actor_id: str,
    ) -> dict[str, Any]:
        clean_title = title.strip()
        if not clean_title:
            raise ValueError("任务名称不能为空")
        clean_note = note.strip()
        if not clean_note:
            raise ValueError("请填写修改原因")
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute(
                "SELECT title, revision, stage FROM tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
            if row is None:
                raise ValueError("任务不存在")
            if int(row["revision"]) != expected_revision:
                raise TaskRevisionConflict("任务已被其他用户修改，请刷新后重试")
            before = {"title": str(row["title"]), "revision": expected_revision}
            new_revision = expected_revision + 1
            now = utc_now()
            connection.execute(
                """
                UPDATE tasks SET title = ?, revision = ? WHERE id = ?
                """,
                (clean_title, new_revision, task_id),
            )
            connection.execute(
                """
                INSERT INTO task_events(
                    task_id, event_type, stage, message, actor_id,
                    data_json, created_at
                ) VALUES (?, 'updated', ?, '任务名称已修改', ?, ?, ?)
                """,
                (
                    task_id,
                    row["stage"],
                    actor_id,
                    json_text(
                        {
                            "before": before,
                            "after": {
                                "title": clean_title,
                                "revision": new_revision,
                            },
                            "note": clean_note,
                        }
                    ),
                    now,
                ),
            )
        add_audit(
            self.database,
            "task",
            task_id,
            "rename",
            actor_id,
            before=before,
            after={
                "title": clean_title,
                "revision": new_revision,
                "note": clean_note,
            },
        )
        return self.get(task_id) or {}
