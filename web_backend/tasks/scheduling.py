from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from sqlite3 import Connection, Row
from typing import Any

from web_backend.common import json_text
from web_backend.database import Database
from web_backend.security import utc_now
from web_backend.task_contracts import (
    ACTIVE_STATUSES,
    SEGMENT_USER_LIMIT,
    WAITING_SEGMENT_STATUSES,
    TaskRevisionConflict,
)

_MOVABLE_SEGMENT_STATUSES = WAITING_SEGMENT_STATUSES | {"paused"}


@dataclass(frozen=True)
class _SegmentOrderChange:
    before: list[str]
    after: list[str]
    rows: list[Row]
    created_at: str


def _segment_reorder(
    rows: list[Row], segment_keys: list[str], now: str
) -> _SegmentOrderChange | None:
    movable_keys = [
        str(row["segment_key"])
        for row in rows
        if row["status"] in _MOVABLE_SEGMENT_STATUSES
    ]
    if len(segment_keys) != len(set(segment_keys)) or set(segment_keys) != set(
        movable_keys
    ):
        raise TaskRevisionConflict("等待片段已经变化，请刷新后重新排序")
    if segment_keys == movable_keys:
        return None

    history_rows = [
        row
        for row in rows
        if row["status"] not in _MOVABLE_SEGMENT_STATUSES and row["status"] != "blocked"
    ]
    movable_by_key = {
        str(row["segment_key"]): row
        for row in rows
        if row["status"] in _MOVABLE_SEGMENT_STATUSES
    }
    blocked_rows = [row for row in rows if row["status"] == "blocked"]
    ordered_rows = (
        history_rows
        + [movable_by_key[segment_key] for segment_key in segment_keys]
        + blocked_rows
    )
    return _SegmentOrderChange(movable_keys, segment_keys, ordered_rows, now)


class TaskSchedulingMixin:
    _insert_audit: Callable[..., None]
    database: Database
    get: Callable[..., dict[str, Any] | None]

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
            change = _segment_reorder(rows, segment_keys, now)
            if change is None:
                return self.get(task_id) or {}
            self._apply_segment_order(connection, task, task_id, actor_id, change)
        return self.get(task_id) or {}

    def _apply_segment_order(
        self,
        connection: Connection,
        task: Row,
        task_id: str,
        actor_id: str,
        change: _SegmentOrderChange,
    ) -> None:
        now = change.created_at
        for position, row in enumerate(change.rows, start=1):
            connection.execute(
                "UPDATE task_segments SET execution_order = ? WHERE id = ?",
                (position, row["id"]),
            )
        connection.execute(
            "UPDATE tasks SET revision = revision + 1 WHERE id = ?",
            (task_id,),
        )
        event_data = {"before": change.before, "after": change.after}
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
            {"segment_order": change.before},
            {"segment_order": change.after},
            now,
        )

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
