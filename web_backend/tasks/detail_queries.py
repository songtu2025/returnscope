from __future__ import annotations

from collections.abc import Callable
from typing import Any

from web_backend.classification_result_queries import system_rerun_counts
from web_backend.database import Database
from web_backend.task_contracts import SEGMENT_USER_LIMIT, WAITING_SEGMENT_STATUSES


class TaskDetailQueriesMixin:
    database: Database
    _serialize: Callable[[dict[str, Any]], dict[str, Any]]
    _serialize_segment: Callable[..., dict[str, Any]]

    def get(self, task_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
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
                """,
                (task_id,),
            ).fetchone()
            segment_rows = connection.execute(
                """
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
                """,
                (task_id,),
            ).fetchall()
            rerun_counts = system_rerun_counts(
                connection,
                [
                    str(segment["result_version_id"])
                    for segment in segment_rows
                    if segment["result_version_id"] is not None
                ],
            )
            owner_running = 0
            task_running = 0
            waiting_positions: dict[str, int] = {}
            if row is not None:
                owner_running_row = connection.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM task_segments s
                    JOIN tasks t ON t.id = s.task_id
                    WHERE t.owner_id = ? AND s.status = 'running'
                    """,
                    (row["owner_id"],),
                ).fetchone()
                owner_running = int(owner_running_row["count"])
                task_running_row = connection.execute(
                    """
                    SELECT COUNT(*) AS count FROM task_segments
                    WHERE task_id = ? AND status = 'running'
                    """,
                    (task_id,),
                ).fetchone()
                task_running = int(task_running_row["count"])
                waiting_rows = connection.execute(
                    """
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
                    """,
                    (row["owner_id"],),
                ).fetchall()
                waiting_positions = {
                    str(value["id"]): position
                    for position, value in enumerate(waiting_rows, start=1)
                }
        if row is None:
            return None
        item = self._serialize(dict(row))
        item["segments"] = [
            self._serialize_segment(
                dict(value),
                rerun_counts.get(str(value["result_version_id"] or ""), 0),
            )
            for value in segment_rows
        ]
        max_parallel = int(item.get("max_parallel_segments", 3))
        for segment in item["segments"]:
            status = str(segment["status"])
            if status not in WAITING_SEGMENT_STATUSES:
                if status == "paused":
                    if int(segment.get("model_failures") or 0) >= 3 and segment.get(
                        "error"
                    ):
                        segment["wait_reason"] = "模型服务异常，任务已暂停"
                    else:
                        segment["wait_reason"] = "已由用户暂停"
                continue
            if item.get("pause_requested"):
                reason = "批量任务已暂停"
            elif task_running >= max_parallel:
                reason = f"本批量并发已满：{task_running}/{max_parallel}"
            elif owner_running >= SEGMENT_USER_LIMIT:
                reason = f"个人运行槽位已满：{owner_running}/{SEGMENT_USER_LIMIT}"
            else:
                reason = f"我的队列第 {waiting_positions.get(str(segment['id']), 1)} 位"
            segment["wait_reason"] = reason
        item["running_segments"] = task_running
        item["owner_running_segments"] = owner_running
        item["owner_segment_limit"] = SEGMENT_USER_LIMIT
        return item
