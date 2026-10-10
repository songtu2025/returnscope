from __future__ import annotations

from dataclasses import replace
from typing import Any

from return_semantics.schemas import TaxonomyConfig
from web_backend.dashboard_insight_details import (
    _reason_detail_payload,
    collect_reason_details,
)
from web_backend.dashboard_insight_overview import (
    collect_label_counts,
    collect_reason_context,
    collect_subject_breakdown,
)
from web_backend.dashboard_insight_preparation import (
    InsightOptions,
    PreparedInsightScope,
)
from web_backend.dashboard_insight_scope import InsightQueryScope, subject_label_filter
from web_backend.dashboard_plan import comment_summary_metrics
from web_backend.dashboard_support import percentage
from web_backend.request_timing import timed_stage
from web_backend.result_hierarchy import hierarchy_counts


def collect_base_facets(
    prepared: PreparedInsightScope, part: str
) -> tuple[list[dict[str, Any]] | None, tuple[int, int] | None]:
    scope = prepared.scope
    base_scope = replace(
        scope,
        where_sql=prepared.facet_where,
        params=prepared.facet_params,
        clean_subject="",
    )
    facet_subjects = (
        collect_subject_breakdown(base_scope)
        if scope.clean_subject and part != "reason"
        else None
    )
    base_label_counts = (
        collect_label_counts(base_scope)
        if scope.clean_subject and part != "reason"
        else None
    )
    return facet_subjects, base_label_counts


def collect_overview_summary(
    prepared: PreparedInsightScope,
    context: dict[str, Any],
    options: InsightOptions,
    part: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    scope = prepared.scope
    connection = scope.connection
    taxonomy = prepared.taxonomy
    summary = dict(context["summary"])
    hierarchy_problems: list[dict[str, Any]] = []
    if part != "reason":
        if any(
            (
                options.listing,
                options.product_name,
                options.product_sku,
                options.date_from,
                options.date_to,
            )
        ) or not {
            "comment_count",
            "total_comment_count",
            "pending_review_comment_count",
            "comment_statuses",
        }.issubset(summary):
            summary.update(
                comment_summary_metrics(
                    connection,
                    prepared.ungrouped_where,
                    prepared.ungrouped_params,
                    prepared.comment_where,
                    prepared.comment_params,
                    feedback_groups=context["counting_basis"] == "feedback_group",
                )
            )
        # 与原因榜单限制到相同标签，父级仍由原有集合算法去重。
        hierarchy_where = scope.where_sql + subject_label_filter(scope, "r", "l")
        hierarchy_params = scope.params.copy()
        if scope.clean_group:
            hierarchy_where += " AND aligned_group(l.label_group, l.label_code, r.result_version_id) = ?"
            hierarchy_params.append(scope.clean_group)
        hierarchy_problems = (
            hierarchy_counts(connection, taxonomy, hierarchy_where, hierarchy_params)
            if taxonomy and taxonomy.structure_version == 2
            else []
        )
    return summary, hierarchy_problems


def materialize_insight_records(scope: InsightQueryScope) -> InsightQueryScope:
    connection = scope.connection
    with timed_stage("insight_records"):
        connection.execute(
            f"""
        CREATE TEMP TABLE dashboard_insight_records AS
        SELECT r.id, r.result_version_id, r.classification_key,
               r.return_date, r.listing, r.product_name, r.product_sku
        FROM classification_result_records r
        WHERE {scope.where_sql}
        """,
            tuple(scope.params),
        )
    scope = replace(
        scope,
        where_sql="1=1",
        params=[],
        records_table="dashboard_insight_records",
    )
    return scope


def collect_reason_payload(
    scope: InsightQueryScope, taxonomy: TaxonomyConfig | None
) -> dict[str, Any]:
    reason_context = collect_reason_context(scope)
    reason_selected = reason_context["selected_reason"]
    reason_details = collect_reason_details(
        scope, reason_selected, reason_context, taxonomy
    )
    return {
        "selected_reason": reason_selected,
        **_reason_detail_payload(reason_details, reason_selected),
    }


def apply_overview_facets(
    overview: dict[str, Any],
    summary: dict[str, Any],
    facet_subjects: list[dict[str, Any]] | None,
    base_label_counts: tuple[int, int] | None,
) -> None:
    base_total, base_labeled = base_label_counts or (
        overview["total_records"],
        overview["labeled_record_count"],
    )
    summary["label_coverage"] = percentage(base_labeled, base_total)
    if facet_subjects is not None:
        overview["subject_breakdown"] = facet_subjects
