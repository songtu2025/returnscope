from __future__ import annotations

from typing import Any

from web_backend.insight_reports.business_issue_context import (
    _business_cases,
    _case_issue_context,
    _diagnostic_issue_context,
)
from web_backend.insight_reports.business_issue_details import _build_business_issue
from web_backend.insight_reports.diagnostic_summary import (
    _compact_diagnostic as _compact_diagnostic,
)
from web_backend.insight_reports.diagnostic_summary import (
    _diagnostic_reason_codes as _diagnostic_reason_codes,
)
from web_backend.insight_reports.diagnostic_summary import (
    _product_mapping_check as _product_mapping_check,
)
from web_backend.insight_reports.diagnostic_summary import (
    _rank_hotspots as _rank_hotspots,
)
from web_backend.insight_reports.diagnostic_summary import (
    _trend_summary as _trend_summary,
)
from web_backend.insight_reports.diagnostic_text import (
    _filter_business_issue_text as _filter_business_issue_text,
)
from web_backend.insight_reports.diagnostic_text import (
    _filter_diagnostic_text as _filter_diagnostic_text,
)
from web_backend.insight_reports.diagnostic_text import (
    _filter_issue_case_text as _filter_issue_case_text,
)
from web_backend.insight_reports.diagnostic_text import (
    _has_text_anomaly as _has_text_anomaly,
)


def _build_business_issues(
    diagnostics: list[dict[str, Any]],
    issue_cases: list[dict[str, Any]],
    *,
    profile: Any,
) -> list[dict[str, Any]]:
    preferred_codes = set(profile.preferred_reason_codes)
    cases_by_code: dict[str, list[dict[str, Any]]] = {}
    for case in issue_cases:
        code = str(case.get("reason_code") or "")
        if code:
            cases_by_code.setdefault(code, []).append(case)
    issues = []
    for diagnostic in diagnostics:
        reason = diagnostic.get("selected_reason") or {}
        code = str(diagnostic.get("reason_code") or "")
        if not code:
            continue
        cases = _business_cases(diagnostic, cases_by_code.get(code, []))
        if cases:
            context = _case_issue_context(code, reason, cases)
        else:
            context = _diagnostic_issue_context(diagnostic, profile)
        issues.append(
            _build_business_issue(code, reason, context, profile, preferred_codes)
        )
    return issues
