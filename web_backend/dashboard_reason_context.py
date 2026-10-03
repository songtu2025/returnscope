"""洞察原因查询、标签目录与范围计数。"""

from __future__ import annotations

import sqlite3
from typing import Any

from web_backend.dashboard_insight_scope import InsightQueryScope, subject_label_filter
from web_backend.request_timing import timed_stage


def _label_catalog(
    scope: InsightQueryScope, reason_rows: list[sqlite3.Row]
) -> tuple[dict[str, str], dict[str, int]]:
    connection = scope.connection
    where_sql = scope.where_sql
    params = scope.params
    clean_group = scope.clean_group

    if clean_group:
        label_name_rows = connection.execute(
            f"""
            SELECT l.label_code,
                   COALESCE(NULLIF(TRIM(l.label_name), ''), l.label_code)
                       AS label,
                   COUNT(DISTINCT r.id) AS record_count
            FROM {scope.records_table} r
            JOIN classification_unit_labels l
              ON l.result_version_id = r.result_version_id
             AND l.classification_key = r.classification_key
             AND l.label_kind = 'problem'
             {subject_label_filter(scope, "r", "l")}
            WHERE {where_sql}
            GROUP BY l.label_code, l.label_name
            """,
            tuple(params),
        ).fetchall()
    else:
        grouped_labels: dict[tuple[str, str | None], dict[str, Any]] = {}
        for row in reason_rows:
            key = (str(row["value"]), row["raw_label_name"])
            if key not in grouped_labels:
                grouped_labels[key] = {
                    "label_code": key[0],
                    "label": str(row["label"]),
                    "record_count": 0,
                }
            grouped_labels[key]["record_count"] += int(row["record_count"])
        label_name_rows = [
            grouped_labels[key]
            for key in sorted(
                grouped_labels,
                key=lambda item: (item[0], item[1] is not None, item[1] or ""),
            )
        ]
    label_names = {str(row["label_code"]): str(row["label"]) for row in label_name_rows}
    label_counts = {
        str(row["label_code"]): int(row["record_count"]) for row in label_name_rows
    }
    return label_names, label_counts


def _reason_rows(
    scope: InsightQueryScope, *, include_primary: bool = True, weighted: bool = False
) -> list[sqlite3.Row]:
    where_sql = scope.where_sql
    clean_group = scope.clean_group
    report_mode = scope.report_mode
    reason_group_filter = ""
    reason_params = list(scope.params)
    record_count = "SUM(r.record_count)" if weighted else "COUNT(r.id)"
    primary_weight = "r.record_count" if weighted else "1"
    if clean_group:
        reason_group_filter = (
            " AND aligned_group(l.label_group, l.label_code, r.result_version_id) = ?"
        )
        reason_params.append(clean_group)
    if report_mode or not include_primary:
        units_join = (
            ""
            if report_mode
            else """JOIN classification_units u
              ON u.result_version_id = r.result_version_id
             AND u.classification_key = r.classification_key"""
        )
        reason_sql = f"""
            SELECT l.label_code AS value,
                   COALESCE(NULLIF(TRIM(l.label_name), ''), l.label_code)
                       AS label,
                   l.label_name AS raw_label_name,
                   aligned_group(l.label_group, l.label_code, r.result_version_id)
                       AS label_group,
                   {record_count} AS record_count,
                   NULL AS primary_record_count
            FROM {scope.records_table} r
            JOIN classification_unit_labels l
              ON l.result_version_id = r.result_version_id
             AND l.classification_key = r.classification_key
             AND l.label_kind = 'problem'
             {subject_label_filter(scope, "r", "l")}
            {units_join}
            WHERE {where_sql}{reason_group_filter}
            GROUP BY l.label_code, l.label_name, label_group
            ORDER BY record_count DESC, label COLLATE NOCASE ASC
        """
    else:
        reason_sql = f"""
        SELECT l.label_code AS value,
               COALESCE(NULLIF(TRIM(l.label_name), ''), l.label_code) AS label,
               l.label_name AS raw_label_name,
               aligned_group(l.label_group, l.label_code, r.result_version_id) AS label_group,
               {record_count} AS record_count,
               SUM(CASE WHEN EXISTS (
                   SELECT 1
                   FROM classification_unit_labels primary_label
                   WHERE primary_label.result_version_id = r.result_version_id
                     AND primary_label.classification_key = r.classification_key
                     AND primary_label.label_kind = 'primary'
                     AND primary_label.label_code = l.label_code
               ) THEN {primary_weight} ELSE 0 END) AS primary_record_count
        FROM {scope.records_table} r
        JOIN classification_unit_labels l
          ON l.result_version_id = r.result_version_id
         AND l.classification_key = r.classification_key
         AND l.label_kind = 'problem'
         {subject_label_filter(scope, "r", "l")}
        JOIN classification_units u
          ON u.result_version_id = r.result_version_id
         AND u.classification_key = r.classification_key
        WHERE {where_sql}{reason_group_filter}
        GROUP BY l.label_code, l.label_name, label_group
        ORDER BY record_count DESC, label COLLATE NOCASE ASC
        """
    return scope.connection.execute(reason_sql, tuple(reason_params)).fetchall()


@timed_stage("insight_reason_context")
def collect_reason_context(scope: InsightQueryScope) -> dict[str, Any]:
    total_records = int(
        scope.connection.execute(
            f"SELECT COUNT(*) FROM {scope.records_table} r WHERE {scope.where_sql}",
            tuple(scope.params),
        ).fetchone()[0]
    )
    reason_rows = _reason_rows(scope, include_primary=False)
    _, label_counts = _label_catalog(scope, reason_rows)
    selected = next(
        (row for row in reason_rows if row["value"] == scope.requested_problem),
        reason_rows[0] if reason_rows else None,
    )
    return {
        "total_records": total_records,
        "label_counts": label_counts,
        "selected_reason": (
            {
                "value": str(selected["value"]),
                "record_count": int(selected["record_count"]),
            }
            if selected
            else None
        ),
    }


def collect_label_counts(scope: InsightQueryScope) -> tuple[int, int]:
    row = scope.connection.execute(
        f"""
        SELECT COUNT(*), COALESCE(SUM(EXISTS (
            SELECT 1 FROM classification_unit_labels label
            WHERE label.result_version_id = r.result_version_id
              AND label.classification_key = r.classification_key
              AND label.label_kind = 'problem'
              {subject_label_filter(scope, "r", "label")}
        )), 0)
        FROM {scope.records_table} r
        WHERE {scope.where_sql}
        """,
        tuple(scope.params),
    ).fetchone()
    return int(row[0]), int(row[1])
