from __future__ import annotations

from typing import Any, NamedTuple

from web_backend.insight_reports.diagnostic_summary import _trend_summary


class _BusinessIssueContext(NamedTuple):
    cases: list[dict[str, Any]]
    dimension: str
    hotspots: list[dict[str, Any]]
    trend_summary: dict[str, Any]
    trend: list[dict[str, Any]]
    opinions: list[dict[str, Any]]
    samples: list[dict[str, Any]]
    parts: list[dict[str, Any]]
    validation_focus: str


def _business_cases(
    diagnostic: dict[str, Any], issue_cases: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    cases = []
    for case in issue_cases[:3]:
        trend = list(case.get("trend", []))
        cases.append(
            {
                **case,
                "value": str(case.get("product_sku") or ""),
                "product_reason_rate": float(case.get("issue_rate") or 0),
                "overall_reason_rate": float(case.get("overall_rate") or 0),
                "trend_summary": _trend_summary(
                    trend,
                    str(diagnostic.get("date_range", {}).get("date_to") or "") or None,
                ),
            }
        )
    return cases


def _case_issue_context(
    code: str, reason: dict[str, Any], cases: list[dict[str, Any]]
) -> _BusinessIssueContext:
    dimension = "variant"
    hotspots = cases
    primary_case = cases[0]
    trend_summary = primary_case["trend_summary"]
    trend = list(primary_case.get("trend", []))
    semantic_profile = primary_case.get("semantic_profile", {})
    opinions = list(semantic_profile.get("opinions", []))[:3]
    samples = list(primary_case.get("samples", []))[:3]
    parts = list(semantic_profile.get("parts", []))[:4]
    top_opinion = next(iter(opinions), None)
    validation_focus = (
        f"先复核 {primary_case.get('product_sku')} 中"
        f"“{top_opinion.get('opinion')}”对应的评论，"
        "再核对实物规格、页面说明与使用情境"
        if top_opinion
        else (
            f"先复核 {primary_case.get('product_sku')} 的"
            f"{reason.get('label') or code}评论，再核对实物和页面说明"
        )
    )
    return _BusinessIssueContext(
        cases=cases,
        dimension=dimension,
        hotspots=hotspots,
        trend_summary=trend_summary,
        trend=trend,
        opinions=opinions,
        samples=samples,
        parts=parts,
        validation_focus=validation_focus,
    )


def _diagnostic_issue_context(
    diagnostic: dict[str, Any], profile: Any
) -> _BusinessIssueContext:
    cases: list[dict[str, Any]] = []
    dimension = "variant" if diagnostic.get("variants") else "product"
    hotspots = list(
        diagnostic.get("variants" if dimension == "variant" else "hotspots", [])
    )[:3]
    trend_summary = diagnostic.get("trend_summary", {})
    trend = list(diagnostic.get("trend", []))
    semantic_profile = diagnostic.get("semantic_profile", {})
    opinions = list(semantic_profile.get("opinions", []))[:3]
    samples = list(diagnostic.get("samples", []))[:3]
    parts = list(semantic_profile.get("parts", []))[:4]
    validation_focus = profile.diagnostic_action
    return _BusinessIssueContext(
        cases=cases,
        dimension=dimension,
        hotspots=hotspots,
        trend_summary=trend_summary,
        trend=trend,
        opinions=opinions,
        samples=samples,
        parts=parts,
        validation_focus=validation_focus,
    )
