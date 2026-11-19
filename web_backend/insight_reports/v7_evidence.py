from __future__ import annotations

from typing import Any

from web_backend.dashboard_support import percentage
from web_backend.dashboards.analysis import _DashboardAnalysis
from web_backend.insight_report_diagnostics import (
    _filter_diagnostic_text,
    _product_mapping_check,
)
from web_backend.insight_report_evidence import _build_source
from web_backend.insight_report_profiles import (
    InsightReportProfile,
    resolve_insight_report_profile,
)
from web_backend.insight_reports.diagnostic_summary import (
    _compact_diagnostic,
    _mask_product_diagnostics,
)
from web_backend.insight_reports.evidence_catalog import (
    _counted_entry,
    _diagnostic_evidence,
    _scope_catalog,
)
from web_backend.insight_reports.v7_candidates import (
    MIN_SAMPLES,
    Candidate,
    candidate_metrics,
    select_candidates,
)


def build_semantic_evidence(
    dashboard_service: _DashboardAnalysis, analysis: dict[str, Any]
) -> dict[str, Any]:
    if analysis.get("hierarchy_conflict"):
        raise ValueError(analysis["message"])
    profile = resolve_insight_report_profile(analysis["sources"])
    product_mapping = _product_mapping_check(
        analysis["summary"], analysis["filter_options"].get("listings", [])
    )
    source = _build_source(analysis, product_mapping, profile)
    overview = analysis["report_signals"]["overview"]
    source["included_record_count"] = overview["total"]
    overview["label_coverage"] = percentage(overview["labeled"], overview["total"])
    source["label_coverage"] = overview["label_coverage"]
    candidates = select_candidates(analysis, source)
    catalog = _scope_catalog(analysis, product_mapping, profile)
    diagnostics = _collect_diagnostics(dashboard_service, analysis, candidates, source)
    issues = []
    for rank, item in enumerate(candidates, 1):
        issue = _issue(item, rank, source, profile, catalog)
        detail_ids = _add_diagnostic_evidence(
            catalog, issue["metrics"], diagnostics.get(item.reason_code or "")
        )
        issue["evidence_ids"].extend(detail_ids)
        issues.append(issue)
    return {
        "source": source,
        "catalog": catalog,
        "analysis": {
            "summary": analysis["summary"],
            "review_bias": analysis["review_bias"],
        },
        "blueprint": {
            "report_type": "semantic_insight",
            "title": "反馈信号与验证方向",
            "overview": overview,
            "issues": issues,
            "executive_summary": _executive_summary(issues, overview, catalog),
            "caveats": [
                "占比仅描述当前样本。多标签可同时命中，标签占比不能相加。",
                "排序先按类型取主线，再在同类按命中数降序、标签编码升序排列。",
            ],
        },
    }


def _executive_summary(
    issues: list[dict[str, Any]], overview: dict[str, Any], catalog: dict[str, Any]
) -> list[dict[str, Any]]:
    limit = max(3, len({issue["kind"] for issue in issues}))
    items = [
        {
            "title": issue["title"][:80],
            "statement": issue["known"][0],
            "evidence_ids": issue["evidence_ids"],
        }
        for issue in issues[:limit]
    ]
    context = [
        ("反馈统计范围", f"当前共纳入 {overview['total']} 条反馈。"),
        ("标签覆盖", f"当前样本中 {overview['labeled']} 条反馈具有标签。"),
        ("评价方向", f"{overview['unclear']} 条反馈无明确正负评价。"),
    ]
    for index, (title, statement) in enumerate(context[: max(0, 3 - len(items))], 1):
        evidence_id = f"overview.{index}"
        catalog[evidence_id] = {"label": title, "value": statement, "data": overview}
        items.append(
            {"title": title, "statement": statement, "evidence_ids": [evidence_id]}
        )
    return items


def _collect_diagnostics(
    dashboard_service: _DashboardAnalysis,
    analysis: dict[str, Any],
    candidates: list[Candidate],
    source: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    reason_codes = {str(item["value"]) for item in analysis["reasons"]}
    codes = [
        item.reason_code for item in candidates if item.reason_code in reason_codes
    ]
    diagnostics = [
        _compact_diagnostic(item)
        for item in dashboard_service.report_diagnostics(
            str(analysis["dashboard_id"]), str(analysis["version_id"]), codes
        )
    ]
    if source["product_mapping"]["status"] == "needs_review":
        diagnostics = _mask_product_diagnostics(diagnostics)
    if source["text_quality"].get("status") == "needs_review":
        diagnostics = [_filter_diagnostic_text(item) for item in diagnostics]
    return {str(item["reason_code"]): item for item in diagnostics}


def _issue(
    item: Candidate,
    rank: int,
    source: dict[str, Any],
    profile: InsightReportProfile,
    catalog: dict[str, Any],
) -> dict[str, Any]:
    metrics = candidate_metrics(item, source["included_record_count"], source)
    evidence_id = f"signal.{item.kind}.{item.code}"
    catalog[evidence_id] = _counted_entry(
        {
            "record_count": item.signal_count,
            "percentage": metrics["return_sample_share"],
            **(item.counts or {}),
        },
        item.title,
    )
    return {
        "id": evidence_id,
        "kind": item.kind,
        "rank": rank,
        "title": item.title[:200],
        "scope": {"category": profile.category_name},
        "metrics": metrics,
        "known": [
            f"{item.signal_count} / {metrics['scoped_return_samples']} 条，"
            f"样本占比 {metrics['return_sample_share']:.1f}%。",
            *item.facts,
        ],
        "evidence_ids": list(
            dict.fromkeys((evidence_id, "scope", *item.extra_evidence))
        ),
        "readiness": _readiness(item, source),
        "fallback_evidence_explanation": "这是当前样本中的信号，可用于确定下一步核查方向。",
        "fallback_unknown": ["补充同口径样本后，该信号是否仍然存在？"],
        "fallback_recommendation": {
            "validation_question": _validation_question(item, profile),
            "rationale": "先核对原始反馈与统计口径，再判断信号是否稳定。",
            "suggested_evidence": ["同口径反馈样本", "对应的分类和复核记录"],
        },
    }


def _validation_question(item: Candidate, profile: InsightReportProfile) -> str:
    if item.kind == "data_gap":
        return "补齐对应数据后，当前反馈分布是否变化？"
    if item.kind == "polarization":
        if item.counts:
            return "两个相反方向的反馈分别出现在哪些使用条件或人群中？"
        return "正向与负向反馈分别出现在哪些使用场景？"
    if item.kind == "opportunity":
        return "相同优点是否在更多独立反馈中重复出现？"
    if item.code in profile.preferred_reason_codes:
        return profile.further_questions[0]
    return "同类负向反馈在什么条件下重复出现？"


def _readiness(item: Candidate, source: dict[str, Any]) -> dict[str, str]:
    if item.signal_count < MIN_SAMPLES:
        reason = f"该信号少于 {MIN_SAMPLES} 条，只适合作为核查线索。"
    elif item.kind == "data_gap" or source["quality_issue_codes"]:
        reason = "存在数据缺口或质量限制，需先核对证据。"
    else:
        return {
            "status": "verification_ready",
            "label": "可进入验证",
            "reason": "当前证据可用于规划独立验证。",
        }
    return {"status": "diagnostic_only", "label": "仅供诊断", "reason": reason}


def _add_diagnostic_evidence(
    catalog: dict[str, Any], metrics: dict[str, Any], diagnostic: dict[str, Any] | None
) -> list[str]:
    if not diagnostic:
        return []
    trend = diagnostic["trend_summary"]
    metrics["trend_direction"] = trend.get("direction", "insufficient")
    metrics["recent_change_percentage_points"] = trend.get("delta_percentage_points")
    # 热点使用自身的样本量、整体基线与 lift，与全范围信号指标分别展示。
    entries = _diagnostic_evidence(diagnostic)
    selected = [
        evidence_id
        for evidence_id in entries
        if evidence_id.endswith((".trend", ".hotspot.1", ".variant.1", ".sample.1"))
    ]
    catalog.update({evidence_id: entries[evidence_id] for evidence_id in selected})
    return selected
