from __future__ import annotations

from typing import Any

from web_backend.dashboard_insight_details import (
    EVIDENCE_PAGE_SIZE,
    _reason_detail_payload,
    collect_reason_details,
    list_reason_evidence,
)
from web_backend.dashboard_insight_overview import (
    collect_insight_overview,
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
from web_backend.dashboard_support import (
    mixed_hierarchy,
    validate_page,
    version_context,
)
from web_backend.dashboards.insight_payloads import (
    OverviewContent,
    hierarchy_conflict_payload,
    overview_payload,
)
from web_backend.dashboards.insight_queries import (
    apply_overview_facets,
    collect_base_facets,
    collect_overview_summary,
    collect_reason_payload,
    materialize_insight_records,
)
from web_backend.database import Database
from web_backend.request_timing import timed_stage

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
            return hierarchy_conflict_payload(dashboard_id, version_id, context)
        prepared = _prepare_scope(
            database, connection, context, options, include_options=part != "reason"
        )
        scope = prepared.scope
        facet_subjects, base_label_counts = collect_base_facets(prepared, part)
        summary, hierarchy_problems = collect_overview_summary(
            prepared, context, options, part
        )
        reuse_option_records = (
            scope.option_where == scope.where_sql
            and scope.option_params == scope.params
        )
        scope = materialize_insight_records(scope)
        if part == "reason":
            return collect_reason_payload(scope, prepared.taxonomy)
        overview = collect_insight_overview(scope)
        # 顶部指标统一使用基础范围，对象和原因筛选只影响下方诊断。
        apply_overview_facets(overview, summary, facet_subjects, base_label_counts)
        selected_reason = overview["selected_reason"]
        details = (
            collect_reason_details(scope, selected_reason, overview, prepared.taxonomy)
            if part == "full"
            else None
        )
        filter_options = _collect_filter_options(scope, reuse_option_records)
        content = OverviewContent(
            overview, summary, hierarchy_problems, details, filter_options
        )
    return overview_payload(dashboard_id, version_id, context, prepared, content)


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
