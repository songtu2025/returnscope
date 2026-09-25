from __future__ import annotations

from typing import Any, cast

from return_semantics.schemas import TaxonomyConfig
from web_backend.dashboard_insight_overview import InsightQueryScope
from web_backend.dashboard_support import percentage, serialize_record


def collect_reason_details(
    scope: InsightQueryScope,
    selected_reason: dict[str, Any] | None,
    overview: dict[str, Any],
    taxonomy: TaxonomyConfig | None = None,
) -> dict[str, Any]:
    connection = scope.connection
    where_sql = scope.where_sql
    params = scope.params
    total_records = int(overview["total_records"])
    label_counts = cast(dict[str, int], overview["label_counts"])
    label_names = cast(dict[str, str], overview["label_names"])

    trend: list[dict[str, Any]] = []
    products: list[dict[str, Any]] = []
    variants: list[dict[str, Any]] = []
    co_reasons: list[dict[str, Any]] = []
    semantic_parts: list[dict[str, Any]] = []
    semantic_opinions: list[dict[str, Any]] = []
    semantic_record_count = 0
    evidence_items: list[dict[str, Any]] = []
    evidence_total = 0
    if selected_reason:
        selected_code = str(selected_reason["value"])
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
                   COUNT(r.id) AS total_record_count,
                   SUM(CASE WHEN EXISTS (
                       SELECT 1 FROM classification_unit_labels selected
                       WHERE selected.result_version_id = r.result_version_id
                         AND selected.classification_key = r.classification_key
                         AND selected.label_kind = 'problem'
                         AND selected.label_code = ?
                   ) THEN 1 ELSE 0 END) AS record_count
            FROM classification_result_records r
            WHERE {where_sql} AND r.return_date IS NOT NULL
            GROUP BY period_start, period_end
            ORDER BY period_start
            """,
            (selected_code, *params),
        ).fetchall()
        trend = [
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
        product_rows = connection.execute(
            f"""
            SELECT COALESCE(NULLIF(TRIM(r.product_name), ''), '未提供产品')
                       AS value,
                   COUNT(r.id) AS total_record_count,
                   SUM(CASE WHEN EXISTS (
                       SELECT 1 FROM classification_unit_labels selected
                       WHERE selected.result_version_id = r.result_version_id
                         AND selected.classification_key = r.classification_key
                         AND selected.label_kind = 'problem'
                         AND selected.label_code = ?
                   ) THEN 1 ELSE 0 END) AS record_count
            FROM classification_result_records r
            WHERE {where_sql}
            GROUP BY value
            HAVING record_count > 0
            ORDER BY record_count DESC, value COLLATE NOCASE ASC
            LIMIT 8
            """,
            (selected_code, *params),
        ).fetchall()
        selected_count = int(selected_reason["record_count"])
        products = [
            {
                "value": row["value"],
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
                "reliable": int(row["total_record_count"]) >= 15,
            }
            for row in product_rows
        ]
        variant_rows = connection.execute(
            f"""
            SELECT COALESCE(NULLIF(TRIM(r.product_sku), ''), '未提供 SKU')
                       AS value,
                   COALESCE(NULLIF(TRIM(r.product_name), ''), '未提供产品')
                       AS product_name,
                   COUNT(r.id) AS total_record_count,
                   SUM(CASE WHEN EXISTS (
                       SELECT 1 FROM classification_unit_labels selected
                       WHERE selected.result_version_id = r.result_version_id
                         AND selected.classification_key = r.classification_key
                         AND selected.label_kind = 'problem'
                         AND selected.label_code = ?
                   ) THEN 1 ELSE 0 END) AS record_count
            FROM classification_result_records r
            WHERE {where_sql}
            GROUP BY value, product_name
            HAVING record_count > 0
            ORDER BY record_count DESC, value COLLATE NOCASE ASC
            LIMIT 12
            """,
            (selected_code, *params),
        ).fetchall()
        variants = [
            {
                "value": str(row["value"]),
                "product_name": str(row["product_name"]),
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
                "reliable": int(row["total_record_count"]) >= 10,
            }
            for row in variant_rows
        ]
        co_reason_rows = connection.execute(
            f"""
            SELECT other.label_code AS value,
                   COALESCE(NULLIF(TRIM(other.label_name), ''),
                            other.label_code) AS label,
                   COUNT(r.id) AS record_count
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
            WHERE {where_sql}
            GROUP BY other.label_code, other.label_name
            ORDER BY record_count DESC, label COLLATE NOCASE ASC
            LIMIT 6
            """,
            (selected_code, selected_code, *params),
        ).fetchall()
        co_reasons = [
            {
                **dict(row),
                "record_count": int(row["record_count"]),
                "percentage": percentage(int(row["record_count"]), selected_count),
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
        semantic_record_count = int(
            connection.execute(
                f"""
                SELECT COUNT(DISTINCT r.id)
                FROM classification_result_records r
                JOIN classification_units u
                  ON u.result_version_id = r.result_version_id
                 AND u.classification_key = r.classification_key
                JOIN json_each(
                    u.classification_json,
                    '$.semantic_units'
                ) unit
                WHERE {where_sql}
                  AND json_extract(unit.value, '$.label_code') = ?
                """,
                (*params, selected_code),
            ).fetchone()[0]
        )
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
            JOIN json_each(
                u.classification_json,
                '$.semantic_units'
            ) unit
            WHERE {where_sql}
              AND json_extract(unit.value, '$.label_code') = ?
            GROUP BY COALESCE(
                NULLIF(json_extract(unit.value, '$.part'), ''),
                'UNSPECIFIED'
            )
            ORDER BY record_count DESC, value ASC
            LIMIT 6
            """,
            (*params, selected_code),
        ).fetchall()
        semantic_parts = [
            {
                "value": str(row["value"]),
                "record_count": int(row["record_count"]),
                "percentage": percentage(
                    int(row["record_count"]), semantic_record_count
                ),
            }
            for row in part_rows
        ]
        opinion_rows = connection.execute(
            f"""
            SELECT json_extract(unit.value, '$.opinion') AS opinion,
                   json_extract(unit.value, '$.subject') AS subject,
                   COALESCE(
                       NULLIF(json_extract(unit.value, '$.part'), ''),
                       'UNSPECIFIED'
                   ) AS part,
                   COUNT(DISTINCT r.id) AS record_count,
                   MAX(json_extract(unit.value, '$.evidence')) AS evidence
            FROM classification_result_records r
            JOIN classification_units u
              ON u.result_version_id = r.result_version_id
             AND u.classification_key = r.classification_key
            JOIN json_each(
                u.classification_json,
                '$.semantic_units'
            ) unit
            WHERE {where_sql}
              AND json_extract(unit.value, '$.label_code') = ?
              AND NULLIF(json_extract(unit.value, '$.opinion'), '')
                  IS NOT NULL
            GROUP BY opinion, subject, part
            ORDER BY record_count DESC, opinion ASC
            LIMIT 4
            """,
            (*params, selected_code),
        ).fetchall()
        semantic_opinions = [
            {
                **dict(row),
                "record_count": int(row["record_count"]),
            }
            for row in opinion_rows
        ]
        evidence_total = selected_count
        evidence_rows = connection.execute(
            f"""
            SELECT r.*, u.processing_status, u.problem_labels_json,
                   u.classification_json
            FROM classification_result_records r
            JOIN classification_units u
              ON u.result_version_id = r.result_version_id
             AND u.classification_key = r.classification_key
            WHERE {where_sql}
              AND EXISTS (
                  SELECT 1 FROM classification_unit_labels selected
                  WHERE selected.result_version_id = r.result_version_id
                    AND selected.classification_key = r.classification_key
                    AND selected.label_kind = 'problem'
                    AND selected.label_code = ?
              )
            ORDER BY datetime(r.return_date) DESC,
                     r.source_row DESC, r.id ASC
            LIMIT 4
            """,
            (*params, selected_code),
        ).fetchall()
        evidence_items = [
            serialize_record(dict(row), taxonomy) for row in evidence_rows
        ]
        for item in evidence_items:
            item["problem_labels"] = [
                label_names.get(str(label), str(label))
                for label in item["problem_labels"]
            ]

    return {
        "trend": trend,
        "products": products,
        "variants": variants,
        "co_reasons": co_reasons,
        "semantic_parts": semantic_parts,
        "semantic_opinions": semantic_opinions,
        "semantic_record_count": semantic_record_count,
        "evidence_items": evidence_items,
        "evidence_total": evidence_total,
    }
