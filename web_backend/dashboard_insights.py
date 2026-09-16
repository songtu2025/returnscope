from __future__ import annotations

from typing import Any

from return_semantics.taxonomy import aligned_label_group
from web_backend.dashboard_insight_details import collect_reason_details
from web_backend.dashboard_insight_overview import (
    InsightQueryScope,
    collect_insight_overview,
)
from web_backend.dashboard_plan import comment_summary_metrics, summarize_sources
from web_backend.dashboard_support import (
    clean_date,
    mixed_hierarchy,
    normalize_filters,
    percentage,
    record_where,
    version_context,
)
from web_backend.database import Database
from web_backend.result_hierarchy import hierarchy_counts, result_taxonomy


def build_insights(
    database: Database,
    dashboard_id: str,
    version_id: str,
    *,
    problem: str | None = None,
    label_group: str | None = None,
    listing: str | None = None,
    product_name: str | None = None,
    product_sku: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    report_mode: bool = False,
) -> dict[str, Any]:
    clean_date_from = clean_date(date_from)
    clean_date_to = clean_date(date_to)
    if clean_date_from and clean_date_to and clean_date_from > clean_date_to:
        raise ValueError("开始日期不能晚于结束日期")
    runtime_filters = normalize_filters(
        {
            "listing": listing,
            "product_name": product_name,
            "product_sku": product_sku,
        }
    )
    clean_group = (label_group or "").strip()
    requested_problem = (problem or "").strip()
    with database.connect() as connection:
        context = version_context(database, connection, dashboard_id, version_id)
        if mixed_hierarchy(connection, context["sources"]):
            return {
                "dashboard_id": dashboard_id,
                "version_id": version_id,
                "hierarchy_conflict": True,
                "message": "该看板包含不同层级标准版本，请按标准版本分别建立看板。",
                "reasons": [],
                "hierarchy_problems": [],
            }
        taxonomy = (
            result_taxonomy(connection, context["source_ids"][0])
            if context["source_ids"]
            else None
        )
        source_taxonomies = {
            source["result_version_id"]: source for source in context["sources"]
        }
        mixed_versions = (
            len(
                {
                    (source["agent_key"], source["taxonomy_version"])
                    for source in context["sources"]
                }
            )
            > 1
        )

        def group_for_result(group, code, result_id):
            source = source_taxonomies.get(result_id, {})
            original = group or "其他原因"
            if not mixed_versions or (taxonomy and taxonomy.structure_version == 2):
                return original
            return aligned_label_group(
                source.get("agent_key", ""),
                source.get("taxonomy_version", ""),
                code,
                original,
            )

        connection.create_function("aligned_group", 3, group_for_result)
        summary = summarize_sources(
            database,
            connection,
            context["source_ids"],
            context["filters"],
            context["sources"],
        )
        option_where, option_params = record_where(
            database,
            context["source_ids"],
            context["filters"],
        )
        where_sql, params = record_where(
            database,
            context["source_ids"],
            context["filters"],
            runtime_filters,
        )
        if clean_date_from:
            where_sql += " AND date(r.return_date) >= date(?)"
            params.append(clean_date_from)
        if clean_date_to:
            where_sql += " AND date(r.return_date) <= date(?)"
            params.append(clean_date_to)
        comment_scope_filters = {
            key: value
            for key, value in context["filters"].items()
            if key != "quality_status"
        }
        comment_scope_where, comment_scope_params = record_where(
            database,
            context["source_ids"],
            comment_scope_filters,
            runtime_filters,
        )
        if clean_date_from:
            comment_scope_where += " AND date(r.return_date) >= date(?)"
            comment_scope_params.append(clean_date_from)
        if clean_date_to:
            comment_scope_where += " AND date(r.return_date) <= date(?)"
            comment_scope_params.append(clean_date_to)
        summary.update(
            comment_summary_metrics(
                connection,
                where_sql,
                params,
                comment_scope_where,
                comment_scope_params,
            )
        )
        hierarchy_problems = (
            hierarchy_counts(connection, taxonomy, where_sql, params)
            if taxonomy and taxonomy.structure_version == 2
            else []
        )
        unit_rollup = (
            report_mode
            and not runtime_filters
            and not clean_date_from
            and not clean_date_to
            and not {key for key in context["filters"] if key != "quality_status"}
        )
        scope = InsightQueryScope(
            connection=connection,
            context=context,
            where_sql=where_sql,
            params=params,
            option_where=option_where,
            option_params=option_params,
            unit_rollup=unit_rollup,
            clean_group=clean_group,
            requested_problem=requested_problem,
            report_mode=report_mode,
        )
        overview = collect_insight_overview(scope)
        selected_reason = overview["selected_reason"]
        details = collect_reason_details(scope, selected_reason, overview)

        filter_options = {}
        for key, column in (
            ("listings", "r.listing"),
            ("product_names", "r.product_name"),
            ("product_skus", "r.product_sku"),
        ):
            rows = connection.execute(
                f"""
                            SELECT DISTINCT {column} AS value
                            FROM classification_result_records r
                            WHERE {option_where}
                              AND {column} IS NOT NULL
                              AND TRIM({column}) <> ''
                            ORDER BY value COLLATE NOCASE ASC
                            """,
                tuple(option_params),
            ).fetchall()
            filter_options[key] = [str(row["value"]) for row in rows]

    date_range = overview["date_range"]
    total_records = int(overview["total_records"])
    labeled_record_count = int(overview["labeled_record_count"])
    subject_breakdown = overview["subject_breakdown"]
    group_rows = overview["group_rows"]
    reasons = overview["reasons"]
    product_reason_matrix = overview["product_reason_matrix"]
    trend = details["trend"]
    products = details["products"]
    variants = details["variants"]
    co_reasons = details["co_reasons"]
    semantic_record_count = int(details["semantic_record_count"])
    semantic_parts = details["semantic_parts"]
    semantic_opinions = details["semantic_opinions"]
    evidence_items = details["evidence_items"]
    evidence_total = int(details["evidence_total"])

    return {
        "dashboard_id": dashboard_id,
        "version_id": version_id,
        "summary": summary,
        "group_alignment": "unified-v1"
        if mixed_versions and not (taxonomy and taxonomy.structure_version == 2)
        else "original",
        "hierarchy_problems": hierarchy_problems,
        "taxonomy": taxonomy.model_dump(mode="json") if taxonomy else None,
        "counting_note": "按原始记录在每个分组内去重；多标签占比之和可能超过100%。",
        "date_range": date_range,
        "filter_options": filter_options,
        "category_groups": [str(row["value"]) for row in group_rows],
        "label_group_breakdown": [
            {
                "value": str(row["value"]),
                "record_count": int(row["record_count"]),
                "percentage": percentage(int(row["record_count"]), total_records),
            }
            for row in group_rows
        ],
        "total_record_count": total_records,
        "labeled_record_count": labeled_record_count,
        "label_coverage": percentage(labeled_record_count, total_records),
        "subject_breakdown": subject_breakdown,
        "reasons": reasons,
        "product_reason_matrix": product_reason_matrix,
        "selected_reason": selected_reason,
        "trend": trend,
        "products": products,
        "variants": variants,
        "co_reasons": co_reasons,
        "semantic_profile": {
            "record_count": semantic_record_count,
            "coverage": percentage(
                semantic_record_count,
                int(selected_reason["record_count"]) if selected_reason else 0,
            ),
            "parts": semantic_parts,
            "opinions": semantic_opinions,
        },
        "evidence": {
            "items": evidence_items,
            "total": evidence_total,
        },
    }
