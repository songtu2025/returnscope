from __future__ import annotations

from typing import Any

from web_backend.insight_report_profiles import (
    InsightReportProfile,
    get_insight_report_profile,
)
from web_backend.insight_reports.legacy_common import _reason_evidence_ids


def _select_reasons(
    reasons: list[dict[str, Any]], profile: InsightReportProfile
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    generic_actionable_reasons = [
        reason
        for reason in reasons
        if "PRODUCT" in reason.get("subjects", [])
        and str(reason.get("label_group") or "") != "其他原因"
    ]
    reason_by_code = {
        str(reason.get("value") or ""): reason for reason in generic_actionable_reasons
    }
    actionable_reasons = [
        reason_by_code[code]
        for code in profile.preferred_reason_codes
        if code in reason_by_code
    ]
    for reason in generic_actionable_reasons:
        if reason not in actionable_reasons:
            actionable_reasons.append(reason)
        if len(actionable_reasons) >= 3:
            break
    actionable_reasons = actionable_reasons[:3]
    broad_reason = next(
        (
            reason
            for reason in reasons
            if len(reason.get("subjects", [])) > 1
            or str(reason.get("label_group") or "") == "其他原因"
        ),
        None,
    )
    return actionable_reasons, broad_reason


def _build_diagnostic_finding(
    evidence: dict[str, Any], actionable_reasons: list[dict[str, Any]]
) -> tuple[dict[str, Any] | None, list[str], list[str]]:
    analysis = evidence["analysis"]
    source = evidence["source"]
    profile = get_insight_report_profile(source.get("report_profile", {}).get("key"))
    diagnostics = {
        str(item.get("reason_code")): item
        for item in analysis.get("diagnostics", [])
        if item.get("reason_code")
    }
    issues_by_code = {
        str(issue.get("reason_code") or ""): issue
        for issue in analysis.get("business_issues", [])
        if issue.get("reason_code")
    }
    reason_evidence_ids = _reason_evidence_ids(actionable_reasons)
    findings: list[dict[str, Any]] = []
    diagnostic_ids = []
    trend_sentences = []
    hotspot_sentences = []
    hotspot_targets = []
    for reason in actionable_reasons:
        code = str(reason.get("value") or "")
        issue = issues_by_code.get(code, {})
        issue_case = next(iter(issue.get("cases", [])), None)
        if issue_case:
            case_id = str(issue_case.get("id") or "")
            trend_summary = issue_case.get("trend_summary", {})
            if (
                trend_summary.get("status") == "available"
                and f"{case_id}.trend" in evidence["catalog"]
            ):
                diagnostic_ids.append(f"{case_id}.trend")
                trend_sentences.append(
                    f"{reason.get('label')}在"
                    f"{issue_case.get('product_sku')}最近"
                    f"{trend_summary.get('window_weeks')}个完整周均值为"
                    f"{float(trend_summary.get('recent_rate') or 0):.1f}%，"
                    f"较最早同长度窗口"
                    f"{float(trend_summary.get('delta_percentage_points') or 0):+.1f}pp"
                )
            diagnostic_ids.append(case_id)
            hotspot_targets.append(str(issue_case.get("product_sku") or ""))
            hotspot_sentences.append(
                f"{reason.get('label')}集中在"
                f"{issue_case.get('product_sku')}："
                f"{int(issue_case.get('record_count') or 0)} / "
                f"{int(issue_case.get('total_record_count') or 0)}条，"
                f"变体内占比"
                f"{float(issue_case.get('product_reason_rate') or 0):.1f}%，"
                f"整体基线"
                f"{float(issue_case.get('overall_reason_rate') or 0):.1f}%，"
                f"为基线的{float(issue_case.get('lift') or 0):.2f}倍，"
                f"超出按整体基线预期约"
                f"{int(issue_case.get('excess_record_count') or 0)}条"
            )
            continue
        diagnostic = diagnostics.get(code, {})
        trend_summary = diagnostic.get("trend_summary", {})
        trend_id = f"diagnostic.{code}.trend"
        if trend_id in evidence["catalog"]:
            diagnostic_ids.append(trend_id)
            trend_sentences.append(
                f"{reason.get('label')}最近"
                f"{trend_summary.get('window_weeks')}个完整周均值为"
                f"{float(trend_summary.get('recent_rate') or 0):.1f}%，"
                f"较最早同长度窗口"
                f"{float(trend_summary.get('delta_percentage_points') or 0):+.1f}pp"
            )
        diagnostic_dimension = "variants" if diagnostic.get("variants") else "hotspots"
        hotspot = next(iter(diagnostic.get(diagnostic_dimension, [])), None)
        evidence_dimension = (
            "variant" if diagnostic_dimension == "variants" else "hotspot"
        )
        hotspot_id = f"diagnostic.{code}.{evidence_dimension}.1"
        if hotspot and hotspot_id in evidence["catalog"]:
            diagnostic_ids.append(hotspot_id)
            hotspot_targets.append(str(hotspot.get("value") or ""))
            hotspot_sentences.append(
                f"{reason.get('label')}在{hotspot.get('value')}达到"
                f"{float(hotspot.get('product_reason_rate') or 0):.1f}%，"
                f"为整体基线的{float(hotspot.get('lift') or 0):.2f}倍"
            )
    hotspot_targets = list(
        dict.fromkeys(target for target in hotspot_targets if target)
    )
    if actionable_reasons:
        diagnostic_conclusion = "；".join(trend_sentences + hotspot_sentences)
        if not diagnostic_conclusion:
            diagnostic_conclusion = profile.diagnostic_empty
        findings.append(
            {
                "id": "finding.diagnostic",
                "kind": "diagnostic",
                "title": (
                    f"{'、'.join(hotspot_targets[:2])}是当前最需要验证的具体 SKU"
                    if hotspot_targets
                    else profile.diagnostic_title
                ),
                "conclusion": f"{diagnostic_conclusion}。",
                "evidence_ids": [
                    *reason_evidence_ids,
                    *diagnostic_ids,
                ],
            }
        )

    return (findings[0] if findings else None), diagnostic_ids, hotspot_targets


def _build_information_finding(
    broad_reason: dict[str, Any] | None, diagnostics: dict[str, dict[str, Any]]
) -> tuple[dict[str, Any] | None, list[str]]:
    findings: list[dict[str, Any]] = []
    information_ids = []
    if broad_reason:
        broad_code = str(broad_reason.get("value") or "")
        broad_diagnostic = diagnostics.get(broad_code, {})
        semantic = broad_diagnostic.get("semantic_profile", {})
        unspecified = next(
            (
                part
                for part in semantic.get("parts", [])
                if part.get("value") == "UNSPECIFIED"
            ),
            None,
        )
        top_opinion = next(iter(semantic.get("opinions", [])), None)
        broad_reason_id = f"reason.{broad_code}"
        information_ids.append(broad_reason_id)
        details = []
        if unspecified:
            details.append(
                f"{float(unspecified.get('percentage') or 0):.1f}%未明确商品部位"
            )
        if top_opinion:
            opinion_id = f"diagnostic.{broad_code}.opinion.1"
            information_ids.append(opinion_id)
            details.append(
                f"最高频语义为“{top_opinion.get('opinion')}”"
                f"（{int(top_opinion.get('record_count') or 0)}条）"
            )
        information_conclusion = (
            f"{broad_reason.get('label')}涉及"
            f"{int(broad_reason.get('record_count') or 0)}条记录，"
            f"占{float(broad_reason.get('percentage') or 0):.1f}%"
        )
        if details:
            information_conclusion += "；" + "；".join(details)
        findings.append(
            {
                "id": "finding.information",
                "kind": "information",
                "title": f"“{broad_reason.get('label')}”需要按意图拆解，而不是当作商品缺陷",
                "conclusion": f"{information_conclusion}。",
                "evidence_ids": [*information_ids, "scope"],
            }
        )

    return (findings[0] if findings else None), information_ids
