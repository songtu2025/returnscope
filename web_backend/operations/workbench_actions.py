from __future__ import annotations

from typing import Any

from web_backend.common import json_value
from web_backend.operations.workbench_common import _actor


def _actions(connection: Any) -> list[dict[str, Any]]:
    task_rows, segment_rows = _task_action_rows(connection)
    result_rows, report_rows = _result_report_action_rows(connection)
    output = _task_actions(task_rows)
    output.extend(_segment_actions(segment_rows))
    output.extend(_result_actions(result_rows))
    output.extend(_report_actions(report_rows))
    return output


def _task_action_rows(connection: Any) -> tuple[Any, Any]:
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
    return task_rows, segment_rows


def _result_report_action_rows(connection: Any) -> tuple[Any, Any]:
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
    return result_rows, report_rows


def _task_actions(task_rows: Any) -> list[dict[str, Any]]:
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
                "actor": _actor(item),
                "updated_at": item["updated_at"],
                "target": {"route": "tasks", "task_id": item["id"]},
            }
        )
    return output


def _segment_actions(segment_rows: Any) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
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
                "actor": _actor(item),
                "updated_at": item["updated_at"],
                "target": {
                    "route": "tasks",
                    "task_id": item["task_id"],
                    "segment_id": item["id"],
                },
            }
        )
    return output


def _result_actions(result_rows: Any) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
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
    return output


def _report_actions(report_rows: Any) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
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
