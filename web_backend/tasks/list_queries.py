from __future__ import annotations

from collections.abc import Callable
from typing import Any

from web_backend.classification_result_queries import system_rerun_counts
from web_backend.common import json_text
from web_backend.database import Database


class TaskListQueriesMixin:
    database: Database
    _serialize_list: Callable[[dict[str, Any]], dict[str, Any]]
    _attach_system_retry_state: Callable[[dict[str, Any], int], None]

    def list(
        self,
        status: str | None = None,
        owner_id: str | None = None,
        include_archived: bool = False,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT t.id, t.title, t.store, t.listing, t.status,
                   t.progress_current, t.progress_total, t.progress_percent,
                   t.result_file_path, t.result_version,
                   t.created_at, t.completed_at, t.archived_at,
                   u.display_name AS owner_name,
                   rd.name AS dataset_name, rv.version AS dataset_version,
                   COALESCE(t.completed_at, t.heartbeat_at, t.started_at,
                            t.created_at) AS updated_at,
                   (SELECT COUNT(*) FROM task_segments segment
                    WHERE segment.task_id = t.id) AS listing_count,
                   (SELECT GROUP_CONCAT(
                               TRIM(
                                   COALESCE(
                                       json_extract(segment.scope_json, '$.store'),
                                       ''
                                   ) || ' ' ||
                                   COALESCE(
                                       json_extract(segment.scope_json, '$.listing'),
                                       ''
                                   )
                               ),
                               ' '
                           )
                    FROM task_segments segment
                    WHERE segment.task_id = t.id) AS listing_search_text,
                   CASE WHEN t.status = 'queued'
                             AND json_extract(
                                 t.snapshot_json,
                                 '$.execution_plan.unresolved_policy'
                             ) = 'run_ready'
                             AND COALESCE(
                                 json_extract(
                                     t.snapshot_json,
                                     '$.execution_plan.summary.blocked_count'
                                 ),
                                 0
                             ) > 0
                        THEN 1 ELSE 0 END AS partial_queue,
                   CASE WHEN t.status = 'queued' THEN (
                       SELECT COUNT(*) + 1 FROM tasks q
                       WHERE q.status = 'queued' AND q.created_at < t.created_at
                   ) END AS queue_position
            FROM tasks t
            JOIN users u ON u.id = t.owner_id
            JOIN dataset_versions rv ON rv.id = t.dataset_version_id
            JOIN datasets rd ON rd.id = rv.dataset_id
            WHERE 1 = 1
        """
        params: list[object] = []
        if status:
            query += " AND t.status = ?"
            params.append(status)
        if owner_id:
            query += " AND t.owner_id = ?"
            params.append(owner_id)
        if not include_archived:
            query += " AND t.archived_at IS NULL"
        query += " ORDER BY t.created_at DESC"
        with self.database.connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
            items = {row["id"]: self._serialize_list(dict(row)) for row in rows}
            for item in items.values():
                item["segments"] = []
            # 一次读取列表所需的执行与结果状态，避免逐任务加载完整详情。
            segments = connection.execute(
                """
                SELECT task_id, agent_key, status, result_publish_status,
                       result_version_id, result_quality_status,
                       result_file_path, error, model_failures
                FROM task_segments
                WHERE task_id IN (SELECT value FROM json_each(?))
                """,
                (json_text(list(items)),),
            ).fetchall()
            rerun_counts = system_rerun_counts(
                connection,
                [
                    str(segment["result_version_id"])
                    for segment in segments
                    if segment["result_version_id"] is not None
                ],
            )
            for segment in segments:
                value = dict(segment)
                version_id = str(value.get("result_version_id") or "")
                self._attach_system_retry_state(
                    value,
                    rerun_counts.get(version_id, 0),
                )
                items[value.pop("task_id")]["segments"].append(value)
        return list(items.values())
