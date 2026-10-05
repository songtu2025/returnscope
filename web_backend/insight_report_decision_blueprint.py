from __future__ import annotations

from typing import Any

from web_backend.insight_report_profiles import get_insight_report_profile
from web_backend.insight_reports.decision_candidates import (
    _collect_issue_candidates,
    _coverage_issue,
)
from web_backend.insight_reports.decision_issue_details import _report_language


def _build_decision_blueprint(evidence: dict[str, Any]) -> dict[str, Any]:
    source = evidence["source"]
    analysis = evidence["analysis"]
    catalog = evidence["catalog"]
    profile = get_insight_report_profile(source.get("report_profile", {}).get("key"))
    listings = list(source.get("listings", []))
    listing = str(listings[0]) if len(listings) == 1 else None
    category = profile.category_name if profile.key != "generic" else None
    sample_label, rate_label, report_subject, _ = _report_language(source)
    candidates = _collect_issue_candidates(source, analysis, catalog)

    if not candidates:
        candidates.append(_coverage_issue(source, profile, category, listing))

    issues: list[dict[str, Any]] = []
    for rank, candidate in enumerate(
        sorted(candidates, key=lambda item: item["rank_key"])[:8],
        1,
    ):
        issue = {key: value for key, value in candidate.items() if key != "rank_key"}
        issue["rank"] = rank
        issues.append(issue)

    scope_name = (
        listing
        if listing
        else f"{len(listings)} 个 Listing"
        if listings
        else "当前范围"
    )
    caveats = [
        f"所有占比均为{sample_label}内占比，不代表{rate_label}。",
        "当前缺少订单量、销量、成本和批次等分母，不能据此推断因果。",
    ]
    if source.get("pending_review_record_count"):
        caveats.append("待审核记录未进入本次统计，结论可能随复核推进而变化。")
    return {
        "report_type": "problem_decision",
        "title": f"{scope_name} {report_subject}判断报告",
        "issues": issues,
        "caveats": caveats,
    }
