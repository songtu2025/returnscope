from __future__ import annotations

import sqlite3
from typing import Any

from web_backend.dashboard_issue_case_samples import list_issue_case_samples
from web_backend.dashboard_support import percentage


def populate_issue_case_details(
    connection: sqlite3.Connection,
    cases: list[dict[str, Any]],
    where_sql: str,
    params: list[Any],
) -> list[dict[str, Any]]:
    for case in cases:
        code = str(case["reason_code"])
        product_name = str(case["product_name"])
        product_sku = str(case["product_sku"])
        case_where = (
            f"{where_sql} AND TRIM(r.product_name) = ? AND TRIM(r.product_sku) = ?"
        )
        case_params = (*params, product_name, product_sku)

        trend_rows = connection.execute(
            f"""
            SELECT date(
                       r.return_date,
                       '-' || ((CAST(strftime('%w', r.return_date) AS INTEGER)
                       + 6) % 7) || ' days'
                   ) AS period_start,
                   date(
                       r.return_date,
                       '-' || ((CAST(strftime('%w', r.return_date) AS INTEGER)
                       + 6) % 7) || ' days',
                       '+6 days'
                   ) AS period_end,
                   COUNT(*) AS total_record_count,
                   SUM(CASE WHEN EXISTS (
                       SELECT 1 FROM classification_unit_labels selected
                       WHERE selected.result_version_id = r.result_version_id
                         AND selected.classification_key = r.classification_key
                         AND selected.label_kind = 'problem'
                         AND selected.label_code = ?
                   ) THEN 1 ELSE 0 END) AS record_count
            FROM classification_result_records r
            WHERE {case_where} AND r.return_date IS NOT NULL
            GROUP BY period_start, period_end
            ORDER BY period_start
            """,
            (code, *case_params),
        ).fetchall()
        case["trend"] = [
            {
                "period_start": row["period_start"],
                "period_end": row["period_end"],
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

        co_reason_rows = connection.execute(
            f"""
            SELECT other.label_code AS value,
                   COALESCE(NULLIF(TRIM(other.label_name), ''),
                            other.label_code) AS label,
                   COUNT(DISTINCT r.id) AS record_count
            FROM classification_result_records r
            JOIN classification_unit_labels selected
              ON selected.result_version_id = r.result_version_id
             AND selected.classification_key = r.classification_key
             AND selected.label_kind = 'problem'
             AND selected.label_code = ?
            JOIN classification_unit_labels other
              ON other.result_version_id = r.result_version_id
             AND other.classification_key = r.classification_key
             AND other.label_kind = 'problem'
             AND other.label_code <> ?
            WHERE {case_where}
            GROUP BY other.label_code, other.label_name
            ORDER BY record_count DESC, label COLLATE NOCASE ASC
            LIMIT 6
            """,
            (code, code, *case_params),
        ).fetchall()
        case["co_reasons"] = [
            {
                "value": str(row["value"]),
                "label": str(row["label"]),
                "record_count": int(row["record_count"]),
                "percentage": percentage(
                    int(row["record_count"]),
                    int(case["record_count"]),
                ),
            }
            for row in co_reason_rows
        ]

        semantic_row = connection.execute(
            f"""
            SELECT COUNT(DISTINCT r.id) AS record_count,
                   COUNT(DISTINCT CASE
                       WHEN UPPER(COALESCE(
                           NULLIF(json_extract(unit.value, '$.part'), ''),
                           'UNSPECIFIED'
                       )) <> 'UNSPECIFIED'
                       THEN r.id
                   END) AS specified_part_record_count
            FROM classification_result_records r
            JOIN classification_units u
              ON u.result_version_id = r.result_version_id
             AND u.classification_key = r.classification_key
            JOIN json_each(u.classification_json, '$.semantic_units') unit
            WHERE {case_where}
              AND json_extract(unit.value, '$.label_code') = ?
            """,
            (*case_params, code),
        ).fetchone()
        semantic_count = int(semantic_row["record_count"] or 0)
        specified_count = int(semantic_row["specified_part_record_count"] or 0)
        part_rows = connection.execute(
            f"""
            SELECT COALESCE(
                       NULLIF(json_extract(unit.value, '$.part'), ''),
                       'UNSPECIFIED'
                   ) AS value,
                   COUNT(DISTINCT r.id) AS record_count
            FROM classification_result_records r
            JOIN classification_units u
              ON u.result_version_id = r.result_version_id
             AND u.classification_key = r.classification_key
            JOIN json_each(u.classification_json, '$.semantic_units') unit
            WHERE {case_where}
              AND json_extract(unit.value, '$.label_code') = ?
            GROUP BY value
            ORDER BY record_count DESC, value ASC
            LIMIT 6
            """,
            (*case_params, code),
        ).fetchall()
        opinion_rows = connection.execute(
            f"""
            SELECT json_extract(unit.value, '$.opinion') AS opinion,
                   json_extract(unit.value, '$.subject') AS subject,
                   COALESCE(
                       NULLIF(json_extract(unit.value, '$.part'), ''),
                       'UNSPECIFIED'
                   ) AS part,
                   COUNT(DISTINCT r.id) AS record_count,
                   MIN(json_extract(unit.value, '$.evidence')) AS evidence
            FROM classification_result_records r
            JOIN classification_units u
              ON u.result_version_id = r.result_version_id
             AND u.classification_key = r.classification_key
            JOIN json_each(u.classification_json, '$.semantic_units') unit
            WHERE {case_where}
              AND json_extract(unit.value, '$.label_code') = ?
              AND NULLIF(json_extract(unit.value, '$.opinion'), '') IS NOT NULL
            GROUP BY opinion, subject, part
            ORDER BY record_count DESC, opinion ASC
            LIMIT 6
            """,
            (*case_params, code),
        ).fetchall()
        case["semantic_profile"] = {
            "record_count": semantic_count,
            "coverage": percentage(
                semantic_count,
                int(case["record_count"]),
            ),
            "specified_part_record_count": specified_count,
            "specified_part_coverage": percentage(
                specified_count,
                semantic_count,
            ),
            "parts": [
                {
                    "value": str(row["value"]),
                    "record_count": int(row["record_count"]),
                    "percentage": percentage(
                        int(row["record_count"]),
                        semantic_count,
                    ),
                }
                for row in part_rows
            ],
            "opinions": [
                {
                    "opinion": str(row["opinion"]),
                    "subject": row["subject"],
                    "part": str(row["part"]),
                    "record_count": int(row["record_count"]),
                    "evidence": row["evidence"],
                }
                for row in opinion_rows
            ],
        }

        case["samples"] = list_issue_case_samples(
            connection, case, case_where, case_params
        )
    return cases
