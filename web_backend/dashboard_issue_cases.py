from __future__ import annotations

from typing import Any

from web_backend.dashboard_issue_case_details import populate_issue_case_details
from web_backend.dashboard_support import (
    feedback_group_scope,
    record_where,
    version_context,
)
from web_backend.dashboards.issue_case_selection import select_issue_cases
from web_backend.dashboards.issue_case_statistics import (
    collect_case_baselines,
    collect_case_candidates,
    collect_case_total,
)
from web_backend.database import Database


def list_issue_cases(
    database: Database,
    dashboard_id: str,
    version_id: str,
    reason_codes: list[str],
    *,
    max_cases_per_reason: int = 3,
) -> list[dict[str, Any]]:
    clean_codes = list(
        dict.fromkeys(str(code).strip() for code in reason_codes if str(code).strip())
    )
    if not clean_codes:
        return []
    if not 1 <= max_cases_per_reason <= 10:
        raise ValueError("每个问题的案例数量必须在 1 到 10 之间")

    with database.connect() as connection:
        context = version_context(database, connection, dashboard_id, version_id)
        where_sql, params = record_where(
            database,
            context["source_ids"],
            context["filters"],
        )
        if context["counting_basis"] == "feedback_group":
            where_sql, params = feedback_group_scope(
                connection, where_sql, params, name="cases"
            )
        total_record_count = collect_case_total(connection, where_sql, params)
        if not total_record_count:
            return []
        overall_by_code = collect_case_baselines(
            connection, where_sql, params, clean_codes
        )
        if not overall_by_code:
            return []
        candidates = collect_case_candidates(connection, where_sql, params, clean_codes)
        selected_cases = select_issue_cases(
            candidates,
            overall_by_code,
            clean_codes,
            total_record_count,
            max_cases_per_reason,
        )
        return populate_issue_case_details(
            connection,
            selected_cases,
            where_sql,
            params,
        )
