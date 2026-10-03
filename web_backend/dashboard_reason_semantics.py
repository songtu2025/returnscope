from __future__ import annotations

from typing import Any

from web_backend.dashboard_insight_scope import InsightQueryScope
from web_backend.dashboard_support import percentage
from web_backend.request_timing import timed_stage


def _collect_reason_semantics(
    scope: InsightQueryScope, selected_code: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    # 明细组装已在同一连接中准备所选原因的反馈范围。
    connection = scope.connection
    where_sql = scope.where_sql
    params = scope.params
    with timed_stage("insight_semantics"):
        # 复用发布时的语义明细，保留当前筛选范围的反馈权重。
        connection.execute(
            "DROP TABLE IF EXISTS temp.dashboard_insight_reason_semantics"
        )
        connection.execute(
            f"""
                CREATE TEMP TABLE dashboard_insight_reason_semantics AS
                WITH selected_units AS MATERIALIZED (
                    SELECT r.result_version_id, r.classification_key,
                           COUNT(*) AS record_count
                    FROM {scope.records_table} r
                    JOIN dashboard_insight_selected_records selected
                      ON selected.id = r.id
                    WHERE {where_sql}
                    GROUP BY r.result_version_id, r.classification_key
                )
                SELECT unit.result_version_id, unit.classification_key, selected.record_count,
                       COALESCE(
                           NULLIF(unit.part, ''),
                           'UNSPECIFIED'
                       ) AS part,
                       unit.opinion, unit.subject, unit.evidence
                FROM selected_units selected
                JOIN classification_unit_semantics unit
                  ON unit.result_version_id = selected.result_version_id
                 AND unit.classification_key = selected.classification_key
                WHERE unit.label_code = ?
                  {"AND unit.subject = ?" if scope.clean_subject else ""}
                """,
            (*params, selected_code, scope.clean_subject)
            if scope.clean_subject
            else (*params, selected_code),
        )
        semantic_rows = connection.execute(
            """
                WITH matched AS MATERIALIZED (
                    SELECT result_version_id, classification_key, part, opinion, subject,
                           MAX(record_count) AS record_count, MAX(evidence) AS evidence
                    FROM dashboard_insight_reason_semantics
                    GROUP BY result_version_id, classification_key, part, opinion, subject
                ),
                part_units AS (
                    SELECT result_version_id, classification_key, part,
                           MAX(record_count) AS record_count
                    FROM matched
                    GROUP BY result_version_id, classification_key, part
                ),
                part_counts AS (
                    SELECT part AS value, SUM(record_count) AS record_count
                    FROM part_units
                    GROUP BY part
                    ORDER BY record_count DESC, value ASC
                    LIMIT 6
                ),
                opinion_counts AS (
                    SELECT opinion, subject, part,
                           SUM(record_count) AS record_count,
                           MAX(evidence) AS evidence
                    FROM matched
                    WHERE NULLIF(opinion, '') IS NOT NULL
                    GROUP BY opinion, subject, part
                    ORDER BY record_count DESC, opinion ASC
                    LIMIT 4
                ),
                matched_units AS (
                    SELECT result_version_id, classification_key,
                           MAX(record_count) AS record_count
                    FROM matched
                    GROUP BY result_version_id, classification_key
                )
                SELECT 'total' AS kind, NULL AS value, NULL AS subject,
                       NULL AS part, COALESCE(SUM(record_count), 0) AS record_count,
                       NULL AS evidence
                FROM matched_units
                UNION ALL
                SELECT 'part', value, NULL, NULL, record_count, NULL
                FROM part_counts
                UNION ALL
                SELECT 'opinion', opinion, subject, part, record_count, evidence
                FROM opinion_counts
                """,
        ).fetchall()
    semantic_record_count = int(semantic_rows[0]["record_count"])
    part_rows = sorted(
        (row for row in semantic_rows if row["kind"] == "part"),
        key=lambda row: (-int(row["record_count"]), str(row["value"])),
    )
    semantic_parts = [
        {
            "value": str(row["value"]),
            "record_count": int(row["record_count"]),
            "percentage": percentage(int(row["record_count"]), semantic_record_count),
        }
        for row in part_rows
    ]
    opinion_rows = sorted(
        (row for row in semantic_rows if row["kind"] == "opinion"),
        key=lambda row: (-int(row["record_count"]), str(row["value"])),
    )
    semantic_opinions = [
        {
            "opinion": row["value"],
            "subject": row["subject"],
            "part": row["part"],
            "record_count": int(row["record_count"]),
            "evidence": row["evidence"],
        }
        for row in opinion_rows
    ]
    return semantic_parts, semantic_opinions, semantic_record_count
