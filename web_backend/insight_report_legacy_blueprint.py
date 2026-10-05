from __future__ import annotations

from typing import Any

from web_backend.insight_report_profiles import (
    get_insight_report_profile,
)
from web_backend.insight_reports.legacy_actions import _build_actions
from web_backend.insight_reports.legacy_common import (
    _report_language,
)
from web_backend.insight_reports.legacy_findings import (
    _build_diagnostic_finding,
    _build_information_finding,
    _select_reasons,
)
from web_backend.insight_reports.legacy_structure import (
    _build_caveats,
    _build_structure_section,
    _StructureSection,
)


def _scope_summary(
    source: dict[str, Any], analysis: dict[str, Any]
) -> tuple[str, bool, str, str]:
    listings = list(source.get("listings", []))
    scope_name = (
        str(listings[0])
        if len(listings) == 1
        else f"{len(listings)} 个 Listing"
        if listings
        else "当前范围"
    )
    provisional = source.get("report_status") == "provisional"
    included = int(source.get("included_record_count") or 0)
    total = int(source.get("total_record_count") or included)
    pending = int(source.get("pending_review_record_count") or 0)
    coverage = float(source.get("coverage_rate") or 0)
    review_bias = analysis.get("review_bias", {})
    bias_note = str(review_bias.get("note") or "")
    _, _, _, problem_label = _report_language(source)
    scope_statement = (
        f"报告纳入 {included} / {total} 条记录，覆盖率 {coverage:.1f}%；"
        f"另有 {pending} 条待审核记录未进入本次统计。{bias_note}"
        if pending
        else f"报告纳入 {included} 条记录，当前范围内无待审核记录。"
    )
    return scope_name, provisional, scope_statement, problem_label


def _validation_summary(
    structure: _StructureSection,
    findings: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    hotspot_targets: list[str],
) -> str:
    diagnostic_summary = (
        findings[1]["conclusion"]
        if len(findings) > 1
        else structure.structure_statement
    )
    diagnostic_action = next(
        (action for action in actions if action.get("id") == "action.diagnostic"),
        None,
    )
    validation_target = (
        str(diagnostic_action.get("target") or "")
        if diagnostic_action
        else "、".join(hotspot_targets[:2])
    )
    validation_statement = (
        f"优先验证{validation_target}：{diagnostic_action.get('fallback_action')}"
        if validation_target and diagnostic_action
        else diagnostic_summary
    )
    return validation_statement


def _executive_summaries(
    structure: _StructureSection,
    findings: list[dict[str, Any]],
    validation_statement: str,
    scope_statement: str,
    provisional: bool,
) -> list[dict[str, Any]]:
    return [
        {
            "id": "summary.1",
            "title": "最明确的问题分化",
            "statement": structure.business_statement,
            "tone": "primary",
            "evidence_ids": [
                *structure.business_evidence_ids,
                structure.group_evidence_id,
                *structure.reason_evidence_ids,
            ],
        },
        {
            "id": "summary.2",
            "title": "优先验证对象",
            "statement": validation_statement,
            "tone": "neutral",
            "evidence_ids": findings[1]["evidence_ids"],
        },
        {
            "id": "summary.3",
            "title": "结论可信边界",
            "statement": scope_statement,
            "tone": "warning" if provisional else "neutral",
            "evidence_ids": ["scope", "review_bias"],
        },
    ]


def _build_blueprint(evidence: dict[str, Any]) -> dict[str, Any]:
    source = evidence["source"]
    analysis = evidence["analysis"]
    profile = get_insight_report_profile(source.get("report_profile", {}).get("key"))
    reasons = list(analysis.get("reasons", []))
    diagnostics = {
        str(item.get("reason_code")): item
        for item in analysis.get("diagnostics", [])
        if item.get("reason_code")
    }
    scope_name, provisional, scope_statement, problem_label = _scope_summary(
        source, analysis
    )
    actionable_reasons, broad_reason = _select_reasons(reasons, profile)
    structure = _build_structure_section(source, analysis, profile, actionable_reasons)
    findings = [structure.finding]

    diagnostic_finding, diagnostic_ids, hotspot_targets = _build_diagnostic_finding(
        evidence, actionable_reasons
    )
    if diagnostic_finding is not None:
        findings.append(diagnostic_finding)

    information_finding, information_ids = _build_information_finding(
        broad_reason, diagnostics
    )
    if information_finding is not None:
        findings.append(information_finding)

    if len(findings) < 2:
        findings.append(
            {
                "id": "finding.coverage",
                "kind": "information",
                "title": "数据覆盖决定当前结论可用于什么决策",
                "conclusion": scope_statement,
                "evidence_ids": ["scope", "review_bias"],
            }
        )

    actions = _build_actions(
        evidence,
        actionable_reasons,
        diagnostic_ids,
        hotspot_targets,
        (broad_reason, information_ids),
    )
    caveats = _build_caveats(evidence)

    validation_statement = _validation_summary(
        structure, findings, actions, hotspot_targets
    )
    return {
        "title": f"{scope_name} {problem_label}{'临时' if provisional else ''}诊断报告",
        "executive_summary": _executive_summaries(
            structure, findings, validation_statement, scope_statement, provisional
        ),
        "findings": findings,
        "actions": actions,
        "further_questions": list(profile.further_questions),
        "caveats": caveats,
    }
