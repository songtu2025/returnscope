from __future__ import annotations

from typing import Any

from web_backend.operations.workbench_common import _time_key


def _recent_outputs(connection: Any, limit: int) -> list[dict[str, Any]]:
    result_rows, dashboard_rows, report_rows = _recent_output_rows(connection, limit)
    output = _result_outputs(result_rows)
    output.extend(_dashboard_outputs(dashboard_rows))
    output.extend(_report_outputs(report_rows))
    output.sort(
        key=lambda item: (
            -_time_key(item.get("updated_at")),
            str(item["type"]),
            str(item["object_id"]),
        )
    )
    return output[:limit]


def _recent_output_rows(
    connection: Any, limit: int
) -> tuple[list[Any], list[Any], list[Any]]:
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
    return (result_rows, dashboard_rows, report_rows)


def _result_outputs(rows: list[Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        output_type = (
            "derived_result" if item["parent_version_id"] else "classification_result"
        )
        title = " / ".join(
            (value for value in (item["store_site"], item["listing"]) if value)
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
    return output


def _dashboard_outputs(rows: list[Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows:
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
    return output


def _report_outputs(rows: list[Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows:
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
    return output
