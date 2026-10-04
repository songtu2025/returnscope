from __future__ import annotations

import sqlite3
from typing import Any

from web_backend.dashboard_issue_case_samples import list_issue_case_samples
from web_backend.dashboards.issue_case_detail_statistics import (
    collect_case_co_reasons,
    collect_case_trend,
)
from web_backend.dashboards.issue_case_semantics import collect_case_semantics


def populate_issue_case_details(
    connection: sqlite3.Connection,
    cases: list[dict[str, Any]],
    where_sql: str,
    params: list[Any],
) -> list[dict[str, Any]]:
    for case in cases:
        code = str(case["reason_code"])
        product_name = str(case["product_name"])
        product_sku = str(case["product_sku"])
        case_where = (
            f"{where_sql} AND TRIM(r.product_name) = ? AND TRIM(r.product_sku) = ?"
        )
        case_params = (*params, product_name, product_sku)
        case["trend"] = collect_case_trend(connection, code, case_where, case_params)
        case["co_reasons"] = collect_case_co_reasons(
            connection, case, code, case_where, case_params
        )
        case["semantic_profile"] = collect_case_semantics(
            connection, case, code, case_where, case_params
        )
        case["samples"] = list_issue_case_samples(
            connection, case, case_where, case_params
        )
    return cases
