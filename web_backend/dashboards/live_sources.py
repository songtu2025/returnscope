"""结果变化后自动推进相关看板，沿用原来源和用户统计范围。"""

from __future__ import annotations

from typing import Any

from web_backend.common import json_value
from web_backend.dashboard_plan import build_plan
from web_backend.dashboards.version_storage import _DashboardVersionStorage
from web_backend.database import Database


def refresh_related_dashboards(
    database: Database, connection: Any, result_id: str | None, now: str
) -> None:
    rows = connection.execute(
        """
        SELECT DISTINCT d.id, d.created_by, v.version_no, data.id AS dataset_id, data.filters_json
        FROM analysis_dashboards d
        JOIN dashboard_versions v ON v.id = d.current_version_id
        JOIN dashboard_dataset_versions data ON data.id = v.dataset_version_id
        JOIN dashboard_dataset_sources s ON s.dataset_version_id = data.id
        JOIN classification_result_versions r ON r.id = s.result_version_id
        WHERE (? IS NULL OR r.result_id = ?) AND d.status = 'active'
        """,
        (result_id, result_id),
    ).fetchall()
    storage = _DashboardVersionStorage()
    storage.database = database
    for row in rows:
        sources = connection.execute(
            """
            SELECT s.result_version_id AS previous_id,
                   (SELECT latest.id FROM classification_result_versions latest
                    WHERE latest.result_id = original.result_id AND latest.publish_status = 'published'
                    ORDER BY latest.version_no DESC LIMIT 1) AS latest_id
            FROM dashboard_dataset_sources s
            JOIN classification_result_versions original ON original.id = s.result_version_id
            WHERE s.dataset_version_id = ?
            """,
            (row["dataset_id"],),
        ).fetchall()
        if all(source["previous_id"] == source["latest_id"] for source in sources):
            continue
        plan = build_plan(
            database,
            connection,
            [source["latest_id"] for source in sources],
            json_value(row["filters_json"], {}),
        )
        version = storage._insert_version(
            connection,
            dashboard_id=row["id"],
            version_no=connection.execute(
                "SELECT COALESCE(MAX(version_no), 0) + 1 FROM dashboard_versions WHERE dashboard_id = ?",
                (row["id"],),
            ).fetchone()[0],
            plan=plan,
            reason="分类结果更新，自动同步",
            actor_id=row["created_by"],
            now=now,
        )
        connection.execute(
            "UPDATE analysis_dashboards SET current_version_id = ?, updated_at = ?, revision = revision + 1 WHERE id = ?",
            (version["version_id"], now, row["id"]),
        )
