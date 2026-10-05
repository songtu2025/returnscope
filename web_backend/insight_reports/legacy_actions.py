from __future__ import annotations

from typing import Any

from web_backend.insight_report_profiles import (
    InsightReportProfile,
    get_insight_report_profile,
)
from web_backend.insight_reports.legacy_common import (
    _reason_evidence_ids,
    _report_language,
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
    language = _report_language(source)
    reason_evidence_ids = _reason_evidence_ids(actionable_reasons)
    actions = _quality_actions(
        product_mapping, text_trusted, mapping_trusted, language[1]
    )
    if actionable_reasons and mapping_trusted:
        actions.append(
            _diagnostic_action(
                primary_issues,
                hotspot_targets,
                profile,
                reason_evidence_ids,
                diagnostic_ids,
            )
        )
    actions.extend(
        _followup_actions(
            broad_reason, information_ids, language[3], language[0], language[2]
        )
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


def _quality_actions(
    product_mapping: dict[str, Any],
    text_trusted: bool,
    mapping_trusted: bool,
    feedback_label: str,
) -> list[dict[str, Any]]:
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
    return actions


def _diagnostic_action(
    primary_issues: list[dict[str, Any]],
    hotspot_targets: list[str],
    profile: InsightReportProfile,
    reason_evidence_ids: list[str],
    diagnostic_ids: list[str],
) -> dict[str, Any]:
    validation_issues = [issue for issue in primary_issues if issue.get("cases")][:3]
    validation_cases = [issue["cases"][0] for issue in validation_issues]
    target = _validation_target(validation_cases, hotspot_targets, profile)
    case_actions = [
        str(issue.get("validation_focus") or "")
        for issue in validation_issues
        if issue.get("validation_focus")
    ]
    case_rationales = _validation_rationales(validation_cases)
    action_evidence_ids = _validation_evidence(
        validation_cases, reason_evidence_ids, diagnostic_ids
    )
    return {
        "id": "action.diagnostic",
        "priority": "P0",
        "target": target,
        "finding_id": "finding.diagnostic",
        "evidence_ids": action_evidence_ids,
        "fallback_action": "；".join(case_actions)
        if case_actions
        else profile.diagnostic_action,
        "fallback_rationale": "；".join(case_rationales)
        + "。这些集中信号值得优先验证，但不能单凭反馈结构推断原因。"
        if case_rationales
        else profile.diagnostic_rationale,
        "fallback_success_signal": "每个目标 SKU 都形成可复核的原因结论；后续同口径反馈中，对应问题连续两个完整周期下降，且反向问题不升高。"
        if validation_cases
        else profile.diagnostic_success_signal,
    }


def _validation_target(
    validation_cases: list[dict[str, Any]],
    hotspot_targets: list[str],
    profile: InsightReportProfile,
) -> str:
    return (
        "、".join(
            dict.fromkeys(
                (
                    str(case.get("product_sku") or "")
                    for case in validation_cases
                    if case.get("product_sku")
                )
            )
        )
        or "、".join(hotspot_targets[:2])
        or f"高频{profile.variant_label}"
    )


def _validation_rationales(validation_cases: list[dict[str, Any]]) -> list[str]:
    return [
        (
            f"{case.get('product_sku')}的{case.get('label')}为"
            f"{float(case.get('product_reason_rate') or 0):.1f}%"
            f"（整体{float(case.get('overall_reason_rate') or 0):.1f}%，"
            f"{float(case.get('lift') or 0):.2f}倍）"
        )
        for case in validation_cases
    ]


def _validation_evidence(
    validation_cases: list[dict[str, Any]],
    reason_evidence_ids: list[str],
    diagnostic_ids: list[str],
) -> list[str]:
    return list(
        dict.fromkeys(
            [
                *reason_evidence_ids,
                *diagnostic_ids,
                *(str(case.get("id")) for case in validation_cases if case.get("id")),
            ]
        )
    )


def _followup_actions(
    broad_reason: dict[str, Any] | None,
    information_ids: list[str],
    problem_label: str,
    record_label: str,
    rate_label: str,
) -> list[dict[str, Any]]:
    actions = []
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
    return actions
