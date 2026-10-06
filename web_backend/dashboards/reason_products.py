from __future__ import annotations

import sqlite3
from typing import Any

from web_backend.dashboard_insight_scope import InsightQueryScope
from web_backend.dashboard_support import percentage
from web_backend.dashboards.statistics_thresholds import (
    MIN_PRODUCT_RECORDS,
    MIN_VARIANT_RECORDS,
)
from web_backend.request_timing import timed_stage


def _product_metrics(
    row: sqlite3.Row,
    selected_count: int,
    total_records: int,
    minimum_sample: int,
) -> dict[str, Any]:
    return {
        "record_count": int(row["record_count"]),
        "total_record_count": int(row["total_record_count"]),
        "reason_share": percentage(int(row["record_count"]), selected_count),
        "product_reason_rate": percentage(
            int(row["record_count"]),
            int(row["total_record_count"]),
        ),
        "overall_reason_rate": percentage(selected_count, total_records),
        "lift": round(
            (int(row["record_count"]) / int(row["total_record_count"]))
            / (selected_count / total_records),
            2,
        )
        if total_records and selected_count
        else 0.0,
        "reliable": int(row["total_record_count"]) >= minimum_sample,
    }


def collect_products(
    scope: InsightQueryScope,
    selected_count: int,
    total_records: int,
) -> list[dict[str, Any]]:
    connection = scope.connection
    where_sql = scope.where_sql
    params = scope.params
    with timed_stage("insight_products"):
        product_rows = connection.execute(
            f"""
            SELECT COALESCE(NULLIF(TRIM(r.product_name), ''), '未提供产品')
                       AS value,
                   COUNT(r.id) AS total_record_count,
                   SUM(CASE WHEN matched.id IS NOT NULL
                            THEN 1 ELSE 0 END) AS record_count
            FROM {scope.records_table} r
            LEFT JOIN dashboard_insight_selected_records matched
              ON matched.id = r.id
            WHERE {where_sql}
            GROUP BY value
            HAVING record_count > 0
            ORDER BY record_count DESC, value COLLATE NOCASE ASC
            LIMIT 8
            """,
            tuple(params),
        ).fetchall()
    return [
        {
            "value": row["value"],
            **_product_metrics(row, selected_count, total_records, MIN_PRODUCT_RECORDS),
        }
        for row in product_rows
    ]


def collect_variants(
    scope: InsightQueryScope,
    selected_count: int,
    total_records: int,
) -> list[dict[str, Any]]:
    connection = scope.connection
    where_sql = scope.where_sql
    params = scope.params
    with timed_stage("insight_variants"):
        variant_rows = connection.execute(
            f"""
            SELECT COALESCE(NULLIF(TRIM(r.product_sku), ''), '未提供 SKU')
                       AS value,
                   COALESCE(NULLIF(TRIM(r.product_name), ''), '未提供产品')
                       AS product_name,
                   COUNT(r.id) AS total_record_count,
                   SUM(CASE WHEN matched.id IS NOT NULL
                            THEN 1 ELSE 0 END) AS record_count
            FROM {scope.records_table} r
            LEFT JOIN dashboard_insight_selected_records matched
              ON matched.id = r.id
            WHERE {where_sql}
            GROUP BY value, product_name
            HAVING record_count > 0
            ORDER BY record_count DESC, value COLLATE NOCASE ASC
            LIMIT 12
            """,
            tuple(params),
        ).fetchall()
    return [
        {
            "value": str(row["value"]),
            "product_name": str(row["product_name"]),
            **_product_metrics(row, selected_count, total_records, MIN_VARIANT_RECORDS),
        }
        for row in variant_rows
    ]
