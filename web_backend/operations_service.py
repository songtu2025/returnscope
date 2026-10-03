from __future__ import annotations

from datetime import datetime
from typing import Any

from web_backend.common import json_value
from web_backend.database import Database
from web_backend.operations.audit_service import AuditLogService as AuditLogService

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
