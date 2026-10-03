from __future__ import annotations

from typing import Any

from web_backend.database import Database
from web_backend.operations.audit_service import AuditLogService as AuditLogService
from web_backend.operations.workbench_actions import _actions
from web_backend.operations.workbench_common import ACTION_PRIORITY as ACTION_PRIORITY
from web_backend.operations.workbench_common import _actor, _time_key


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

    _actions = staticmethod(_actions)
    _actor = staticmethod(_actor)
    _time_key = staticmethod(_time_key)
