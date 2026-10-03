from __future__ import annotations

import sqlite3
from typing import Any

from web_backend.dashboard_common import TEXT_ENCODING_ANOMALY


def list_issue_case_samples(
    connection: sqlite3.Connection,
    case: dict[str, Any],
    case_where: str,
    case_params: tuple[Any, ...],
) -> list[dict[str, Any]]:
    code = str(case["reason_code"])
    product_name = str(case["product_name"])
    product_sku = str(case["product_sku"])
    sample_rows = connection.execute(
        f"""
            WITH samples AS (
                SELECT r.classification_key, r.comment, r.reason,
                       COUNT(*) AS record_count,
                       MAX(r.return_date) AS latest_return_date,
                       MAX(CASE WHEN EXISTS (
                           SELECT 1
                           FROM json_each(
                               u.classification_json,
                               '$.semantic_units'
                           ) semantic
                           WHERE json_extract(
                               semantic.value,
                               '$.label_code'
                           ) = ?
                             AND UPPER(COALESCE(
                                 NULLIF(json_extract(
                                     semantic.value,
                                     '$.part'
                                 ), ''),
                                 'UNSPECIFIED'
                             )) <> 'UNSPECIFIED'
                       ) THEN 1 ELSE 0 END) AS has_specific_part
                FROM classification_result_records r
                JOIN classification_units u
                  ON u.result_version_id = r.result_version_id
                 AND u.classification_key = r.classification_key
                JOIN classification_unit_labels selected
                  ON selected.result_version_id = r.result_version_id
                 AND selected.classification_key = r.classification_key
                 AND selected.label_kind = 'problem'
                 AND selected.label_code = ?
                WHERE {case_where}
                GROUP BY r.classification_key, r.comment, r.reason
            )
            SELECT * FROM samples
            ORDER BY has_specific_part DESC,
                     record_count DESC,
                     LENGTH(COALESCE(comment, reason, '')) DESC,
                     classification_key ASC
            LIMIT 12
            """,
        (code, code, *case_params),
    ).fetchall()
    samples = []
    for row in sample_rows:
        if has_text_anomaly(row["comment"], row["reason"]):
            continue
        samples.append(
            {
                "classification_key": str(row["classification_key"]),
                "comment": row["comment"],
                "reason": row["reason"],
                "product_name": product_name,
                "product_sku": product_sku,
                "record_count": int(row["record_count"]),
                "latest_return_date": row["latest_return_date"],
                "has_specific_part": bool(row["has_specific_part"]),
            }
        )
        if len(samples) >= 6:
            break
    return samples


def has_text_anomaly(*values: Any) -> bool:
    return any(TEXT_ENCODING_ANOMALY.search(str(value)) for value in values if value)
