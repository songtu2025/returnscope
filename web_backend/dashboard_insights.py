from __future__ import annotations

from dataclasses import replace
from typing import Any

from web_backend.dashboard_insight_details import (
    EVIDENCE_PAGE_SIZE,
    _reason_detail_payload,
    collect_reason_details,
    list_reason_evidence,
)
from web_backend.dashboard_insight_overview import (
    collect_insight_overview,
    collect_label_counts,
    collect_reason_context,
    collect_subject_breakdown,
)
from web_backend.dashboard_insight_preparation import (
    InsightOptions as InsightOptions,
)
from web_backend.dashboard_insight_preparation import (
    _collect_filter_options,
    _prepare_scope,
)
from web_backend.dashboard_insight_preparation import (
    _prepare_subject_labels as _prepare_subject_labels,
)
from web_backend.dashboard_plan import comment_summary_metrics
from web_backend.dashboard_support import (
    mixed_hierarchy,
    percentage,
    validate_page,
    version_context,
)
from web_backend.database import Database
from web_backend.request_timing import timed_stage
from web_backend.result_hierarchy import hierarchy_counts

INSIGHT_PAGE_CACHE_KIB = 64 * 1024


@timed_stage("insight_build")
def build_insights(
    database: Database,
    dashboard_id: str,
    version_id: str,
    options: InsightOptions,
    *,
    part: str = "full",
) -> dict[str, Any]:
    if part not in {"full", "overview", "reason"}:
        raise ValueError("不支持的洞察数据部分")
    with database.connect() as connection:
        # 仅本次洞察查询扩大页面缓存，连接关闭后释放。
        connection.execute(f"PRAGMA cache_size = -{INSIGHT_PAGE_CACHE_KIB}")
        context = version_context(database, connection, dashboard_id, version_id)
        if mixed_hierarchy(connection, context["sources"]):
            return {
                "dashboard_id": dashboard_id,
                "version_id": version_id,
                "analysis_context": context["analysis_context"],
                "hierarchy_conflict": True,
                "message": "该看板包含不同层级标准版本，请按标准版本分别建立看板。",
                "reasons": [],
                "hierarchy_problems": [],
            }
        prepared = _prepare_scope(
            database, connection, context, options, include_options=part != "reason"
        )
        scope = prepared.scope
        taxonomy = prepared.taxonomy
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
        summary = dict(context["summary"])
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
            hierarchy_problems = (
                hierarchy_counts(connection, taxonomy, scope.where_sql, scope.params)
                if taxonomy and taxonomy.structure_version == 2
                else []
            )
        reuse_option_records = (
            scope.option_where == scope.where_sql
            and scope.option_params == scope.params
        )
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
        if part == "reason":
            reason_context = collect_reason_context(scope)
            reason_selected = reason_context["selected_reason"]
            reason_details = collect_reason_details(
                scope, reason_selected, reason_context, taxonomy
            )
            return {
                "selected_reason": reason_selected,
                **_reason_detail_payload(reason_details, reason_selected),
            }
        overview = collect_insight_overview(scope)
        # 顶部指标统一使用基础范围，对象和原因筛选只影响下方诊断。
        base_total, base_labeled = base_label_counts or (
            overview["total_records"],
            overview["labeled_record_count"],
        )
        summary["label_coverage"] = percentage(base_labeled, base_total)
        if facet_subjects is not None:
            overview["subject_breakdown"] = facet_subjects
        selected_reason = overview["selected_reason"]
        details = (
            collect_reason_details(scope, selected_reason, overview, taxonomy)
            if part == "full"
            else None
        )

        filter_options = _collect_filter_options(scope, reuse_option_records)

    date_range = overview["date_range"]
    total_records = int(overview["total_records"])
    labeled_record_count = int(overview["labeled_record_count"])
    subject_breakdown = overview["subject_breakdown"]
    group_rows = overview["group_rows"]
    reasons = overview["reasons"]
    product_reason_matrix = overview["product_reason_matrix"]
    return {
        "dashboard_id": dashboard_id,
        "version_id": version_id,
        "analysis_context": context["analysis_context"],
        "counting_basis": context["counting_basis"],
        "summary": summary,
        "group_alignment": "unified-v1"
        if prepared.mixed_versions
        and not (taxonomy and taxonomy.structure_version == 2)
        else "original",
        "hierarchy_problems": hierarchy_problems,
        "taxonomy": taxonomy.model_dump(mode="json") if taxonomy else None,
        "counting_note": (
            "按反馈组在每个分组内去重；多标签占比之和可能超过100%。"
            if context["counting_basis"] == "feedback_group"
            else "按原始记录在每个分组内去重；多标签占比之和可能超过100%。"
        ),
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
        **(_reason_detail_payload(details, selected_reason) if details else {}),
    }


def build_evidence_page(
    database: Database,
    dashboard_id: str,
    version_id: str,
    options: InsightOptions,
    *,
    page: int = 1,
) -> dict[str, Any]:
    validate_page(page, EVIDENCE_PAGE_SIZE)
    selected_code = (options.problem or "").strip()
    if not selected_code:
        raise ValueError("问题原因不能为空")
    with database.connect() as connection:
        context = version_context(database, connection, dashboard_id, version_id)
        if mixed_hierarchy(connection, context["sources"]):
            raise ValueError("该看板包含不同层级标准版本")
        prepared = _prepare_scope(
            database, connection, context, options, include_options=False
        )
        return list_reason_evidence(
            prepared.scope, selected_code, prepared.taxonomy, page=page
        )


def build_report_diagnostics(
    database: Database,
    dashboard_id: str,
    version_id: str,
    reason_codes: list[str],
) -> list[dict[str, Any]]:
    with database.connect() as connection:
        context = version_context(database, connection, dashboard_id, version_id)
        if mixed_hierarchy(connection, context["sources"]):
            return []
        prepared = _prepare_scope(database, connection, context, InsightOptions())
        overview = collect_insight_overview(prepared.scope)
        reasons = overview["reasons"]
        diagnostics = []
        for code in reason_codes:
            selected_reason = next(
                (reason for reason in reasons if reason["value"] == code),
                reasons[0] if reasons else None,
            )
            details = collect_reason_details(
                prepared.scope, selected_reason, overview, prepared.taxonomy
            )
            diagnostics.append(
                {
                    "date_range": overview["date_range"],
                    "selected_reason": selected_reason,
                    **_reason_detail_payload(details, selected_reason),
                }
            )
        return diagnostics
