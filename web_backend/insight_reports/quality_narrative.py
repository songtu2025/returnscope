from __future__ import annotations

from typing import Any

from web_backend.insight_reports.quality_context import (
    PRODUCT_EVIDENCE_MARKERS,
    TEXT_EVIDENCE_MARKERS,
    _LiveQualityEvaluation,
)


def _summary_is_blocked(
    summary: dict[str, Any], context: _LiveQualityEvaluation
) -> bool:
    references = summary.get("evidence_ids", [])
    if not context.mapping_trusted:
        summary_text = f"{summary.get('title', '')} {summary.get('statement', '')}"
        references_product = any(
            marker in item for item in references for marker in PRODUCT_EVIDENCE_MARKERS
        )
        if any(name in summary_text for name in context.product_names):
            return True
        if references_product:
            return True
    return not context.text_trusted and any(
        marker in item for item in references for marker in TEXT_EVIDENCE_MARKERS
    )


def _gate_summary(
    quality_issues: list[dict[str, Any]], consistency_blocked: bool
) -> dict[str, Any] | None:
    if not quality_issues:
        return None
    issue_labels = "、".join(item["label"] for item in quality_issues)
    evidence_ids = list(
        dict.fromkeys(
            evidence_id
            for item in quality_issues
            for evidence_id in item["evidence_ids"]
        )
    )
    return {
        "id": "summary.quality_gate",
        "title": "当前报告不可使用" if consistency_blocked else "当前结论仅供诊断",
        "statement": (
            f"{issue_labels}。"
            + (
                "请重新生成报告后再使用。"
                if consistency_blocked
                else "问题修复前，不应直接下发商品整改。"
            )
        ),
        "tone": "warning",
        "evidence_ids": evidence_ids or ["scope"],
    }


def _apply_summaries(
    context: _LiveQualityEvaluation,
) -> list[dict[str, Any]]:
    if not context.mapping_trusted:
        context.content["findings"] = [
            finding
            for finding in context.content.get("findings", [])
            if finding.get("kind") != "diagnostic"
        ]
    summaries = [
        summary
        for summary in context.content.get("executive_summary", [])
        if not _summary_is_blocked(summary, context)
    ]
    quality_issues = list(context.source_issues)
    consistency_blocked = context.consistency["status"] == "blocked"
    if consistency_blocked:
        quality_issues.insert(
            0,
            {
                "code": "report_consistency",
                "label": "报告内部数据不一致",
                "detail": "；".join(context.consistency["issues"][:3]),
                "evidence_ids": [],
            },
        )
        summaries = []
    gate_summary = _gate_summary(quality_issues, consistency_blocked)
    candidates = [gate_summary, *summaries] if gate_summary else summaries
    unique_summaries: list[dict[str, Any]] = []
    seen_summaries: set[tuple[Any, Any]] = set()
    for summary in candidates:
        key = (summary.get("title"), summary.get("statement"))
        if key in seen_summaries:
            continue
        seen_summaries.add(key)
        unique_summaries.append(summary)
    context.content["executive_summary"] = unique_summaries[:4]
    return quality_issues


def _quality_gate_actions(context: _LiveQualityEvaluation) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if not context.text_trusted:
        actions.append(
            {
                "id": "action.text_quality",
                "priority": "P0",
                "target": "退货评论源数据",
                "action": (
                    "重新导出并导入未发生乱码的原始退货数据，"
                    "再重新生成分类结果和 AI 洞察报告。"
                ),
                "rationale": (
                    "评论文本检测到中英文异常混排，语义分类和原始证据可能失真。"
                ),
                "success_signal": (
                    "重新导入后不再检测到异常混排，抽样评论与源文件一致。"
                ),
                "evidence_ids": ["text_quality", "scope"],
            }
        )
    if not context.mapping_trusted:
        actions.append(
            {
                "id": "action.mapping",
                "priority": "P0",
                "target": "商品主数据映射",
                "action": (
                    "核对源 SKU、商品 SKU 与商品名称的对应关系后，再下发商品级整改。"
                ),
                "rationale": (
                    "存在未匹配或缺少名称的商品记录，"
                    "当前不能确认商品级热点对应的真实对象。"
                ),
                "success_signal": (
                    "源 SKU、商品 SKU 与商品名称形成唯一且可追溯的映射。"
                ),
                "evidence_ids": ["product_mapping", "scope"],
            }
        )
    return actions


def _apply_actions(context: _LiveQualityEvaluation) -> None:
    actions = [
        action
        for action in context.content.get("actions", [])
        if action.get("id") != "action.diagnostic" or context.mapping_trusted
    ]
    gate_actions = _quality_gate_actions(context)
    if not context.mapping_trusted:
        actions = [action for action in actions if action.get("id") != "action.mapping"]
    gate_ids = {item["id"] for item in gate_actions}
    actions = [action for action in actions if action.get("id") not in gate_ids]
    candidates = (
        [] if context.consistency["status"] == "blocked" else [*gate_actions, *actions]
    )
    unique_actions: list[dict[str, Any]] = []
    seen_action_ids: set[Any] = set()
    for action in candidates:
        action_id = action.get("id")
        if action_id in seen_action_ids:
            continue
        seen_action_ids.add(action_id)
        unique_actions.append(action)
    action_order = {
        "action.mapping": 0,
        "action.diagnostic": 1,
        "action.text_quality": 2,
        "action.information": 3,
        "action.scope": 4,
    }
    unique_actions.sort(
        key=lambda action: action_order.get(str(action.get("id") or ""), 99)
    )
    context.content["actions"] = unique_actions[:6]


def _decision_readiness(context: _LiveQualityEvaluation) -> dict[str, str]:
    warnings = []
    if not context.text_trusted:
        warnings.append(
            "评论文本质量未通过门禁：在重新导入干净源数据前，"
            "本报告只可用于定位数据问题，不可下发商品整改。"
        )
    if not context.mapping_trusted:
        warnings.append(
            str(context.product_mapping.get("note") or "商品主数据需核对。")
        )
    if context.pending_count:
        warnings.append(
            str(context.review_bias.get("note") or context.source_issues[-1]["detail"])
        )
    caveats = [*warnings, *context.content.get("caveats", [])]
    context.content["caveats"] = list(dict.fromkeys(caveats))
    if context.consistency["status"] == "blocked":
        return {
            "status": "unusable",
            "label": "不可使用",
            "reason": "报告内部数据不一致，请重新生成报告。",
        }
    if context.source_issues:
        labels = "、".join(item["label"] for item in context.source_issues)
        return {
            "status": "diagnostic_only",
            "label": "仅供诊断",
            "reason": f"当前存在{labels}，不应直接下发商品整改。",
        }
    return {
        "status": "actionable",
        "label": "可行动",
        "reason": "数据质量与报告一致性校验均已通过。",
    }


def _quality_gate_status(context: _LiveQualityEvaluation) -> str:
    if context.consistency["status"] == "blocked":
        return "blocked"
    if context.source_issues:
        return "warning"
    return "passed"
