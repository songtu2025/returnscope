from __future__ import annotations

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
from web_backend.dashboard_reason_context import (
    _label_catalog,
    _reason_rows,
)
from web_backend.dashboard_reason_context import (
    collect_label_counts as collect_label_counts,
)
from web_backend.dashboard_reason_context import (
    collect_reason_context as collect_reason_context,
)
from web_backend.dashboard_semantic_breakdown import (
    _collect_semantic_breakdown,
)
from web_backend.dashboard_semantic_breakdown import (
    collect_subject_breakdown as collect_subject_breakdown,
)
from web_backend.dashboard_support import percentage
from web_backend.request_timing import timed_stage


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
