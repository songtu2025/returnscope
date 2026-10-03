"""洞察对象分布与原因对象关联统计。"""

from __future__ import annotations

from typing import Any

from web_backend.dashboard_common import SUBJECT_LABELS
from web_backend.dashboard_insight_scope import (
    InsightQueryScope,
    prepare_scope_semantics,
)
from web_backend.dashboard_support import percentage


def _collect_semantic_breakdown(
    scope: InsightQueryScope, total_records: int
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    connection = scope.connection
    context = scope.context
    where_sql = scope.where_sql
    params = scope.params
    unit_rollup = scope.unit_rollup

    if unit_rollup:
        source_placeholders = ",".join("?" for _ in context["source_ids"])
        subject_rows = connection.execute(
            f"""
            WITH unit_subjects AS (
                SELECT DISTINCT u.id,
                       json_extract(unit.value, '$.subject') AS value,
                       u.record_count
                FROM classification_units u
                JOIN json_each(
                    u.classification_json,
                    '$.semantic_units'
                ) unit
                WHERE u.result_version_id IN ({source_placeholders})
                  AND u.quality_status = 'ready'
                  AND json_extract(unit.value, '$.subject') IS NOT NULL
            )
            SELECT value, SUM(record_count) AS record_count,
                   COUNT(*) AS semantic_unit_count
            FROM unit_subjects
            GROUP BY value
            ORDER BY record_count DESC, value ASC
            """,
            tuple(context["source_ids"]),
        ).fetchall()
    else:
        prepare_scope_semantics(
            connection, where_sql, params, records_table=scope.records_table
        )
        record_count = (
            "SUM(r.record_count)"
            if scope.records_table == "dashboard_insight_weighted_units"
            else "COUNT(*)"
        )
        semantic_rows = connection.execute(
            f"""
            WITH filtered_units AS MATERIALIZED (
                SELECT r.result_version_id, r.classification_key,
                       {record_count} AS record_count
                FROM {scope.records_table} r
                WHERE {where_sql}
                GROUP BY r.result_version_id, r.classification_key
            ),
            semantic_rows AS MATERIALIZED (
                SELECT filtered_units.result_version_id,
                       filtered_units.classification_key,
                       filtered_units.record_count,
                       unit.subject, unit.label_code
                FROM filtered_units
                JOIN dashboard_insight_scope_semantics unit
                  ON unit.result_version_id = filtered_units.result_version_id
                 AND unit.classification_key = filtered_units.classification_key
            ),
            subject_units AS (
                SELECT result_version_id, classification_key, subject,
                       MAX(record_count) AS record_count,
                       SUM(record_count) AS semantic_unit_count
                FROM semantic_rows
                WHERE subject IS NOT NULL
                GROUP BY result_version_id, classification_key, subject
            ),
            reason_subject_units AS (
                SELECT DISTINCT result_version_id, classification_key,
                       label_code, subject, record_count
                FROM semantic_rows
            )
            SELECT 'subject' AS kind, NULL AS label_code,
                   subject AS value, SUM(record_count) AS record_count,
                   SUM(semantic_unit_count) AS semantic_unit_count
            FROM subject_units
            GROUP BY subject
            UNION ALL
            SELECT 'reason_subject', reason_subject_units.label_code,
                   reason_subject_units.subject,
                   SUM(reason_subject_units.record_count), NULL
            FROM reason_subject_units
            JOIN classification_unit_labels l
              ON l.result_version_id = reason_subject_units.result_version_id
             AND l.classification_key = reason_subject_units.classification_key
             AND l.label_kind = 'problem'
             AND l.label_code = reason_subject_units.label_code
            GROUP BY reason_subject_units.label_code,
                     reason_subject_units.subject
            """,
            tuple(params),
        ).fetchall()
        subject_rows = sorted(
            (row for row in semantic_rows if row["kind"] == "subject"),
            key=lambda row: (-int(row["record_count"]), str(row["value"])),
        )
        reason_subject_rows = sorted(
            (
                {
                    "label_code": row["label_code"],
                    "subject": row["value"],
                    "record_count": row["record_count"],
                }
                for row in semantic_rows
                if row["kind"] == "reason_subject"
            ),
            key=lambda row: -int(row["record_count"]),
        )
    subject_breakdown = [
        {
            "value": str(row["value"]),
            "label": SUBJECT_LABELS.get(str(row["value"]), str(row["value"])),
            "record_count": int(row["record_count"]),
            "semantic_unit_count": int(row["semantic_unit_count"]),
            "percentage": percentage(int(row["record_count"]), total_records),
        }
        for row in subject_rows
    ]
    if unit_rollup:
        reason_subject_rows = connection.execute(
            f"""
            WITH unit_subjects AS (
                SELECT DISTINCT u.id,
                       json_extract(unit.value, '$.label_code') AS label_code,
                       json_extract(unit.value, '$.subject') AS subject,
                       u.record_count
                FROM classification_units u
                JOIN json_each(
                    u.classification_json,
                    '$.semantic_units'
                ) unit
                WHERE u.result_version_id IN ({source_placeholders})
                  AND u.quality_status = 'ready'
                  AND json_extract(unit.value, '$.label_code') IS NOT NULL
            )
            SELECT label_code, subject,
                   SUM(record_count) AS record_count
            FROM unit_subjects
            GROUP BY label_code, subject
            ORDER BY record_count DESC
            """,
            tuple(context["source_ids"]),
        ).fetchall()
    reason_subjects: dict[str, list[str]] = {}
    for row in reason_subject_rows:
        reason_subjects.setdefault(str(row["label_code"]), []).append(
            str(row["subject"])
        )
    return subject_breakdown, reason_subjects


def collect_subject_breakdown(scope: InsightQueryScope) -> list[dict[str, Any]]:
    total_records = int(
        scope.connection.execute(
            f"SELECT COUNT(*) FROM {scope.records_table} r WHERE {scope.where_sql}",
            tuple(scope.params),
        ).fetchone()[0]
    )
    return _collect_semantic_breakdown(scope, total_records)[0]
