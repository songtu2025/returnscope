from __future__ import annotations

from typing import Any

from web_backend.insight_report_profiles import (
    InsightReportProfile,
    get_insight_report_profile,
)
from web_backend.insight_reports.decision_issue_details import (
    _issue_evidence_ids,
    _issue_known_facts,
    _issue_metrics,
    _issue_readiness,
    _issue_scope,
    _report_language,
)


def _build_issue_candidate(
    source: dict[str, Any],
    catalog: dict[str, Any],
    business_issue: dict[str, Any],
    row: dict[str, Any],
    index: int,
) -> dict[str, Any]:
    code = str(business_issue.get("reason_code") or "")
    dimension = str(business_issue.get("hotspot_dimension") or "product")
    profile = get_insight_report_profile(source.get("report_profile", {}).get("key"))
    listings = list(source.get("listings", []))
    listing = str(listings[0]) if len(listings) == 1 else None
    category = profile.category_name if profile.key != "generic" else None
    sample_label, rate_label, _, original_feedback = _report_language(source)
    case_id, product, sku, issue_id = _issue_scope(code, dimension, row)
    metrics = _issue_metrics(row, business_issue, source)
    lift_value = row.get("lift")
    rank_lift = float(lift_value) if lift_value is not None else 0.0
    label = str(business_issue.get("label") or code)
    target = sku or product
    title = f"{target} · {label}" if target else label
    questions = list(profile.further_questions)[:3]
    if target:
        questions.insert(0, f"{target} 的该问题是否在相同条件下重复出现？")
    return {
        "id": issue_id,
        "rank_key": (
            0 if business_issue.get("role") == "primary" else 1,
            -int(row.get("excess_record_count") or 0),
            -rank_lift,
            -metrics["matched_return_samples"],
            title,
        ),
        "title": title,
        "scope": {
            "category": category,
            "listing": listing,
            "product": product,
            "sku": sku,
        },
        "metrics": metrics,
        "known": _issue_known_facts(business_issue, metrics, label, sample_label),
        "fallback_evidence_explanation": (
            f"该信号在当前{sample_label}中形成集中分化，"
            f"但仅凭反馈与样本结构不能判断{rate_label}或因果。"
        ),
        "fallback_unknown": list(dict.fromkeys(questions))[:5],
        "fallback_recommendation": {
            "label": "建议验证",
            "validation_question": f"是否需要进一步验证 {target or label} 的{label}风险？",
            "rationale": (
                "当前证据足以定位问题范围，但仍需结合实物、"
                "页面信息或业务分母验证原因与影响。"
            ),
            "suggested_evidence": [
                f"复核命中的{original_feedback}",
                "核对相同范围的商品信息与实物表现",
                "补充订单量或销量分母",
            ],
        },
        "readiness": _issue_readiness(source, row, product, sku, metrics),
        "evidence_ids": _issue_evidence_ids(code, dimension, index, case_id, catalog),
    }


def _collect_issue_candidates(
    source: dict[str, Any],
    analysis: dict[str, Any],
    catalog: dict[str, Any],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for business_issue in analysis.get("business_issues", []):
        if not business_issue.get("reason_code"):
            continue
        rows = list(business_issue.get("cases", []))
        if not rows:
            rows = list(business_issue.get("hotspots", []))
        if not rows:
            rows = [None]
        for index, row in enumerate(rows[:2], 1):
            candidates.append(
                _build_issue_candidate(
                    source, catalog, business_issue, row or {}, index
                )
            )
    return candidates


def _coverage_issue(
    source: dict[str, Any],
    profile: InsightReportProfile,
    category: str | None,
    listing: str | None,
) -> dict[str, Any]:
    return {
        "id": "issue.scope.coverage",
        "rank_key": (1, 0, 0, 0, "数据覆盖"),
        "title": "当前范围尚未形成可定位的问题信号",
        "scope": {
            "category": category,
            "listing": listing,
            "product": None,
            "sku": None,
        },
        "metrics": {
            "matched_return_samples": 0,
            "scoped_return_samples": int(source.get("included_record_count") or 0),
            "return_sample_share": 0.0,
            "baseline_return_sample_share": None,
            "gap_percentage_points": None,
            "lift": None,
            "recent_change_percentage_points": None,
            "trend_direction": "insufficient",
        },
        "known": ["当前已分析范围内没有形成可定位到具体问题的稳定信号。"],
        "fallback_evidence_explanation": "现有数据只能说明覆盖范围，不能支持具体问题判断。",
        "fallback_unknown": list(profile.further_questions)[:5]
        or ["是否需要补充更完整的分类与商品信息？"],
        "fallback_recommendation": {
            "label": "建议验证",
            "validation_question": "是否需要先补充分类与商品证据？",
            "rationale": "当前缺少可定位的问题信号。",
            "suggested_evidence": ["补充已审核分类结果"],
        },
        "readiness": {
            "status": "diagnostic_only",
            "label": "仅供诊断",
            "reason": "当前证据不足以定位具体问题。",
        },
        "evidence_ids": ["scope"],
    }
