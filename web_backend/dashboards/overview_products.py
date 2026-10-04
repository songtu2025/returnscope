from __future__ import annotations

import sqlite3
from typing import Any

from web_backend.dashboard_insight_scope import InsightQueryScope, subject_label_filter
from web_backend.dashboard_support import percentage


def _product_matrix_rows(scope: InsightQueryScope) -> list[sqlite3.Row]:
    connection = scope.connection
    where_sql = scope.where_sql
    params = scope.params
    return connection.execute(
        f"""
        WITH filtered_records AS MATERIALIZED (
            SELECT r.id, r.result_version_id, r.classification_key,
                   r.product_name
            FROM {scope.records_table} r
            WHERE {where_sql}
        ),
        top_products AS (
            SELECT product_name AS value,
                   COUNT(*) AS total_record_count
            FROM filtered_records
            WHERE product_name IS NOT NULL
              AND TRIM(product_name) <> ''
            GROUP BY product_name
            ORDER BY total_record_count DESC, value COLLATE NOCASE ASC
            LIMIT 8
        )
        SELECT top_products.value,
               top_products.total_record_count,
               l.label_code,
               COUNT(DISTINCT filtered_records.id) AS record_count
        FROM top_products
        JOIN filtered_records
          ON filtered_records.product_name = top_products.value
        LEFT JOIN classification_unit_labels l
          ON l.result_version_id = filtered_records.result_version_id
         AND l.classification_key = filtered_records.classification_key
         AND l.label_kind = 'problem'
         {subject_label_filter(scope, "filtered_records", "l")}
        GROUP BY top_products.value, top_products.total_record_count,
                 l.label_code
        ORDER BY top_products.total_record_count DESC,
                 top_products.value COLLATE NOCASE ASC,
                 record_count DESC
        """,
        tuple(params),
    ).fetchall()


def collect_product_reason_matrix(
    scope: InsightQueryScope,
    total_records: int,
    label_names: dict[str, str],
    label_counts: dict[str, int],
) -> list[dict[str, Any]]:
    product_matrix_rows = _product_matrix_rows(scope)
    product_reason_matrix: list[dict[str, Any]] = []
    products_by_name: dict[str, dict[str, Any]] = {}
    for row in product_matrix_rows:
        product_name_value = str(row["value"])
        product = products_by_name.get(product_name_value)
        if product is None:
            product = {
                "value": product_name_value,
                "total_record_count": int(row["total_record_count"]),
                "reliable": int(row["total_record_count"]) >= 15,
                "reason_rates": {},
            }
            products_by_name[product_name_value] = product
            product_reason_matrix.append(product)
        if row["label_code"] is None:
            continue
        label_code = str(row["label_code"])
        record_count = int(row["record_count"])
        product_rate = percentage(record_count, int(row["total_record_count"]))
        overall_count = label_counts.get(label_code, 0)
        product["reason_rates"][label_code] = {
            "label": label_names.get(label_code, label_code),
            "record_count": record_count,
            "percentage": product_rate,
            "lift": round(
                (record_count / int(row["total_record_count"]))
                / (overall_count / total_records),
                2,
            )
            if overall_count and total_records
            else 0.0,
        }
    return product_reason_matrix
