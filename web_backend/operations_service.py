from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from web_backend.common import json_value
from web_backend.database import Database

ACTION_PRIORITY = {
    "blocked": 0,
    "failed": 1,
    "report_failed": 1,
    "report_running": 2,
    "review_required": 3,
    "paused": 4,
}


class WorkbenchService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def summary(self, limit: int = 5) -> dict[str, Any]:
        with self.database.connect() as connection:
            actions = self._actions(connection)
            recent_outputs = self._recent_outputs(connection, limit)
            counts = dict(
                connection.execute(
                    """
                    SELECT
                      (SELECT COUNT(*) FROM tasks
                       WHERE status = 'blocked') AS blocked_tasks,
                      (SELECT COUNT(*) FROM task_segments
                       WHERE status = 'blocked') AS blocked_segments,
                      (SELECT COUNT(*) FROM task_segments
                       WHERE status = 'failed') AS failed_segments,
                      (SELECT COUNT(*) FROM tasks
                       WHERE status = 'paused') AS paused_tasks,
                      (SELECT COUNT(*) FROM task_segments
                       WHERE status = 'paused') AS paused_segments,
                      (SELECT COUNT(*) FROM classification_result_versions
                       WHERE publish_status = 'published'
                         AND quality_status = 'review_required')
                        AS review_required_results,
                      (SELECT COUNT(*) FROM classification_result_versions
                       WHERE publish_status = 'published'
                         AND quality_status = 'ready') AS ready_results,
                      (SELECT COUNT(*) FROM analysis_dashboards
                       WHERE status = 'active') AS dashboards,
                      (SELECT COUNT(*) FROM ai_insight_reports
                       WHERE status IN ('queued', 'running')) AS running_reports,
                      (SELECT COUNT(*) FROM ai_insight_reports
                       WHERE status = 'failed') AS failed_reports
                    """
                ).fetchone()
            )
        actions.sort(
            key=lambda item: (
                ACTION_PRIORITY[item["type"]],
                -self._time_key(item.get("updated_at")),
                str(item["object_id"]),
            )
        )
        return {
            "actions": actions[:limit],
            "recent_outputs": recent_outputs,
            "counts": {key: int(value or 0) for key, value in counts.items()},
        }

    @staticmethod
    def _actions(connection: Any) -> list[dict[str, Any]]:
        task_rows = connection.execute(
            """
            SELECT t.id, t.title, t.status, t.message, t.error,
                   owner.id AS actor_id, owner.display_name AS actor_name,
                   COALESCE(t.heartbeat_at, t.completed_at, t.started_at,
                            t.created_at) AS updated_at
            FROM tasks t
            LEFT JOIN users owner ON owner.id = t.owner_id
            WHERE t.status IN ('blocked', 'paused')
            """
        ).fetchall()
        segment_rows = connection.execute(
            """
            SELECT s.id, s.task_id, s.segment_key, s.status, s.error,
                   s.result_publish_error, s.scope_json, t.title AS task_title,
                   owner.id AS actor_id, owner.display_name AS actor_name,
                   COALESCE(s.heartbeat_at, s.completed_at, s.started_at,
                            s.created_at) AS updated_at
            FROM task_segments s
            JOIN tasks t ON t.id = s.task_id
            LEFT JOIN users owner ON owner.id = t.owner_id
            WHERE s.status IN ('blocked', 'failed', 'paused')
            """
        ).fetchall()
        result_rows = connection.execute(
            """
            SELECT v.id, v.result_id, v.quality_status, v.published_at,
                   v.created_at, v.created_by, creator.display_name,
                   r.source_task_id, r.source_segment_id,
                   r.store_site, r.listing
            FROM classification_result_versions v
            JOIN classification_results r ON r.id = v.result_id
            LEFT JOIN users creator ON creator.id = v.created_by
            WHERE v.publish_status = 'published'
              AND v.quality_status = 'review_required'
            """
        ).fetchall()
        report_rows = connection.execute(
            """
            SELECT report.id, report.dashboard_id,
                   report.dashboard_version_id, report.status,
                   report.stage, report.error, report.created_at,
                   report.started_at, report.completed_at,
                   report.created_by, creator.display_name,
                   dashboard.name AS dashboard_name
            FROM ai_insight_reports report
            JOIN analysis_dashboards dashboard
              ON dashboard.id = report.dashboard_id
            LEFT JOIN users creator ON creator.id = report.created_by
            WHERE report.status IN ('queued', 'running')
               OR (
                    report.status = 'failed'
                    AND NOT EXISTS (
                        SELECT 1 FROM ai_insight_reports child
                        WHERE child.parent_job_id = report.id
                    )
               )
            """
        ).fetchall()

        output: list[dict[str, Any]] = []
        for row in task_rows:
            item = dict(row)
            action_type = "blocked" if item["status"] == "blocked" else "paused"
            output.append(
                {
                    "type": action_type,
                    "object_type": "task",
                    "object_id": item["id"],
                    "task_id": item["id"],
                    "segment_id": None,
                    "result_version_id": None,
                    "title": item["title"],
                    "reason": item["error"] or item["message"] or "",
                    "status": item["status"],
                    "actor": WorkbenchService._actor(item),
                    "updated_at": item["updated_at"],
                    "target": {"route": "tasks", "task_id": item["id"]},
                }
            )
        for row in segment_rows:
            item = dict(row)
            scope = json_value(item.pop("scope_json"), {}) or {}
            listing = str(scope.get("listing") or item["segment_key"])
            output.append(
                {
                    "type": item["status"],
                    "object_type": "task_segment",
                    "object_id": item["id"],
                    "task_id": item["task_id"],
                    "segment_id": item["id"],
                    "result_version_id": None,
                    "title": f"{item['task_title']} / {listing}",
                    "reason": (
                        item["error"] or item["result_publish_error"] or item["status"]
                    ),
                    "status": item["status"],
                    "actor": WorkbenchService._actor(item),
                    "updated_at": item["updated_at"],
                    "target": {
                        "route": "tasks",
                        "task_id": item["task_id"],
                        "segment_id": item["id"],
                    },
                }
            )
        for row in result_rows:
            item = dict(row)
            title = " / ".join(
                value for value in (item["store_site"], item["listing"]) if value
            ) or str(item["id"])
            output.append(
                {
                    "type": "review_required",
                    "object_type": "classification_result_version",
                    "object_id": item["id"],
                    "task_id": item["source_task_id"],
                    "segment_id": item["source_segment_id"],
                    "result_version_id": item["id"],
                    "title": title,
                    "reason": "分类结果需要人工复核",
                    "status": item["quality_status"],
                    "actor": {
                        "id": item["created_by"],
                        "name": item["display_name"],
                    },
                    "updated_at": item["published_at"] or item["created_at"],
                    "target": {
                        "route": "classification-results",
                        "result_version_id": item["id"],
                        "action": "review",
                    },
                }
            )
        stage_labels = {
            "queued": "等待生成",
            "preparing_evidence": "正在准备证据",
            "calling_model": "模型正在解释证据",
            "assembling_report": "正在装配报告",
            "publishing": "正在发布报告",
        }
        for row in report_rows:
            item = dict(row)
            failed = item["status"] == "failed"
            output.append(
                {
                    "type": "report_failed" if failed else "report_running",
                    "object_type": "ai_insight_report_job",
                    "object_id": item["id"],
                    "task_id": None,
                    "segment_id": None,
                    "result_version_id": None,
                    "title": item["dashboard_name"],
                    "reason": (
                        item["error"]
                        if failed
                        else stage_labels.get(item["stage"], "正在生成报告")
                    ),
                    "status": item["status"],
                    "actor": {
                        "id": item["created_by"],
                        "name": item["display_name"],
                    },
                    "updated_at": (
                        item["completed_at"] or item["started_at"] or item["created_at"]
                    ),
                    "target": {
                        "route": "analysis-dashboards",
                        "dashboard_id": item["dashboard_id"],
                        "version_id": item["dashboard_version_id"],
                        "report_id": item["id"],
                        "tab": "report",
                    },
                }
            )
        return output

    @staticmethod
    def _recent_outputs(connection: Any, limit: int) -> list[dict[str, Any]]:
        result_rows = connection.execute(
            """
            SELECT v.id, v.result_id, v.version_no, v.parent_version_id,
                   v.published_at, v.created_at, v.quality_status,
                   r.store_site, r.listing
            FROM classification_result_versions v
            JOIN classification_results r ON r.id = v.result_id
            WHERE v.publish_status = 'published' AND v.quality_status = 'ready'
            ORDER BY COALESCE(v.published_at, v.created_at) DESC, v.id ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        dashboard_rows = connection.execute(
            """
            SELECT d.id, d.name, d.current_version_id, d.updated_at,
                   v.version_no
            FROM analysis_dashboards d
            JOIN dashboard_versions v ON v.id = d.current_version_id
            WHERE d.status = 'active'
            ORDER BY d.updated_at DESC, d.id ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        report_rows = connection.execute(
            """
            SELECT published.id AS version_id, published.version_no,
                   published.published_at, report.id AS report_id,
                   report.dashboard_id, report.dashboard_version_id,
                   dashboard.name
            FROM ai_insight_report_versions published
            JOIN ai_insight_reports report ON report.id = published.job_id
            JOIN analysis_dashboards dashboard
              ON dashboard.id = report.dashboard_id
            ORDER BY published.published_at DESC, published.id ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        output: list[dict[str, Any]] = []
        for row in result_rows:
            item = dict(row)
            output_type = (
                "derived_result"
                if item["parent_version_id"]
                else "classification_result"
            )
            title = " / ".join(
                value for value in (item["store_site"], item["listing"]) if value
            ) or str(item["id"])
            output.append(
                {
                    "type": output_type,
                    "object_id": item["result_id"],
                    "version_id": item["id"],
                    "version_no": int(item["version_no"]),
                    "title": title,
                    "status": item["quality_status"],
                    "updated_at": item["published_at"] or item["created_at"],
                    "target": {
                        "route": "classification-results",
                        "result_version_id": item["id"],
                    },
                }
            )
        for row in dashboard_rows:
            item = dict(row)
            output.append(
                {
                    "type": "dashboard",
                    "object_id": item["id"],
                    "version_id": item["current_version_id"],
                    "version_no": int(item["version_no"]),
                    "title": item["name"],
                    "status": "active",
                    "updated_at": item["updated_at"],
                    "target": {
                        "route": "analysis-dashboards",
                        "dashboard_id": item["id"],
                        "version_id": item["current_version_id"],
                    },
                }
            )
        for row in report_rows:
            item = dict(row)
            output.append(
                {
                    "type": "insight_report",
                    "object_id": item["report_id"],
                    "version_id": item["version_id"],
                    "version_no": int(item["version_no"]),
                    "title": item["name"],
                    "status": "completed",
                    "updated_at": item["published_at"],
                    "target": {
                        "route": "analysis-dashboards",
                        "dashboard_id": item["dashboard_id"],
                        "version_id": item["dashboard_version_id"],
                        "report_id": item["report_id"],
                        "tab": "report",
                    },
                }
            )
        output.sort(
            key=lambda item: (
                -WorkbenchService._time_key(item.get("updated_at")),
                str(item["type"]),
                str(item["object_id"]),
            )
        )
        return output[:limit]

    @staticmethod
    def _actor(item: dict[str, Any]) -> dict[str, Any]:
        return {"id": item.get("actor_id"), "name": item.get("actor_name")}

    @staticmethod
    def _time_key(value: Any) -> float:
        text = str(value or "").replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text).timestamp()
        except ValueError:
            return 0.0


class AuditLogService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list(
        self,
        *,
        actor_id: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        action: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        where = ["1 = 1"]
        params: list[Any] = []
        for column, value in (
            ("a.actor_id", actor_id),
            ("a.entity_type", entity_type),
            ("a.entity_id", entity_id),
            ("a.action", action),
        ):
            if value:
                where.append(f"{column} = ?")
                params.append(value)
        if date_from:
            normalized_from, _ = self._date_boundary(date_from, is_end=False)
            where.append("a.created_at >= ?")
            params.append(normalized_from)
        if date_to:
            normalized_to, inclusive = self._date_boundary(date_to, is_end=True)
            where.append("a.created_at <= ?" if inclusive else "a.created_at < ?")
            params.append(normalized_to)
        where_sql = " AND ".join(where)
        with self.database.connect() as connection:
            total = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM audit_logs a WHERE {where_sql}",
                    tuple(params),
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"""
                SELECT a.*, u.display_name AS actor_name
                FROM audit_logs a
                LEFT JOIN users u ON u.id = a.actor_id
                WHERE {where_sql}
                ORDER BY a.created_at DESC, a.id ASC
                LIMIT ? OFFSET ?
                """,
                (*params, page_size, (page - 1) * page_size),
            ).fetchall()
            target_context = self._target_context(connection, rows)
        items = []
        for row in rows:
            item = dict(row)
            item["before"] = json_value(item.pop("before_json"), None)
            item["after"] = json_value(item.pop("after_json"), None)
            item["target"] = self._target(
                item["entity_type"],
                item["entity_id"],
                target_context,
            )
            items.append(item)
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    @staticmethod
    def _target_context(
        connection: Any,
        audit_rows: list[Any],
    ) -> dict[tuple[str, str], dict[str, Any]]:
        ids_by_type: dict[str, set[str]] = {}
        for row in audit_rows:
            ids_by_type.setdefault(str(row["entity_type"]), set()).add(
                str(row["entity_id"])
            )

        context: dict[tuple[str, str], dict[str, Any]] = {}

        def load(entity_type: str, query: str) -> None:
            entity_ids = sorted(ids_by_type.get(entity_type, set()))
            if not entity_ids:
                return
            placeholders = ",".join("?" for _ in entity_ids)
            rows = connection.execute(
                query.format(placeholders=placeholders),
                tuple(entity_ids),
            ).fetchall()
            for row in rows:
                item = dict(row)
                context[(entity_type, str(item["id"]))] = item

        load("task", "SELECT id FROM tasks WHERE id IN ({placeholders})")
        load(
            "task_segment",
            """
            SELECT segment.id, segment.task_id
            FROM task_segments segment
            JOIN tasks task ON task.id = segment.task_id
            WHERE segment.id IN ({placeholders})
            """,
        )
        load(
            "classification_result_version",
            """
            SELECT id FROM classification_result_versions
            WHERE id IN ({placeholders})
            """,
        )
        load(
            "classification_result",
            """
            SELECT id, result_version_id
            FROM (
                SELECT result.id, version.id AS result_version_id,
                       ROW_NUMBER() OVER (
                           PARTITION BY result.id
                           ORDER BY version.version_no DESC,
                                    version.published_at DESC,
                                    version.id ASC
                       ) AS position
                FROM classification_results result
                JOIN classification_result_versions version
                  ON version.result_id = result.id
                 AND version.publish_status = 'published'
                WHERE result.id IN ({placeholders})
            ) latest
            WHERE position = 1
            """,
        )
        load(
            "review",
            """
            SELECT id, workflow_status FROM review_records
            WHERE id IN ({placeholders})
            """,
        )
        load(
            "review_batch",
            "SELECT id FROM review_batches WHERE id IN ({placeholders})",
        )
        load(
            "dataset",
            "SELECT id, kind FROM datasets WHERE id IN ({placeholders})",
        )
        load(
            "api_connection",
            "SELECT id FROM api_connections WHERE id IN ({placeholders})",
        )
        load(
            "api_config_version",
            """
            SELECT id, connection_id FROM api_config_versions
            WHERE id IN ({placeholders})
            """,
        )
        load(
            "api_model",
            """
            SELECT id, connection_id FROM api_models
            WHERE id IN ({placeholders})
            """,
        )
        load("user", "SELECT id FROM users WHERE id IN ({placeholders})")
        load(
            "analysis_dashboard",
            """
            SELECT id, current_version_id FROM analysis_dashboards
            WHERE id IN ({placeholders})
            """,
        )
        return context

    @staticmethod
    def _target(
        entity_type: str,
        entity_id: str,
        context: dict[tuple[str, str], dict[str, Any]],
    ) -> dict[str, Any] | None:
        source = context.get((entity_type, entity_id))
        if source is None:
            return None
        if entity_type == "task":
            return {"route": "tasks", "task_id": entity_id}
        if entity_type == "task_segment":
            return {
                "route": "tasks",
                "task_id": source["task_id"],
                "segment_id": entity_id,
            }
        if entity_type == "classification_result_version":
            return {
                "route": "classification-results",
                "result_version_id": entity_id,
            }
        if entity_type == "classification_result":
            return {
                "route": "classification-results",
                "result_version_id": source["result_version_id"],
            }
        if entity_type == "review":
            return {
                "route": "review",
                "review_id": entity_id,
                "workflow_status": source["workflow_status"],
            }
        if entity_type == "review_batch":
            return {"route": "review-center", "batch_id": entity_id}
        if entity_type == "dataset":
            return {
                "route": "data",
                "dataset_id": entity_id,
                "view": source["kind"],
            }
        if entity_type == "api_connection":
            return {
                "route": "api",
                "tab": "api",
                "connection_id": entity_id,
            }
        if entity_type == "api_config_version":
            return {
                "route": "api",
                "tab": "api",
                "connection_id": source["connection_id"],
                "config_version_id": entity_id,
            }
        if entity_type == "api_model":
            return {
                "route": "api",
                "tab": "models",
                "connection_id": source["connection_id"],
                "model_id": entity_id,
            }
        if entity_type == "user":
            return {
                "route": "team",
                "tab": "users",
                "user_id": entity_id,
            }
        if entity_type == "analysis_dashboard":
            target = {
                "route": "analysis-dashboards",
                "dashboard_id": entity_id,
            }
            if source["current_version_id"]:
                target["version_id"] = source["current_version_id"]
            return target
        return None

    @staticmethod
    def _date_boundary(value: str, *, is_end: bool) -> tuple[str, bool]:
        clean_value = value.strip()
        if len(clean_value) == 10:
            try:
                parsed_date = date.fromisoformat(clean_value)
            except ValueError as exc:
                raise ValueError("审计日期必须是 YYYY-MM-DD 或 ISO 时间戳") from exc
            boundary_date = parsed_date + timedelta(days=1) if is_end else parsed_date
            boundary = datetime.combine(
                boundary_date,
                time.min,
                tzinfo=timezone.utc,
            )
            return boundary.isoformat(), False
        try:
            parsed_time = datetime.fromisoformat(clean_value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("审计日期必须是 YYYY-MM-DD 或 ISO 时间戳") from exc
        if parsed_time.tzinfo is not None:
            parsed_time = parsed_time.astimezone(timezone.utc)
        return parsed_time.isoformat(), True
