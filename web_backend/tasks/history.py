from __future__ import annotations

from collections.abc import Callable
from typing import Any

from web_backend.common import add_audit, json_text
from web_backend.database import Database
from web_backend.security import utc_now
from web_backend.task_contracts import FINAL_STATUSES


class TaskHistoryMixin:
    _insert_audit: Callable[..., None]
    create: Callable[..., dict[str, Any]]
    database: Database
    get: Callable[..., dict[str, Any] | None]

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
