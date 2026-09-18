from __future__ import annotations

from collections.abc import Callable
from typing import Any

from web_backend.common import add_audit, json_text
from web_backend.database import Database
from web_backend.security import utc_now
from web_backend.task_contracts import FINAL_STATUSES, TaskRevisionConflict


class TaskLifecycleMixin:
    database: Database
    get: Callable[..., dict[str, Any] | None]
    create: Callable[..., dict[str, Any]]
    _insert_audit: Callable[..., None]

    def set_archived(
        self,
        task_ids: list[str],
        archived: bool,
        actor_id: str,
    ) -> list[dict[str, Any]]:
        unique_ids = list(dict.fromkeys(task_ids))
        if not unique_ids:
            raise ValueError("请选择任务")
        placeholders = ",".join("?" for _ in unique_ids)
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            rows = connection.execute(
                f"""
                SELECT id, status, stage, archived_at
                FROM tasks
                WHERE id IN ({placeholders})
                """,
                tuple(unique_ids),
            ).fetchall()
            rows_by_id = {str(row["id"]): row for row in rows}
            missing = [task_id for task_id in unique_ids if task_id not in rows_by_id]
            if missing:
                raise ValueError("部分任务不存在")
            if archived:
                invalid = [
                    task_id
                    for task_id in unique_ids
                    if rows_by_id[task_id]["status"] not in FINAL_STATUSES
                ]
                if invalid:
                    raise ValueError("仅已结束任务可以归档")

            action = "archive" if archived else "restore"
            event_type = "task_archived" if archived else "task_restored"
            message = "任务已归档" if archived else "任务已恢复"
            for task_id in unique_ids:
                row = rows_by_id[task_id]
                was_archived = bool(row["archived_at"])
                if was_archived == archived:
                    continue
                connection.execute(
                    """
                    UPDATE tasks
                    SET archived_at = ?, archived_by = ?, revision = revision + 1
                    WHERE id = ?
                    """,
                    (
                        now if archived else None,
                        actor_id if archived else None,
                        task_id,
                    ),
                )
                event_data = {
                    "before": {"archived": was_archived},
                    "after": {"archived": archived},
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
                        event_type,
                        row["stage"],
                        message,
                        actor_id,
                        json_text(event_data),
                        now,
                    ),
                )
                self._insert_audit(
                    connection,
                    task_id,
                    action,
                    actor_id,
                    event_data["before"],
                    event_data["after"],
                    now,
                )
        return [self.get(task_id) or {} for task_id in unique_ids]

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

    def retry(self, task_id: str, actor_id: str) -> dict[str, Any]:
        source = self.get(task_id)
        if source is None:
            raise ValueError("任务不存在")
        if source["status"] == "partial":
            raise ValueError("部分完成任务请使用片段重试或重新规划")
        if source["status"] not in FINAL_STATUSES:
            raise ValueError("任务结束后才能再次运行")
        suffix = "（重试）" if source["status"] != "completed" else "（再次运行）"
        result = self.create(
            actor_id=actor_id,
            title=f"{source['title']}{suffix}"[:120],
            dataset_version_id=str(source["dataset_version_id"]),
            product_version_id=str(source["product_version_id"]),
            config_version_id=str(source["config_version_id"]),
            store=str(source["store"]),
            listing=source["listing"],
            unresolved_policy=(
                source["snapshot"]
                .get("execution_plan", {})
                .get("unresolved_policy", "block_all")
            ),
            segment_order=(
                [str(segment["segment_key"]) for segment in source["segments"]]
                if source["segments"]
                else None
            ),
            max_parallel_segments=int(source.get("max_parallel_segments", 3)),
        )
        add_audit(
            self.database,
            "task",
            task_id,
            "retry",
            actor_id,
            after={"new_task_id": result["id"]},
        )
        return result

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
