from __future__ import annotations

import sqlite3
from typing import Any

from return_semantics.schemas import TaxonomyConfig
from web_backend.classification_result_payload import classification_comment_status
from web_backend.common import json_value
from web_backend.dashboard_common import COMMENT_SUMMARY_STATUSES, FEEDBACK_GROUP_BASIS
from web_backend.dashboard_support import record_where
from web_backend.database import Database
from web_backend.result_hierarchy import feedback_group_key_sql, result_taxonomy

_SOURCE_TOTALS_SQL = """
SELECT COUNT(DISTINCT {identity}) AS record_count,
       COUNT(DISTINCT r.result_version_id || ':' ||
             r.classification_key) AS unit_count,
       COUNT(DISTINCT CASE WHEN r.product_name IS NULL
                     OR TRIM(r.product_name) = ''
                THEN {identity} END) AS product_name_missing_count,
       COUNT(DISTINCT CASE WHEN r.product_match_status != 'matched'
                THEN {identity} END) AS product_unmatched_count
FROM classification_result_records r
WHERE {where_sql}
"""

_SOURCE_COVERAGE_SQL = """
SELECT COUNT(DISTINCT {identity}) AS total_record_count,
       COUNT(DISTINCT CASE WHEN r.quality_status = 'excluded'
                THEN {identity} END) AS excluded_record_count,
       COUNT(DISTINCT CASE WHEN r.quality_status NOT IN ('ready', 'excluded')
                THEN {identity} END) AS pending_review_record_count
FROM classification_result_records r
WHERE {scope_where}
"""

_COMMENT_STATUS_COUNTS_SQL = """
SELECT r.result_version_id, u.classification_json,
       {count_sql} AS comment_count
FROM classification_result_records r
JOIN classification_units u
  ON u.result_version_id = r.result_version_id
 AND u.classification_key = r.classification_key
WHERE {where_sql}
GROUP BY r.result_version_id, r.classification_key
"""

_COMMENT_COVERAGE_SQL = """
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
"""


def summarize_sources(
    database: Database,
    connection: sqlite3.Connection,
    source_ids: list[str],
    filters: dict[str, list[str]],
    sources: list[dict[str, Any]],
    *,
    include_comment_metrics: bool = True,
    feedback_groups: bool = False,
) -> dict[str, Any]:
    identity = feedback_group_key_sql("r") if feedback_groups else "r.id"
    if source_ids:
        where_sql, params = record_where(database, source_ids, filters)
        row = connection.execute(
            _SOURCE_TOTALS_SQL.format(identity=identity, where_sql=where_sql),
            tuple(params),
        ).fetchone()
        record_count = int(row["record_count"] or 0)
        unit_count = int(row["unit_count"] or 0)
        missing_count = int(row["product_name_missing_count"] or 0)
        unmatched_count = int(row["product_unmatched_count"] or 0)
    else:
        record_count = unit_count = missing_count = unmatched_count = 0
    summary = _source_summary(
        source_ids, sources, (record_count, unit_count, missing_count, unmatched_count)
    )
    if feedback_groups:
        summary["counting_basis"] = FEEDBACK_GROUP_BASIS
    if source_ids:
        scope_filters = {
            key: value for key, value in filters.items() if key != "quality_status"
        }
        scope_where, scope_params = record_where(database, source_ids, scope_filters)
        if include_comment_metrics:
            summary.update(
                comment_summary_metrics(
                    connection,
                    where_sql,
                    params,
                    scope_where,
                    scope_params,
                    feedback_groups=feedback_groups,
                )
            )
        _update_review_coverage(
            connection, summary, scope_where, scope_params, identity
        )
    return summary


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
        _COMMENT_STATUS_COUNTS_SQL.format(count_sql=count_sql, where_sql=where_sql),
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
        _COMMENT_COVERAGE_SQL.format(
            count_sql=count_sql, total_where_sql=total_where_sql
        ),
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


def _source_summary(
    source_ids: list[str],
    sources: list[dict[str, Any]],
    counts: tuple[int, int, int, int],
) -> dict[str, Any]:
    record_count, unit_count, missing_count, unmatched_count = counts
    return {
        "source_count": len(source_ids),
        "store_count": len(
            {source["store_site"] for source in sources if source["store_site"]}
        ),
        "listing_count": len(
            {(source["store_site"], source["listing"]) for source in sources}
        ),
        "record_count": record_count,
        "unit_count": unit_count,
        "comment_count": 0,
        "total_comment_count": 0,
        "pending_review_comment_count": 0,
        "comment_statuses": [
            {"status": status, "comment_count": 0}
            for status in COMMENT_SUMMARY_STATUSES
        ],
        "product_name_missing_count": missing_count,
        "product_unmatched_count": unmatched_count,
        "review_changed_unit_count": sum(
            int(source.get("review_changed_unit_count") or 0) for source in sources
        ),
        "taxonomy_versions": sorted(
            {
                str(source["taxonomy_version"])
                for source in sources
                if source.get("taxonomy_version")
            }
        ),
    }


def _update_review_coverage(
    connection: sqlite3.Connection,
    summary: dict[str, Any],
    scope_where: str,
    scope_params: list[Any],
    identity: str,
) -> None:
    record_count = summary["record_count"]
    coverage = connection.execute(
        _SOURCE_COVERAGE_SQL.format(identity=identity, scope_where=scope_where),
        tuple(scope_params),
    ).fetchone()
    total_record_count = int(coverage["total_record_count"] or 0)
    excluded_record_count = int(coverage["excluded_record_count"] or 0)
    pending_review_record_count = int(coverage["pending_review_record_count"] or 0)
    if (
        total_record_count != record_count
        or excluded_record_count
        or pending_review_record_count
    ):
        summary.update(
            {
                "total_record_count": total_record_count,
                "pending_review_record_count": pending_review_record_count,
                "excluded_record_count": excluded_record_count,
                "coverage_rate": round(
                    record_count * 100 / total_record_count,
                    2,
                )
                if total_record_count
                else 0,
            }
        )
