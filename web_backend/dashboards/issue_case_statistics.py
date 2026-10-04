from __future__ import annotations

import sqlite3
from typing import Any

_CANDIDATE_SQL = """
WITH scoped_records AS (
    SELECT r.*,
           TRIM(r.product_name) AS case_product_name,
           TRIM(r.product_sku) AS case_product_sku
    FROM classification_result_records r
    WHERE {where_sql}
),
variant_totals AS (
    SELECT case_product_name, case_product_sku,
           COUNT(*) AS total_record_count
    FROM scoped_records
    WHERE case_product_name <> '' AND case_product_sku <> ''
    GROUP BY case_product_name, case_product_sku
),
case_counts AS (
    SELECT label.label_code,
           r.case_product_name AS product_name,
           r.case_product_sku AS product_sku,
           COUNT(*) AS record_count
    FROM scoped_records r
    JOIN classification_unit_labels label
      ON label.result_version_id = r.result_version_id
     AND label.classification_key = r.classification_key
     AND label.label_kind = 'problem'
    WHERE r.case_product_name <> ''
      AND r.case_product_sku <> ''
      AND label.label_code IN ({placeholders})
    GROUP BY label.label_code,
             r.case_product_name, r.case_product_sku
)
SELECT cases.*, totals.total_record_count
FROM case_counts cases
JOIN variant_totals totals
  ON totals.case_product_name = cases.product_name
 AND totals.case_product_sku = cases.product_sku
ORDER BY cases.label_code,
         cases.record_count DESC,
         cases.product_name COLLATE NOCASE ASC,
         cases.product_sku COLLATE NOCASE ASC
"""


def collect_case_total(
    connection: sqlite3.Connection, where_sql: str, params: list[Any]
) -> int:
    return int(
        connection.execute(
            f"SELECT COUNT(*) FROM classification_result_records r WHERE {where_sql}",
            tuple(params),
        ).fetchone()[0]
    )


def collect_case_baselines(
    connection: sqlite3.Connection,
    where_sql: str,
    params: list[Any],
    clean_codes: list[str],
) -> dict[str, dict[str, Any]]:
    placeholders = ",".join("?" for _ in clean_codes)
    overall_rows = connection.execute(
        f"""
        SELECT label.label_code,
               COALESCE(NULLIF(TRIM(MAX(label.label_name)), ''),
                        label.label_code) AS label,
               COALESCE(NULLIF(TRIM(MAX(label.label_group)), ''), '')
                   AS label_group,
               COUNT(DISTINCT r.id) AS record_count
        FROM classification_result_records r
        JOIN classification_unit_labels label
          ON label.result_version_id = r.result_version_id
         AND label.classification_key = r.classification_key
         AND label.label_kind = 'problem'
        WHERE {where_sql}
          AND label.label_code IN ({placeholders})
        GROUP BY label.label_code
        """,
        (*params, *clean_codes),
    ).fetchall()
    return {
        str(row["label_code"]): {
            "label": str(row["label"]),
            "label_group": str(row["label_group"]),
            "record_count": int(row["record_count"]),
        }
        for row in overall_rows
    }


def collect_case_candidates(
    connection: sqlite3.Connection,
    where_sql: str,
    params: list[Any],
    clean_codes: list[str],
) -> list[sqlite3.Row]:
    return connection.execute(
        _CANDIDATE_SQL.format(
            where_sql=where_sql, placeholders=",".join("?" for _ in clean_codes)
        ),
        (*params, *clean_codes),
    ).fetchall()
