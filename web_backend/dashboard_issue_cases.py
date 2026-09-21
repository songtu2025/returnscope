from __future__ import annotations

import hashlib
import sqlite3
from typing import Any

from web_backend.dashboard_common import TEXT_ENCODING_ANOMALY
from web_backend.dashboard_support import (
    feedback_group_scope,
    percentage,
    record_where,
    version_context,
)
from web_backend.database import Database


def list_issue_cases(
    database: Database,
    dashboard_id: str,
    version_id: str,
    reason_codes: list[str],
    *,
    max_cases_per_reason: int = 3,
) -> list[dict[str, Any]]:
    clean_codes = list(
        dict.fromkeys(str(code).strip() for code in reason_codes if str(code).strip())
    )
    if not clean_codes:
        return []
    if not 1 <= max_cases_per_reason <= 10:
        raise ValueError("每个问题的案例数量必须在 1 到 10 之间")

    with database.connect() as connection:
        context = version_context(database, connection, dashboard_id, version_id)
        where_sql, params = record_where(
            database,
            context["source_ids"],
            context["filters"],
        )
        if context["counting_basis"] == "feedback_group":
            where_sql, params = feedback_group_scope(
                connection, where_sql, params, name="cases"
            )
        placeholders = ",".join("?" for _ in clean_codes)
        total_record_count = int(
            connection.execute(
                f"SELECT COUNT(*) FROM classification_result_records r "
                f"WHERE {where_sql}",
                tuple(params),
            ).fetchone()[0]
        )
        if not total_record_count:
            return []

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
        overall_by_code: dict[str, dict[str, Any]] = {
            str(row["label_code"]): {
                "label": str(row["label"]),
                "label_group": str(row["label_group"]),
                "record_count": int(row["record_count"]),
            }
            for row in overall_rows
        }
        if not overall_by_code:
            return []

        candidate_rows = connection.execute(
            f"""
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
            """,
            (*params, *clean_codes),
        ).fetchall()

        cases_by_code: dict[str, list[dict[str, Any]]] = {
            code: [] for code in clean_codes
        }
        for row in candidate_rows:
            code = str(row["label_code"])
            overall = overall_by_code.get(code)
            if overall is None:
                continue
            record_count = int(row["record_count"])
            variant_total = int(row["total_record_count"])
            baseline = overall["record_count"] / total_record_count
            lift = round((record_count / variant_total) / baseline, 2)
            excess = round(record_count - variant_total * baseline)
            if variant_total < 10 or record_count < 10 or lift < 1.1 or excess <= 0:
                continue
            product_name = str(row["product_name"])
            product_sku = str(row["product_sku"])
            identity = f"{code}\x1f{product_name}\x1f{product_sku}"
            cases_by_code[code].append(
                {
                    "id": (
                        f"issue_case.{code}."
                        f"{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:12]}"
                    ),
                    "reason_code": code,
                    "label": overall["label"],
                    "label_group": overall["label_group"],
                    "product_name": product_name,
                    "product_sku": product_sku,
                    "record_count": record_count,
                    "total_record_count": variant_total,
                    "reason_record_count": overall["record_count"],
                    "reason_share": percentage(
                        record_count,
                        overall["record_count"],
                    ),
                    "issue_rate": percentage(
                        record_count,
                        variant_total,
                    ),
                    "overall_rate": percentage(
                        overall["record_count"],
                        total_record_count,
                    ),
                    "lift": lift,
                    "excess_record_count": excess,
                    "reliable": True,
                }
            )

        selected_cases = []
        for code in clean_codes:
            ranked = sorted(
                cases_by_code[code],
                key=lambda item: (
                    int(item["excess_record_count"]),
                    float(item["lift"]),
                    int(item["record_count"]),
                    str(item["product_name"]),
                    str(item["product_sku"]),
                ),
                reverse=True,
            )
            selected_cases.extend(ranked[:max_cases_per_reason])
        return populate_issue_case_details(
            connection,
            selected_cases,
            where_sql,
            params,
        )


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
        case["samples"] = samples
    return cases


def has_text_anomaly(*values: Any) -> bool:
    return any(TEXT_ENCODING_ANOMALY.search(str(value)) for value in values if value)
