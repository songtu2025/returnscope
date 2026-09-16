from __future__ import annotations

from typing import Any

from web_backend.common import json_text, json_value, new_id
from web_backend.database import Database
from web_backend.task_contracts import SEGMENT_USER_LIMIT, WAITING_SEGMENT_STATUSES


class TaskQueriesMixin:
    database: Database

    def list(
        self,
        status: str | None = None,
        owner_id: str | None = None,
        include_archived: bool = False,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT t.*, u.display_name AS owner_name,
                   rd.name AS dataset_name, rv.version AS dataset_version,
                   pd.name AS product_name, pv.version AS product_version,
                   c.name AS connection_name, cv.version AS config_version,
                   cv.primary_model,
                   COALESCE(t.completed_at, t.heartbeat_at, t.started_at,
                            t.created_at) AS updated_at,
                   (SELECT COUNT(*) FROM task_segments segment
                    WHERE segment.task_id = t.id) AS listing_count,
                   (SELECT GROUP_CONCAT(segment.scope_json, ' ')
                    FROM task_segments segment
                    WHERE segment.task_id = t.id) AS listing_search_text,
                   CASE WHEN t.status = 'queued' THEN (
                       SELECT COUNT(*) + 1 FROM tasks q
                       WHERE q.status = 'queued' AND q.created_at < t.created_at
                   ) END AS queue_position
            FROM tasks t
            JOIN users u ON u.id = t.owner_id
            JOIN dataset_versions rv ON rv.id = t.dataset_version_id
            JOIN datasets rd ON rd.id = rv.dataset_id
            JOIN dataset_versions pv ON pv.id = t.product_version_id
            JOIN datasets pd ON pd.id = pv.dataset_id
            JOIN api_config_versions cv ON cv.id = t.config_version_id
            JOIN api_connections c ON c.id = cv.connection_id
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
            items = {row["id"]: self._serialize(dict(row)) for row in rows}
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
            for segment in segments:
                value = dict(segment)
                items[value.pop("task_id")]["segments"].append(value)
        return list(items.values())

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
            self._serialize_segment(dict(value)) for value in segment_rows
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

    def events(self, task_id: str, after_id: int = 0) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT e.*, u.display_name AS actor_name
                FROM task_events e
                LEFT JOIN users u ON u.id = e.actor_id
                WHERE e.task_id = ? AND e.id > ?
                ORDER BY e.id ASC
                """,
                (task_id, after_id),
            ).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            item["data"] = json_value(item.pop("data_json"), {})
            output.append(item)
        return output

    def running_count(self, owner_id: str) -> int:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM task_segments s
                JOIN tasks t ON t.id = s.task_id
                WHERE t.owner_id = ? AND s.status = 'running'
                """,
                (owner_id,),
            ).fetchone()
        return int(row["count"])

    @staticmethod
    def _status_text(status: str) -> tuple[str, str]:
        values = {
            "queued": ("等待运行", "任务执行计划已更新并进入队列"),
            "running": ("语义分析", "Listing 片段正在运行"),
            "paused": ("已暂停", "未完成 Listing 已暂停"),
            "completed": ("分析完成", "全部任务片段已经完成"),
            "partial": ("部分完成", "已有可交付结果，仍有片段待处理"),
            "blocked": ("等待品类处理", "当前没有可执行的任务片段"),
            "cancelled": ("已取消", "未完成 Listing 已取消"),
            "failed": ("运行失败", "Listing 片段运行失败"),
        }
        return values[status]

    @staticmethod
    def _segment_status(
        segment: dict[str, Any],
        unresolved_policy: str,
        has_blocked: bool,
    ) -> str:
        if segment["status"] == "blocked":
            return "blocked"
        if unresolved_policy == "block_all" and has_blocked:
            return "not_started"
        return "queued"

    @staticmethod
    def _insert_audit(
        connection: Any,
        task_id: str,
        action: str,
        actor_id: str,
        before: dict[str, Any],
        after: dict[str, Any],
        created_at: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO audit_logs(
                id, entity_type, entity_id, action, before_json,
                after_json, actor_id, created_at
            ) VALUES (?, 'task', ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id("audit"),
                task_id,
                action,
                json_text(before),
                json_text(after),
                actor_id,
                created_at,
            ),
        )

    @staticmethod
    def _serialize(item: dict[str, Any]) -> dict[str, Any]:
        item["snapshot"] = json_value(item.pop("snapshot_json", None), {})
        item["metrics"] = json_value(item.pop("metrics_json", None), {})
        item["cancel_requested"] = bool(item.get("cancel_requested"))
        item["pause_requested"] = bool(item.get("pause_requested"))
        return item

    @staticmethod
    def _serialize_segment(item: dict[str, Any]) -> dict[str, Any]:
        item["variants"] = json_value(item.pop("variants_json", None), [])
        item["scope"] = json_value(item.pop("scope_json", None), {})
        item["model_policy"] = json_value(
            item.pop("model_policy_json", None),
            None,
        )
        item.pop("classification_keys_json", None)
        requested_action = item.get("requested_action")
        item["display_status"] = (
            f"{requested_action}_pending"
            if item.get("status") == "running" and requested_action
            else item.get("status")
        )
        return item
