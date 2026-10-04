from __future__ import annotations

import sqlite3
from dataclasses import replace
from typing import Any

from web_backend.dashboard_insight_scope import InsightQueryScope, subject_label_filter
from web_backend.dashboard_reason_context import _label_catalog, _reason_rows
from web_backend.dashboard_support import percentage


def collect_date_range(scope: InsightQueryScope) -> dict[str, Any]:
    connection = scope.connection
    option_where = scope.option_where
    option_params = scope.option_params
    return dict(
        connection.execute(
            f"""
            SELECT MIN(date(r.return_date)) AS date_from,
                   MAX(date(r.return_date)) AS date_to
            FROM classification_result_records r
            WHERE {option_where}
            """,
            tuple(option_params),
        ).fetchone()
    )


def prepare_weighted_scope(scope: InsightQueryScope) -> InsightQueryScope:
    connection = scope.connection
    where_sql = scope.where_sql
    params = scope.params
    # 首屏按分类单元加权；调用方的明细与翻页仍沿用原反馈范围。
    connection.execute(
        f"""
        CREATE TEMP TABLE dashboard_insight_weighted_units AS
        SELECT r.result_version_id, r.classification_key,
               COUNT(*) AS record_count
        FROM {scope.records_table} r
        WHERE {where_sql}
        GROUP BY r.result_version_id, r.classification_key
        """,
        tuple(params),
    )
    return replace(
        scope,
        records_table="dashboard_insight_weighted_units",
        where_sql="1=1",
        params=[],
    )


def collect_group_rows(scope: InsightQueryScope) -> list[sqlite3.Row]:
    connection = scope.connection
    return connection.execute(
        f"""
        WITH unit_groups AS (
            SELECT aligned_group(l.label_group, l.label_code, r.result_version_id) AS value,
                   MAX(r.record_count) AS record_count, MIN(l.rowid) AS label_order
            FROM dashboard_insight_weighted_units r
            JOIN classification_unit_labels l
              ON l.result_version_id = r.result_version_id
             AND l.classification_key = r.classification_key
             AND l.label_kind = 'problem'
             {subject_label_filter(scope, "r", "l")}
            GROUP BY r.result_version_id, r.classification_key, value
        )
        SELECT value, SUM(record_count) AS record_count
        FROM unit_groups
        GROUP BY value
        ORDER BY record_count DESC, MIN(label_order)
        """,
    ).fetchall()


def collect_reasons(
    scope: InsightQueryScope,
    weighted_scope: InsightQueryScope,
    total_records: int,
    reason_subjects: dict[str, list[str]],
) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, int]]:
    report_mode = scope.report_mode
    reason_rows = _reason_rows(weighted_scope, weighted=True)
    label_names, label_counts = _label_catalog(scope, reason_rows)
    reasons = [
        {
            **{
                key: value
                for key, value in dict(row).items()
                if key != "raw_label_name"
            },
            "record_count": int(row["record_count"]),
            "primary_record_count": (
                None if report_mode else int(row["primary_record_count"] or 0)
            ),
            "companion_only_count": (
                None
                if report_mode
                else int(row["record_count"]) - int(row["primary_record_count"] or 0)
            ),
            "primary_rate": (
                None
                if report_mode
                else percentage(
                    int(row["primary_record_count"] or 0),
                    int(row["record_count"]),
                )
            ),
            "subjects": reason_subjects.get(str(row["value"]), []),
            "percentage": percentage(int(row["record_count"]), total_records),
        }
        for row in reason_rows
    ]
    return reasons, label_names, label_counts
