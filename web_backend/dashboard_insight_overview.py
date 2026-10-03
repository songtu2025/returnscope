from __future__ import annotations

import sqlite3
from dataclasses import replace
from typing import Any

from web_backend.dashboard_insight_scope import (
    InsightQueryScope as InsightQueryScope,
)
from web_backend.dashboard_insight_scope import (
    prepare_scope_semantics as prepare_scope_semantics,
)
from web_backend.dashboard_insight_scope import (
    subject_label_filter as subject_label_filter,
)
from web_backend.dashboard_semantic_breakdown import (
    _collect_semantic_breakdown,
)
from web_backend.dashboard_semantic_breakdown import (
    collect_subject_breakdown as collect_subject_breakdown,
)
from web_backend.dashboard_support import percentage
from web_backend.request_timing import timed_stage


def _label_catalog(
    scope: InsightQueryScope, reason_rows: list[sqlite3.Row]
) -> tuple[dict[str, str], dict[str, int]]:
    connection = scope.connection
    where_sql = scope.where_sql
    params = scope.params
    clean_group = scope.clean_group

    if clean_group:
        label_name_rows = connection.execute(
            f"""
            SELECT l.label_code,
                   COALESCE(NULLIF(TRIM(l.label_name), ''), l.label_code)
                       AS label,
                   COUNT(DISTINCT r.id) AS record_count
            FROM {scope.records_table} r
            JOIN classification_unit_labels l
              ON l.result_version_id = r.result_version_id
             AND l.classification_key = r.classification_key
             AND l.label_kind = 'problem'
             {subject_label_filter(scope, "r", "l")}
            WHERE {where_sql}
            GROUP BY l.label_code, l.label_name
            """,
            tuple(params),
        ).fetchall()
    else:
        grouped_labels: dict[tuple[str, str | None], dict[str, Any]] = {}
        for row in reason_rows:
            key = (str(row["value"]), row["raw_label_name"])
            if key not in grouped_labels:
                grouped_labels[key] = {
                    "label_code": key[0],
                    "label": str(row["label"]),
                    "record_count": 0,
                }
            grouped_labels[key]["record_count"] += int(row["record_count"])
        label_name_rows = [
            grouped_labels[key]
            for key in sorted(
                grouped_labels,
                key=lambda item: (item[0], item[1] is not None, item[1] or ""),
            )
        ]
    label_names = {str(row["label_code"]): str(row["label"]) for row in label_name_rows}
    label_counts = {
        str(row["label_code"]): int(row["record_count"]) for row in label_name_rows
    }
    return label_names, label_counts


def _reason_rows(
    scope: InsightQueryScope, *, include_primary: bool = True, weighted: bool = False
) -> list[sqlite3.Row]:
    where_sql = scope.where_sql
    clean_group = scope.clean_group
    report_mode = scope.report_mode
    reason_group_filter = ""
    reason_params = list(scope.params)
    record_count = "SUM(r.record_count)" if weighted else "COUNT(r.id)"
    primary_weight = "r.record_count" if weighted else "1"
    if clean_group:
        reason_group_filter = (
            " AND aligned_group(l.label_group, l.label_code, r.result_version_id) = ?"
        )
        reason_params.append(clean_group)
    if report_mode or not include_primary:
        units_join = (
            ""
            if report_mode
            else """JOIN classification_units u
              ON u.result_version_id = r.result_version_id
             AND u.classification_key = r.classification_key"""
        )
        reason_sql = f"""
            SELECT l.label_code AS value,
                   COALESCE(NULLIF(TRIM(l.label_name), ''), l.label_code)
                       AS label,
                   l.label_name AS raw_label_name,
                   aligned_group(l.label_group, l.label_code, r.result_version_id)
                       AS label_group,
                   {record_count} AS record_count,
                   NULL AS primary_record_count
            FROM {scope.records_table} r
            JOIN classification_unit_labels l
              ON l.result_version_id = r.result_version_id
             AND l.classification_key = r.classification_key
             AND l.label_kind = 'problem'
             {subject_label_filter(scope, "r", "l")}
            {units_join}
            WHERE {where_sql}{reason_group_filter}
            GROUP BY l.label_code, l.label_name, label_group
            ORDER BY record_count DESC, label COLLATE NOCASE ASC
        """
    else:
        reason_sql = f"""
        SELECT l.label_code AS value,
               COALESCE(NULLIF(TRIM(l.label_name), ''), l.label_code) AS label,
               l.label_name AS raw_label_name,
               aligned_group(l.label_group, l.label_code, r.result_version_id) AS label_group,
               {record_count} AS record_count,
               SUM(CASE WHEN EXISTS (
                   SELECT 1
                   FROM classification_unit_labels primary_label
                   WHERE primary_label.result_version_id = r.result_version_id
                     AND primary_label.classification_key = r.classification_key
                     AND primary_label.label_kind = 'primary'
                     AND primary_label.label_code = l.label_code
               ) THEN {primary_weight} ELSE 0 END) AS primary_record_count
        FROM {scope.records_table} r
        JOIN classification_unit_labels l
          ON l.result_version_id = r.result_version_id
         AND l.classification_key = r.classification_key
         AND l.label_kind = 'problem'
         {subject_label_filter(scope, "r", "l")}
        JOIN classification_units u
          ON u.result_version_id = r.result_version_id
         AND u.classification_key = r.classification_key
        WHERE {where_sql}{reason_group_filter}
        GROUP BY l.label_code, l.label_name, label_group
        ORDER BY record_count DESC, label COLLATE NOCASE ASC
        """
    return scope.connection.execute(reason_sql, tuple(reason_params)).fetchall()


@timed_stage("insight_reason_context")
def collect_reason_context(scope: InsightQueryScope) -> dict[str, Any]:
    total_records = int(
        scope.connection.execute(
            f"SELECT COUNT(*) FROM {scope.records_table} r WHERE {scope.where_sql}",
            tuple(scope.params),
        ).fetchone()[0]
    )
    reason_rows = _reason_rows(scope, include_primary=False)
    _, label_counts = _label_catalog(scope, reason_rows)
    selected = next(
        (row for row in reason_rows if row["value"] == scope.requested_problem),
        reason_rows[0] if reason_rows else None,
    )
    return {
        "total_records": total_records,
        "label_counts": label_counts,
        "selected_reason": (
            {
                "value": str(selected["value"]),
                "record_count": int(selected["record_count"]),
            }
            if selected
            else None
        ),
    }


def collect_label_counts(scope: InsightQueryScope) -> tuple[int, int]:
    row = scope.connection.execute(
        f"""
        SELECT COUNT(*), COALESCE(SUM(EXISTS (
            SELECT 1 FROM classification_unit_labels label
            WHERE label.result_version_id = r.result_version_id
              AND label.classification_key = r.classification_key
              AND label.label_kind = 'problem'
              {subject_label_filter(scope, "r", "label")}
        )), 0)
        FROM {scope.records_table} r
        WHERE {scope.where_sql}
        """,
        tuple(scope.params),
    ).fetchone()
    return int(row[0]), int(row[1])


@timed_stage("insight_overview")
def collect_insight_overview(
    scope: InsightQueryScope, *, total_record_count: int | None = None
) -> dict[str, Any]:
    connection = scope.connection
    where_sql = scope.where_sql
    params = scope.params
    option_where = scope.option_where
    option_params = scope.option_params
    requested_problem = scope.requested_problem
    report_mode = scope.report_mode

    date_range = dict(
        connection.execute(
            f"""
            SELECT MIN(date(r.return_date)) AS date_from,
                   MAX(date(r.return_date)) AS date_to
            FROM classification_result_records r
            WHERE {option_where}
            """,
            tuple(option_params),
        ).fetchone()
    )
    total_records, labeled_record_count = collect_label_counts(scope)
    if total_record_count is not None:
        total_records = total_record_count
    # 只在首屏汇总中按分类单元加权，明细与翻页仍使用原反馈范围。
    connection.execute(
        f"""
        CREATE TEMP TABLE dashboard_insight_weighted_units AS
        SELECT r.result_version_id, r.classification_key,
               COUNT(*) AS record_count
        FROM {scope.records_table} r
        WHERE {where_sql}
        GROUP BY r.result_version_id, r.classification_key
        """,
        tuple(params),
    )
    weighted_scope = replace(
        scope,
        records_table="dashboard_insight_weighted_units",
        where_sql="1=1",
        params=[],
    )
    subject_breakdown, reason_subjects = _collect_semantic_breakdown(
        weighted_scope, total_records
    )
    group_rows = connection.execute(
        f"""
        WITH unit_groups AS (
            SELECT aligned_group(l.label_group, l.label_code, r.result_version_id) AS value,
                   MAX(r.record_count) AS record_count, MIN(l.rowid) AS label_order
            FROM dashboard_insight_weighted_units r
            JOIN classification_unit_labels l
              ON l.result_version_id = r.result_version_id
             AND l.classification_key = r.classification_key
             AND l.label_kind = 'problem'
             {subject_label_filter(scope, "r", "l")}
            GROUP BY r.result_version_id, r.classification_key, value
        )
        SELECT value, SUM(record_count) AS record_count
        FROM unit_groups
        GROUP BY value
        ORDER BY record_count DESC, MIN(label_order)
        """,
    ).fetchall()
    reason_rows = _reason_rows(weighted_scope, weighted=True)
    label_names, label_counts = _label_catalog(scope, reason_rows)
    reasons = [
        {
            **{
                key: value
                for key, value in dict(row).items()
                if key != "raw_label_name"
            },
            "record_count": int(row["record_count"]),
            "primary_record_count": (
                None if report_mode else int(row["primary_record_count"] or 0)
            ),
            "companion_only_count": (
                None
                if report_mode
                else int(row["record_count"]) - int(row["primary_record_count"] or 0)
            ),
            "primary_rate": (
                None
                if report_mode
                else percentage(
                    int(row["primary_record_count"] or 0),
                    int(row["record_count"]),
                )
            ),
            "subjects": reason_subjects.get(str(row["value"]), []),
            "percentage": percentage(int(row["record_count"]), total_records),
        }
        for row in reason_rows
    ]
    product_matrix_rows = connection.execute(
        f"""
        WITH filtered_records AS MATERIALIZED (
            SELECT r.id, r.result_version_id, r.classification_key,
                   r.product_name
            FROM {scope.records_table} r
            WHERE {where_sql}
        ),
        top_products AS (
            SELECT product_name AS value,
                   COUNT(*) AS total_record_count
            FROM filtered_records
            WHERE product_name IS NOT NULL
              AND TRIM(product_name) <> ''
            GROUP BY product_name
            ORDER BY total_record_count DESC, value COLLATE NOCASE ASC
            LIMIT 8
        )
        SELECT top_products.value,
               top_products.total_record_count,
               l.label_code,
               COUNT(DISTINCT filtered_records.id) AS record_count
        FROM top_products
        JOIN filtered_records
          ON filtered_records.product_name = top_products.value
        LEFT JOIN classification_unit_labels l
          ON l.result_version_id = filtered_records.result_version_id
         AND l.classification_key = filtered_records.classification_key
         AND l.label_kind = 'problem'
         {subject_label_filter(scope, "filtered_records", "l")}
        GROUP BY top_products.value, top_products.total_record_count,
                 l.label_code
        ORDER BY top_products.total_record_count DESC,
                 top_products.value COLLATE NOCASE ASC,
                 record_count DESC
        """,
        tuple(params),
    ).fetchall()
    product_reason_matrix: list[dict[str, Any]] = []
    products_by_name: dict[str, dict[str, Any]] = {}
    for row in product_matrix_rows:
        product_name_value = str(row["value"])
        product = products_by_name.get(product_name_value)
        if product is None:
            product = {
                "value": product_name_value,
                "total_record_count": int(row["total_record_count"]),
                "reliable": int(row["total_record_count"]) >= 15,
                "reason_rates": {},
            }
            products_by_name[product_name_value] = product
            product_reason_matrix.append(product)
        if row["label_code"] is None:
            continue
        label_code = str(row["label_code"])
        record_count = int(row["record_count"])
        product_rate = percentage(record_count, int(row["total_record_count"]))
        overall_count = label_counts.get(label_code, 0)
        product["reason_rates"][label_code] = {
            "label": label_names.get(label_code, label_code),
            "record_count": record_count,
            "percentage": product_rate,
            "lift": round(
                (record_count / int(row["total_record_count"]))
                / (overall_count / total_records),
                2,
            )
            if overall_count and total_records
            else 0.0,
        }
    selected_reason = (
        None
        if report_mode
        else next(
            (item for item in reasons if item["value"] == requested_problem),
            reasons[0] if reasons else None,
        )
    )

    return {
        "date_range": date_range,
        "total_records": total_records,
        "labeled_record_count": labeled_record_count,
        "subject_breakdown": subject_breakdown,
        "group_rows": group_rows,
        "label_names": label_names,
        "label_counts": label_counts,
        "reasons": reasons,
        "product_reason_matrix": product_reason_matrix,
        "selected_reason": selected_reason,
    }
