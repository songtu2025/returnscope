from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from sqlite3 import Connection
from typing import TYPE_CHECKING, Any

from web_backend.classification_result_queries import system_rerun_counts
from web_backend.database import Database
from web_backend.task_contracts import SEGMENT_USER_LIMIT, WAITING_SEGMENT_STATUSES

_DEFAULT_TASK_PARALLELISM = 3
_PAUSED_MODEL_FAILURE_DISPLAY_THRESHOLD = 3

_TASK_DETAIL_SQL = """
                SELECT t.*, u.display_name AS owner_name,
                       rd.name AS dataset_name, rv.version AS dataset_version,
                       pd.name AS product_name, pv.version AS product_version,
                       c.name AS connection_name, cv.version AS config_version,
                       cv.primary_model, cv.primary_effort,
                       cv.cheap_model, cv.secondary_model,
                       CASE WHEN t.status = 'queued' THEN (
                           SELECT COUNT(*) + 1 FROM tasks q
                           WHERE q.status = 'queued'
                             AND q.created_at < t.created_at
                       ) END AS queue_position
                FROM tasks t
                JOIN users u ON u.id = t.owner_id
                JOIN dataset_versions rv ON rv.id = t.dataset_version_id
                JOIN datasets rd ON rd.id = rv.dataset_id
                JOIN dataset_versions pv ON pv.id = t.product_version_id
                JOIN datasets pd ON pd.id = pv.dataset_id
                JOIN api_config_versions cv ON cv.id = t.config_version_id
                JOIN api_connections c ON c.id = cv.connection_id
                WHERE t.id = ?
                """

_TASK_SEGMENTS_SQL = """
                SELECT segment.*, standard.name AS standard_name,
                       standard.id AS standard_id,
                       standard_version.version_no AS standard_version
                FROM task_segments segment
                LEFT JOIN classification_standard_versions standard_version
                  ON standard_version.id = segment.standard_version_id
                LEFT JOIN classification_standards standard
                  ON standard.id = standard_version.standard_id
                WHERE segment.task_id = ?
                ORDER BY segment.execution_order, segment.segment_key
                """

_OWNER_RUNNING_SQL = """
                    SELECT COUNT(*) AS count
                    FROM task_segments s
                    JOIN tasks t ON t.id = s.task_id
                    WHERE t.owner_id = ? AND s.status = 'running'
                    """

_TASK_RUNNING_SQL = """
                    SELECT COUNT(*) AS count FROM task_segments
                    WHERE task_id = ? AND status = 'running'
                    """

_OWNER_WAITING_SQL = """
                    SELECT s.id
                    FROM task_segments s
                    JOIN tasks t ON t.id = s.task_id
                    WHERE t.owner_id = ?
                      AND s.status IN ('queued', 'retry_pending')
                    ORDER BY
                      (SELECT COUNT(*) FROM task_segments active
                       WHERE active.task_id = t.id AND active.status = 'running'),
                      COALESCE(t.last_scheduled_at, t.created_at),
                      s.execution_order, s.created_at
                    """


@dataclass(frozen=True)
class _TaskCapacity:
    owner_running: int
    task_running: int
    waiting_positions: dict[str, int]


def _running_capacity(
    connection: Connection, task_id: str, owner_id: str
) -> _TaskCapacity:
    owner_row = connection.execute(_OWNER_RUNNING_SQL, (owner_id,)).fetchone()
    task_row = connection.execute(_TASK_RUNNING_SQL, (task_id,)).fetchone()
    waiting_rows = connection.execute(_OWNER_WAITING_SQL, (owner_id,)).fetchall()
    positions = {
        str(value["id"]): position
        for position, value in enumerate(waiting_rows, start=1)
    }
    return _TaskCapacity(int(owner_row["count"]), int(task_row["count"]), positions)


def _segment_wait_reason(
    segment: dict[str, Any],
    task: dict[str, Any],
    capacity: _TaskCapacity,
    max_parallel: int,
) -> str | None:
    status = str(segment["status"])
    if status == "paused":
        model_issue = int(
            segment.get("model_failures") or 0
        ) >= _PAUSED_MODEL_FAILURE_DISPLAY_THRESHOLD and segment.get("error")
        return "模型服务异常，任务已暂停" if model_issue else "已由用户暂停"
    if status not in WAITING_SEGMENT_STATUSES:
        return None
    if task.get("pause_requested"):
        return "批量任务已暂停"
    if capacity.task_running >= max_parallel:
        return f"本批量并发已满：{capacity.task_running}/{max_parallel}"
    if capacity.owner_running >= SEGMENT_USER_LIMIT:
        return f"个人运行槽位已满：{capacity.owner_running}/{SEGMENT_USER_LIMIT}"
    return f"我的队列第 {capacity.waiting_positions.get(str(segment['id']), 1)} 位"


class TaskDetailQueriesMixin:
    database: Database
    _serialize: Callable[[dict[str, Any]], dict[str, Any]]

    if TYPE_CHECKING:

        @classmethod
        def _serialize_segment(
            cls,
            item: dict[str, Any],
            system_failure_count: int = 0,
        ) -> dict[str, Any]: ...

    def get(self, task_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(_TASK_DETAIL_SQL, (task_id,)).fetchone()
            segment_rows = connection.execute(_TASK_SEGMENTS_SQL, (task_id,)).fetchall()
            rerun_counts = system_rerun_counts(
                connection,
                [
                    str(segment["result_version_id"])
                    for segment in segment_rows
                    if segment["result_version_id"] is not None
                ],
            )
            if row is None:
                return None
            capacity = _running_capacity(connection, task_id, row["owner_id"])
        item = self._serialize(dict(row))
        item["segments"] = [
            self._serialize_segment(
                dict(value),
                rerun_counts.get(str(value["result_version_id"] or ""), 0),
            )
            for value in segment_rows
        ]
        max_parallel = int(item.get("max_parallel_segments", _DEFAULT_TASK_PARALLELISM))
        for segment in item["segments"]:
            reason = _segment_wait_reason(
                segment,
                item,
                capacity,
                max_parallel,
            )
            if reason is not None:
                segment["wait_reason"] = reason
        item["running_segments"] = capacity.task_running
        item["owner_running_segments"] = capacity.owner_running
        item["owner_segment_limit"] = SEGMENT_USER_LIMIT
        return item
