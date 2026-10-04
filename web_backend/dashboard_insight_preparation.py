from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from return_semantics.schemas import SubjectCode, TaxonomyConfig
from return_semantics.taxonomy import aligned_label_group
from web_backend.dashboard_insight_scope import (
    InsightQueryScope,
    prepare_scope_semantics,
)
from web_backend.dashboard_support import (
    clean_date,
    feedback_group_scope,
    normalize_filters,
    record_where,
)
from web_backend.database import Database
from web_backend.request_timing import timed_stage
from web_backend.result_hierarchy import result_taxonomy


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


@timed_stage("insight_scope")
def _prepare_scope(
    database: Database,
    connection: sqlite3.Connection,
    context: dict[str, Any],
    options: InsightOptions,
    *,
    include_options: bool = True,
) -> PreparedInsightScope:
    clean_date_from, clean_date_to = _clean_date_range(options)
    runtime_filters = normalize_filters(
        {
            "listing": options.listing,
            "product_name": options.product_name,
            "product_sku": options.product_sku,
        }
    )
    taxonomy, mixed_versions = _prepare_taxonomy_alignment(connection, context)
    (option_where, option_params), (where_sql, params), comment_scope = _record_scopes(
        database, context, runtime_filters, (clean_date_from, clean_date_to)
    )
    comment_scope_where, comment_scope_params = comment_scope
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
    clean_subject, where_sql = _subject_scope(connection, where_sql, params, options)
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


def _clean_date_range(options: InsightOptions) -> tuple[str | None, str | None]:
    clean_date_from = clean_date(options.date_from)
    clean_date_to = clean_date(options.date_to)
    if clean_date_from and clean_date_to and clean_date_from > clean_date_to:
        raise ValueError("开始日期不能晚于结束日期")
    return clean_date_from, clean_date_to


def _prepare_taxonomy_alignment(
    connection: sqlite3.Connection, context: dict[str, Any]
) -> tuple[TaxonomyConfig | None, bool]:
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
    return taxonomy, mixed_versions


def _record_scopes(
    database: Database,
    context: dict[str, Any],
    runtime_filters: dict[str, list[str]],
    date_range: tuple[str | None, str | None],
) -> tuple[tuple[str, list[Any]], tuple[str, list[Any]], tuple[str, list[Any]]]:
    clean_date_from, clean_date_to = date_range
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
    return (
        (option_where, option_params),
        (where_sql, params),
        (comment_scope_where, comment_scope_params),
    )


def _subject_scope(
    connection: sqlite3.Connection,
    where_sql: str,
    params: list[Any],
    options: InsightOptions,
) -> tuple[str, str]:
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
    return clean_subject, where_sql
