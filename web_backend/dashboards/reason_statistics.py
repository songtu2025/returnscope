from __future__ import annotations

from typing import Any

from web_backend.dashboard_insight_scope import InsightQueryScope, subject_label_filter
from web_backend.dashboard_support import percentage
from web_backend.request_timing import timed_stage


def prepare_selected_records(scope: InsightQueryScope, selected_code: str) -> None:
    connection = scope.connection
    where_sql = scope.where_sql
    params = scope.params
    connection.execute(
        "CREATE TEMP TABLE IF NOT EXISTS dashboard_insight_selected_records "
        "(id TEXT PRIMARY KEY)"
    )
    connection.execute("DELETE FROM dashboard_insight_selected_records")
    connection.execute(
        f"""
        INSERT INTO dashboard_insight_selected_records(id)
        SELECT DISTINCT r.id
        FROM {scope.records_table} r
        JOIN classification_unit_labels selected
          ON selected.result_version_id = r.result_version_id
         AND selected.classification_key = r.classification_key
         AND selected.label_kind = 'problem'
         AND selected.label_code = ?
         {subject_label_filter(scope, "r", "selected")}
        WHERE {where_sql}
        """,
        (selected_code, *params),
    )


def collect_trend(scope: InsightQueryScope) -> list[dict[str, Any]]:
    connection = scope.connection
    where_sql = scope.where_sql
    params = scope.params
    with timed_stage("insight_trend"):
        trend_rows = connection.execute(
            f"""
            SELECT date(r.return_date, 'weekday 0', '-6 days') AS period_start,
                   date(r.return_date, 'weekday 0') AS period_end,
                   COUNT(r.id) AS total_record_count,
                   SUM(CASE WHEN matched.id IS NOT NULL
                            THEN 1 ELSE 0 END) AS record_count
            FROM {scope.records_table} r
            LEFT JOIN dashboard_insight_selected_records matched
              ON matched.id = r.id
            WHERE {where_sql} AND r.return_date IS NOT NULL
            GROUP BY period_start, period_end
            ORDER BY period_start
            """,
            tuple(params),
        ).fetchall()
    return [
        {
            **dict(row),
            "record_count": int(row["record_count"] or 0),
            "total_record_count": int(row["total_record_count"] or 0),
            "percentage": percentage(
                int(row["record_count"] or 0),
                int(row["total_record_count"] or 0),
            ),
            "low_sample": int(row["total_record_count"] or 0) < 10,
        }
        for row in trend_rows
    ]


def collect_co_reasons(
    scope: InsightQueryScope,
    selected_code: str,
    selected_count: int,
    total_records: int,
    label_counts: dict[str, int],
) -> list[dict[str, Any]]:
    connection = scope.connection
    where_sql = scope.where_sql
    params = scope.params
    with timed_stage("insight_co_reasons"):
        co_reason_rows = connection.execute(
            f"""
            SELECT other.label_code AS value,
                   COALESCE(NULLIF(TRIM(other.label_name), ''),
                            other.label_code) AS label,
                   COUNT(r.id) AS record_count
            FROM {scope.records_table} r
            JOIN dashboard_insight_selected_records selected
              ON selected.id = r.id
            JOIN classification_unit_labels other
              ON other.result_version_id = r.result_version_id
             AND other.classification_key = r.classification_key
             AND other.label_kind = 'problem'
             AND other.label_code <> ?
             {subject_label_filter(scope, "r", "other")}
            WHERE {where_sql}
            GROUP BY other.label_code, other.label_name
            ORDER BY record_count DESC, label COLLATE NOCASE ASC
            LIMIT 6
            """,
            (selected_code, *params),
        ).fetchall()
    return [
        {
            **dict(row),
            "record_count": int(row["record_count"]),
            "percentage": percentage(int(row["record_count"]), selected_count),
            "baseline_record_count": label_counts.get(str(row["value"]), 0),
            "lift": round(
                (int(row["record_count"]) / selected_count)
                / (label_counts.get(str(row["value"]), 0) / total_records),
                2,
            )
            if total_records and label_counts.get(str(row["value"]), 0)
            else 0.0,
        }
        for row in co_reason_rows
    ]
