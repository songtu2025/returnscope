from __future__ import annotations

import sqlite3
from typing import Any

from return_semantics.schemas import TaxonomyConfig
from web_backend.classification_result_payload import classification_comment_status
from web_backend.common import json_value
from web_backend.dashboard_common import COMMENT_SUMMARY_STATUSES
from web_backend.result_hierarchy import feedback_group_key_sql, result_taxonomy


def comment_summary_metrics(
    connection: sqlite3.Connection,
    where_sql: str,
    params: list[Any],
    total_where_sql: str,
    total_params: list[Any],
    *,
    feedback_groups: bool = False,
) -> dict[str, Any]:
    count_sql = (
        f"COUNT(DISTINCT {feedback_group_key_sql('r')})"
        if feedback_groups
        else "COUNT(r.id)"
    )
    rows = connection.execute(
        f"""
        SELECT r.result_version_id, u.classification_json,
               {count_sql} AS comment_count
        FROM classification_result_records r
        JOIN classification_units u
          ON u.result_version_id = r.result_version_id
         AND u.classification_key = r.classification_key
        WHERE {where_sql}
        GROUP BY r.result_version_id, r.classification_key
        """,
        tuple(params),
    ).fetchall()
    status_counts = {status: 0 for status in COMMENT_SUMMARY_STATUSES}
    taxonomies: dict[str, TaxonomyConfig | None] = {}
    for row in rows:
        version_id = str(row["result_version_id"])
        if version_id not in taxonomies:
            taxonomies[version_id] = result_taxonomy(connection, version_id)
        payload = json_value(row["classification_json"], {})
        status = classification_comment_status(payload, taxonomies[version_id])
        status_counts[status] += int(row["comment_count"] or 0)

    coverage = connection.execute(
        f"""
        SELECT COALESCE(SUM(comment_count), 0) AS total_comment_count,
               COALESCE(SUM(
                   CASE WHEN pending_review = 1 THEN comment_count ELSE 0 END
               ), 0) AS pending_review_comment_count
        FROM (
            SELECT {count_sql} AS comment_count,
                   MAX(
                       CASE WHEN u.quality_status NOT IN ('ready', 'excluded')
                            THEN 1 ELSE 0 END
                   ) AS pending_review
            FROM classification_result_records r
            JOIN classification_units u
              ON u.result_version_id = r.result_version_id
             AND u.classification_key = r.classification_key
            WHERE {total_where_sql}
            GROUP BY r.result_version_id, r.classification_key
        ) scoped_comments
        """,
        tuple(total_params),
    ).fetchone()
    return {
        "comment_count": sum(int(row["comment_count"] or 0) for row in rows),
        "total_comment_count": int(coverage["total_comment_count"] or 0),
        "pending_review_comment_count": int(
            coverage["pending_review_comment_count"] or 0
        ),
        "comment_statuses": [
            {"status": status, "comment_count": status_counts[status]}
            for status in COMMENT_SUMMARY_STATUSES
        ],
    }
