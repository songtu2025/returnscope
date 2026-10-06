from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from sqlite3 import Connection, Row
from typing import Any

from web_backend.common import add_audit, json_text
from web_backend.database import Database
from web_backend.security import utc_now
from web_backend.task_contracts import FINAL_STATUSES


@dataclass(frozen=True, kw_only=True)
class _ArchiveOperation:
    """同一批归档写入共用的操作者、时间和事件信息。"""

    archived: bool
    actor_id: str
    now: str
    action: str
    event_type: str
    message: str


def _archive_rows(
    connection: Connection,
    unique_ids: list[str],
    placeholders: str,
    archived: bool,
) -> dict[str, Row]:
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

    return rows_by_id


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
            rows_by_id = _archive_rows(connection, unique_ids, placeholders, archived)
            operation = _ArchiveOperation(
                archived=archived,
                actor_id=actor_id,
                now=now,
                action="archive" if archived else "restore",
                event_type="task_archived" if archived else "task_restored",
                message="任务已归档" if archived else "任务已恢复",
            )
            for task_id in unique_ids:
                row = rows_by_id[task_id]
                was_archived = bool(row["archived_at"])
                if was_archived == archived:
                    continue
                self._write_archive_change(
                    connection, task_id, row, operation, was_archived
                )
        return [self.get(task_id) or {} for task_id in unique_ids]

    def _write_archive_change(
        self,
        connection: Connection,
        task_id: str,
        row: Row,
        operation: _ArchiveOperation,
        was_archived: bool,
    ) -> None:
        connection.execute(
            """
            UPDATE tasks
            SET archived_at = ?, archived_by = ?, revision = revision + 1
            WHERE id = ?
            """,
            (
                operation.now if operation.archived else None,
                operation.actor_id if operation.archived else None,
                task_id,
            ),
        )
        event_data = {
            "before": {"archived": was_archived},
            "after": {"archived": operation.archived},
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
                operation.event_type,
                row["stage"],
                operation.message,
                operation.actor_id,
                json_text(event_data),
                operation.now,
            ),
        )
        self._insert_audit(
            connection,
            task_id,
            operation.action,
            operation.actor_id,
            event_data["before"],
            event_data["after"],
            operation.now,
        )

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
