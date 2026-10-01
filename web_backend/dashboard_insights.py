from __future__ import annotations

import sqlite3
from dataclasses import dataclass, replace
from typing import Any

from return_semantics.schemas import SubjectCode, TaxonomyConfig
from return_semantics.taxonomy import aligned_label_group
from web_backend.dashboard_insight_details import (
    EVIDENCE_PAGE_SIZE,
    collect_reason_details,
    list_reason_evidence,
)
from web_backend.dashboard_insight_overview import (
    InsightQueryScope,
    collect_insight_overview,
    collect_label_counts,
    collect_reason_context,
    collect_subject_breakdown,
    prepare_scope_semantics,
)
from web_backend.dashboard_plan import comment_summary_metrics
from web_backend.dashboard_support import (
    clean_date,
    feedback_group_scope,
    mixed_hierarchy,
    normalize_filters,
    percentage,
    record_where,
    validate_page,
    version_context,
)
from web_backend.database import Database
from web_backend.request_timing import timed_stage
from web_backend.result_hierarchy import hierarchy_counts, result_taxonomy

INSIGHT_PAGE_CACHE_KIB = 64 * 1024


@dataclass(frozen=True)
class InsightOptions:
    problem: str | None = None
    subject: str | None = None
    label_group: str | None = None
    listing: str | None = None
    product_name: str | None = None
    product_sku: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    report_mode: bool = False


@dataclass(frozen=True)
class PreparedInsightScope:
    scope: InsightQueryScope
    taxonomy: TaxonomyConfig | None
    mixed_versions: bool
    ungrouped_where: str
    ungrouped_params: list[Any]
    comment_where: str
    comment_params: list[Any]
    facet_where: str
    facet_params: list[Any]


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


@timed_stage("insight_filter_options")
def _collect_filter_options(
    scope: InsightQueryScope, reuse_option_records: bool
) -> dict[str, list[str]]:
    columns = {
        "listings": "r.listing",
        "product_names": "r.product_name",
        "product_skus": "r.product_sku",
    }
    table = (
        scope.records_table if reuse_option_records else "classification_result_records"
    )
    where_sql = "1=1" if reuse_option_records else scope.option_where
    params = [] if reuse_option_records else scope.option_params
    materialization = "NOT MATERIALIZED" if reuse_option_records else "MATERIALIZED"
    queries = [
        f"SELECT DISTINCT '{key}' AS kind, {column} AS value "
        f"FROM option_records r WHERE {column} IS NOT NULL AND TRIM({column}) <> ''"
        for key, column in columns.items()
    ]
    # 原表只读取一次；已有临时范围则直接复用，保留去重和 SQLite 排序口径。
    rows = scope.connection.execute(
        f"""
        WITH option_records AS {materialization} (
            SELECT r.listing, r.product_name, r.product_sku
            FROM {table} r WHERE {where_sql}
        )
        {" UNION ALL ".join(queries)}
        ORDER BY kind, value COLLATE NOCASE ASC
        """,
        tuple(params),
    ).fetchall()
    options: dict[str, list[str]] = {key: [] for key in columns}
    for row in rows:
        options[str(row["kind"])].append(str(row["value"]))
    return options


@timed_stage("insight_scope")
def _prepare_scope(
    database: Database,
    connection: sqlite3.Connection,
    context: dict[str, Any],
    options: InsightOptions,
    *,
    include_options: bool = True,
) -> PreparedInsightScope:
    clean_date_from = clean_date(options.date_from)
    clean_date_to = clean_date(options.date_to)
    if clean_date_from and clean_date_to and clean_date_from > clean_date_to:
        raise ValueError("开始日期不能晚于结束日期")
    runtime_filters = normalize_filters(
        {
            "listing": options.listing,
            "product_name": options.product_name,
            "product_sku": options.product_sku,
        }
    )
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
    option_where, option_params = record_where(
        database, context["source_ids"], context["filters"]
    )
    where_sql, params = record_where(
        database, context["source_ids"], context["filters"], runtime_filters
    )
    comment_scope_filters = {
        key: value
        for key, value in context["filters"].items()
        if key != "quality_status"
    }
    comment_scope_where, comment_scope_params = record_where(
        database, context["source_ids"], comment_scope_filters, runtime_filters
    )
    for operator, value in ((">=", clean_date_from), ("<=", clean_date_to)):
        if value:
            date_filter = f" AND date(r.return_date) {operator} date(?)"
            where_sql += date_filter
            params.append(value)
            comment_scope_where += date_filter
            comment_scope_params.append(value)
    ungrouped_where = where_sql
    ungrouped_params = params
    if context["counting_basis"] == "feedback_group":
        (option_where, option_params), (where_sql, params) = _prepare_feedback_scopes(
            connection,
            (option_where, option_params),
            (where_sql, params),
            include_options,
        )
    facet_where, facet_params = where_sql, params.copy()
    clean_subject = (options.subject or "").strip()
    if clean_subject:
        if clean_subject not in {item.value for item in SubjectCode}:
            raise ValueError("问题对象不合法")
        _prepare_subject_labels(connection, where_sql, params, clean_subject)
        where_sql += (
            " AND EXISTS (SELECT 1 FROM dashboard_insight_subject_labels subject_label"
            " WHERE subject_label.result_version_id = r.result_version_id"
            " AND subject_label.classification_key = r.classification_key)"
        )
    unit_rollup = (
        options.report_mode
        and not clean_subject
        and not runtime_filters
        and not clean_date_from
        and not clean_date_to
        and not {key for key in context["filters"] if key != "quality_status"}
        and context["counting_basis"] != "feedback_group"
    )
    return PreparedInsightScope(
        scope=InsightQueryScope(
            connection=connection,
            context=context,
            where_sql=where_sql,
            params=params,
            option_where=option_where,
            option_params=option_params,
            unit_rollup=unit_rollup,
            clean_group=(options.label_group or "").strip(),
            clean_subject=clean_subject,
            requested_problem=(options.problem or "").strip(),
            report_mode=options.report_mode,
        ),
        taxonomy=taxonomy,
        mixed_versions=mixed_versions,
        ungrouped_where=ungrouped_where,
        ungrouped_params=ungrouped_params,
        comment_where=comment_scope_where,
        comment_params=comment_scope_params,
        facet_where=facet_where,
        facet_params=facet_params,
    )


@timed_stage("insight_feedback_groups")
def _prepare_feedback_scopes(
    connection: sqlite3.Connection,
    option_scope: tuple[str, list[Any]],
    current_scope: tuple[str, list[Any]],
    include_options: bool,
) -> tuple[tuple[str, list[Any]], tuple[str, list[Any]]]:
    """全屏准备选项与当前范围，详情和翻页只准备当前反馈范围。"""
    if not include_options:
        option_scope = current_scope
    grouped_options = feedback_group_scope(connection, *option_scope, name="options")
    grouped_current = (
        grouped_options
        if option_scope == current_scope
        else feedback_group_scope(connection, *current_scope, name="main")
    )
    return grouped_options, grouped_current


@timed_stage("insight_subject")
def _prepare_subject_labels(
    connection: sqlite3.Connection, where_sql: str, params: list[Any], subject: str
) -> None:
    prepare_scope_semantics(connection, where_sql, params)
    connection.execute(
        "CREATE TEMP TABLE dashboard_insight_subject_labels "
        "(result_version_id TEXT NOT NULL, classification_key TEXT NOT NULL, "
        "label_code TEXT NOT NULL, "
        "PRIMARY KEY (result_version_id, classification_key, label_code))"
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO dashboard_insight_subject_labels
        SELECT result_version_id, classification_key, label_code
        FROM dashboard_insight_scope_semantics
        WHERE subject = ? AND label_code IS NOT NULL
        """,
        (subject,),
    )


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
