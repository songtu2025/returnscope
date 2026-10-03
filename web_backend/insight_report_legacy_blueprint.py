from __future__ import annotations

from typing import Any, NamedTuple

from web_backend.insight_report_profiles import (
    InsightReportProfile,
    get_insight_report_profile,
)
from web_backend.insight_reports.legacy_common import (
    _reason_evidence_ids,
    _report_language,
)
from web_backend.insight_reports.legacy_findings import (
    _build_diagnostic_finding,
    _build_information_finding,
    _select_reasons,
)


def _build_actions(
    evidence: dict[str, Any],
    actionable_reasons: list[dict[str, Any]],
    diagnostic_ids: list[str],
    hotspot_targets: list[str],
    information: tuple[dict[str, Any] | None, list[str]],
) -> list[dict[str, Any]]:
    broad_reason, information_ids = information
    source = evidence["source"]
    analysis = evidence["analysis"]
    profile = get_insight_report_profile(source.get("report_profile", {}).get("key"))
    primary_issues = [
        issue
        for issue in analysis.get("business_issues", [])
        if issue.get("role") == "primary"
    ]
    product_mapping = source.get("product_mapping", {})
    mapping_trusted = product_mapping.get("status") != "needs_review"
    text_quality = source.get("text_quality", {})
    text_trusted = text_quality.get("status") != "needs_review"
    record_label, feedback_label, rate_label, problem_label = _report_language(source)
    reason_evidence_ids = _reason_evidence_ids(actionable_reasons)
    actions = []
    if not text_trusted:
        actions.append(
            {
                "id": "action.text_quality",
                "priority": "P0",
                "target": f"{feedback_label}源数据",
                "finding_id": "finding.structure",
                "evidence_ids": ["text_quality", "scope"],
                "fallback_action": f"重新导出并导入未发生乱码的原始{feedback_label}数据，再重新生成分类结果。",
                "fallback_rationale": "评论文本已经出现编码异常，语义分类和原始证据均可能失真。",
                "fallback_success_signal": "重新导入后不再检测到中英文异常混排，抽样评论与源文件一致。",
            }
        )
    if not mapping_trusted:
        actions.append(
            {
                "id": "action.mapping",
                "priority": "P0",
                "target": f"Listing {product_mapping.get('listing')} 的商品主数据映射",
                "finding_id": "finding.structure",
                "evidence_ids": ["product_mapping", "scope"],
                "fallback_action": "核对源 SKU、商品 SKU 与商品名称的对应关系后再下发商品级整改。",
                "fallback_rationale": "存在未匹配或缺少名称的商品记录，当前不能确认商品级热点对应的真实对象。",
                "fallback_success_signal": "源 SKU、商品 SKU 与商品名称形成唯一且可追溯的映射。",
            }
        )
    if actionable_reasons and mapping_trusted:
        validation_issues = [issue for issue in primary_issues if issue.get("cases")][
            :3
        ]
        validation_cases = [issue["cases"][0] for issue in validation_issues]
        target = (
            "、".join(
                dict.fromkeys(
                    str(case.get("product_sku") or "")
                    for case in validation_cases
                    if case.get("product_sku")
                )
            )
            or "、".join(hotspot_targets[:2])
            or f"高频{profile.variant_label}"
        )
        case_actions = [
            str(issue.get("validation_focus") or "")
            for issue in validation_issues
            if issue.get("validation_focus")
        ]
        case_rationales = [
            (
                f"{case.get('product_sku')}的{case.get('label')}为"
                f"{float(case.get('product_reason_rate') or 0):.1f}%"
                f"（整体{float(case.get('overall_reason_rate') or 0):.1f}%，"
                f"{float(case.get('lift') or 0):.2f}倍）"
            )
            for case in validation_cases
        ]
        action_evidence_ids = list(
            dict.fromkeys(
                [
                    *reason_evidence_ids,
                    *diagnostic_ids,
                    *(
                        str(case.get("id"))
                        for case in validation_cases
                        if case.get("id")
                    ),
                ]
            )
        )
        actions.append(
            {
                "id": "action.diagnostic",
                "priority": "P0",
                "target": target,
                "finding_id": "finding.diagnostic",
                "evidence_ids": action_evidence_ids,
                "fallback_action": (
                    "；".join(case_actions)
                    if case_actions
                    else profile.diagnostic_action
                ),
                "fallback_rationale": (
                    "；".join(case_rationales)
                    + "。这些集中信号值得优先验证，但不能单凭反馈结构推断原因。"
                    if case_rationales
                    else profile.diagnostic_rationale
                ),
                "fallback_success_signal": (
                    "每个目标 SKU 都形成可复核的原因结论；后续同口径反馈中，"
                    "对应问题连续两个完整周期下降，且反向问题不升高。"
                    if validation_cases
                    else profile.diagnostic_success_signal
                ),
            }
        )
    if broad_reason:
        actions.append(
            {
                "id": "action.information",
                "priority": "P1",
                "target": f"{broad_reason.get('label')}相关记录",
                "finding_id": "finding.information",
                "evidence_ids": information_ids,
                "fallback_action": "按反馈表达的具体意图、对象和使用场景拆分宽泛原因。",
                "fallback_rationale": f"宽泛标签混合多种{problem_label}情境，不能直接转化为单一商品整改。",
                "fallback_success_signal": "宽泛原因被稳定拆分为可解释子类，且未明确对象占比下降。",
            }
        )
    actions.append(
        {
            "id": "action.scope",
            "priority": "P2",
            "target": "待审核记录与商品销量分母",
            "finding_id": "finding.structure",
            "evidence_ids": ["scope", "review_bias"],
            "fallback_action": "持续处理待审核记录，并补充商品销量或订单量分母。",
            "fallback_rationale": f"{record_label}占比只能描述问题结构，不能代替{rate_label}。",
            "fallback_success_signal": f"待审核占比下降并形成商品级{rate_label}基线。",
        }
    )
    action_order = {
        "action.mapping": 0,
        "action.diagnostic": 1,
        "action.text_quality": 2,
        "action.information": 3,
        "action.scope": 4,
    }
    actions.sort(key=lambda item: action_order.get(str(item.get("id")), 99))
    return actions


class _StructureSection(NamedTuple):
    finding: dict[str, Any]
    structure_statement: str
    business_statement: str
    business_evidence_ids: list[str]
    group_evidence_id: str
    reason_evidence_ids: list[str]


def _build_structure_section(
    source: dict[str, Any],
    analysis: dict[str, Any],
    profile: InsightReportProfile,
    actionable_reasons: list[dict[str, Any]],
) -> _StructureSection:
    groups = list(analysis.get("label_group_breakdown", []))
    primary_issues = [
        issue
        for issue in analysis.get("business_issues", [])
        if issue.get("role") == "primary"
    ]
    included = int(source.get("included_record_count") or 0)
    record_label, _, _, _ = _report_language(source)
    primary_group = next(
        (group for group in groups if str(group.get("value")) != "其他原因"),
        groups[0] if groups else None,
    )
    group_evidence_id = "scope"
    if primary_group:
        group_evidence_id = next(
            (
                f"group.{index}"
                for index, group in enumerate(groups, 1)
                if group.get("value") == primary_group.get("value")
            ),
            "scope",
        )
    reason_evidence_ids = _reason_evidence_ids(actionable_reasons)
    structure_statement = (
        f"{primary_group.get('value')}覆盖 "
        f"{int(primary_group.get('record_count') or 0)} 条记录，"
        f"占已纳入样本 {float(primary_group.get('percentage') or 0):.1f}%。"
        if primary_group
        else f"当前共纳入 {included} 条可分析{record_label}。"
    )
    if actionable_reasons:
        reason_text = "；".join(
            f"{reason.get('label')} {int(reason.get('record_count') or 0)} 条"
            f"（{float(reason.get('percentage') or 0):.1f}%）"
            for reason in actionable_reasons
        )
        structure_statement = f"{structure_statement.rstrip('。')}；其中{reason_text}。"
    business_headlines = []
    business_evidence_ids = []
    for issue in primary_issues[:3]:
        hotspot = next(iter(issue.get("hotspots", [])), None)
        if not hotspot:
            continue
        rate = float(hotspot.get("product_reason_rate") or 0)
        baseline = float(hotspot.get("overall_reason_rate") or 0)
        business_headlines.append(
            f"{issue.get('label')}在{hotspot.get('value')}为{rate:.1f}%，"
            f"比整体基线高{rate - baseline:+.1f}pp"
        )
        business_evidence_ids.append(str(issue.get("id")))
    business_statement = (
        "；".join(business_headlines) + "。"
        if business_headlines
        else structure_statement
    )

    findings = [
        {
            "id": "finding.structure",
            "kind": "structure",
            "title": (
                f"{profile.category_name}问题已经分化到具体{profile.variant_label}"
                if business_headlines
                else f"{primary_group.get('value')}是当前最值得优先处理的商品问题"
                if primary_group
                else "当前问题结构需要先完成业务归类"
            ),
            "conclusion": business_statement,
            "evidence_ids": [
                *business_evidence_ids,
                group_evidence_id,
                *reason_evidence_ids,
                "scope",
            ],
        }
    ]

    return _StructureSection(
        findings[0],
        structure_statement,
        business_statement,
        business_evidence_ids,
        group_evidence_id,
        reason_evidence_ids,
    )


def _build_caveats(evidence: dict[str, Any]) -> list[str]:
    source = evidence["source"]
    analysis = evidence["analysis"]
    _, _, rate_label, problem_label = _report_language(source)
    provisional = source.get("report_status") == "provisional"
    pending = int(source.get("pending_review_record_count") or 0)
    review_bias = analysis.get("review_bias", {})
    bias_note = str(review_bias.get("note") or "")
    product_mapping = source.get("product_mapping", {})
    text_quality = source.get("text_quality", {})
    text_trusted = text_quality.get("status") != "needs_review"
    caveats = [
        f"本报告只描述所选分类结果版本中的{problem_label}结构，不代表{rate_label}。",
        "当前缺少销量、订单量、成本和批次等分母数据，不能据此推断因果。",
    ]
    if provisional:
        caveats.insert(
            0,
            f"这是临时报告：{pending} 条待审核记录未纳入，结论可能随复核推进而变化。",
        )
        if review_bias.get("status") == "concentrated":
            caveats.insert(1, bias_note)
    if product_mapping.get("status") == "needs_review":
        caveats.append(str(product_mapping.get("note")))
    if not text_trusted:
        caveats.append(str(text_quality.get("note")))

    return caveats


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
    return {
        "title": f"{scope_name} {problem_label}{'临时' if provisional else ''}诊断报告",
        "executive_summary": [
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
        ],
        "findings": findings,
        "actions": actions,
        "further_questions": list(profile.further_questions),
        "caveats": caveats,
    }
