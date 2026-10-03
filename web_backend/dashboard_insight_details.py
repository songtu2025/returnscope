from __future__ import annotations

from typing import Any, cast

from return_semantics.schemas import TaxonomyConfig
from web_backend.dashboard_insight_overview import (
    InsightQueryScope,
    subject_label_filter,
)
from web_backend.dashboard_reason_evidence import (
    EVIDENCE_PAGE_SIZE as EVIDENCE_PAGE_SIZE,
)
from web_backend.dashboard_reason_evidence import (
    list_reason_evidence as list_reason_evidence,
)
from web_backend.dashboard_reason_semantics import _collect_reason_semantics
from web_backend.dashboard_support import percentage
from web_backend.request_timing import timed_stage


@timed_stage("insight_reason_details")
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
        co_reasons = [
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
        semantic_parts, semantic_opinions, semantic_record_count = (
            _collect_reason_semantics(scope, selected_code)
        )
        evidence_total = selected_count
        evidence_items = list_reason_evidence(
            scope,
            selected_code,
            taxonomy,
            total=evidence_total,
        )["items"]

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


def _reason_detail_payload(
    details: dict[str, Any], selected_reason: dict[str, Any] | None
) -> dict[str, Any]:
    semantic_record_count = int(details["semantic_record_count"])
    return {
        "trend": details["trend"],
        "products": details["products"],
        "variants": details["variants"],
        "co_reasons": details["co_reasons"],
        "semantic_profile": {
            "record_count": semantic_record_count,
            "coverage": percentage(
                semantic_record_count,
                int(selected_reason["record_count"]) if selected_reason else 0,
            ),
            "parts": details["semantic_parts"],
            "opinions": details["semantic_opinions"],
        },
        "evidence": {
            "items": details["evidence_items"],
            "total": int(details["evidence_total"]),
            "page": 1,
            "page_size": EVIDENCE_PAGE_SIZE,
        },
    }
