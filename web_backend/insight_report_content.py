from __future__ import annotations

import json
import re
from typing import Any

from web_backend.insight_report_contracts import (
    InsightDecisionReportContent,
    InsightReportContent,
)


def _messages_v6(evidence: dict[str, Any]) -> list[dict[str, str]]:
    schema = {
        "issues": [
            {
                "id": "使用 fixed_blueprint 中的 issue id",
                "evidence_explanation": "解释已知证据说明了什么",
                "unknown": ["尚未回答的问题"],
                "validation_question": "下一步要验证的问题",
                "recommendation_rationale": "为什么需要验证",
                "suggested_evidence": ["验证需要补充的证据"],
            }
        ]
    }
    return [
        {
            "role": "system",
            "content": (
                "你是资深电商退货分析负责人。系统已经确定问题列表、排序、"
                "范围、指标、已知事实、证据引用和可信状态。你只负责用中文解释"
                "这些证据、列出尚未回答的问题，并给出验证建议。不得增加或修改"
                "任何数字，不得改写问题 id、排序、范围、指标、已知事实、证据引用"
                "和可信状态。不得把退货样本内占比称为退货率，不得推断因果，"
                "不得提出直接整改、任务、负责人、截止时间或商品开发方案。"
                "只返回 JSON，不要返回 Markdown。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "output_schema": schema,
                    "fixed_blueprint": evidence["blueprint"],
                    "evidence": {
                        "source": evidence["source"],
                        "catalog": evidence["catalog"],
                        "analysis": evidence["analysis"],
                    },
                },
                ensure_ascii=False,
            ),
        },
    ]


def _assemble_content_v6(
    evidence: dict[str, Any],
    payload: Any,
) -> InsightDecisionReportContent:
    if not isinstance(payload, dict):
        raise ValueError("模型返回的报告解释不是 JSON 对象")
    blueprint = evidence["blueprint"]
    generated_by_id = _items_by_id(payload.get("issues"))
    issues = []
    for item in blueprint["issues"]:
        generated = generated_by_id.get(item["id"], {})
        fallback_recommendation = item["fallback_recommendation"]
        unknown = [
            text
            for value in generated.get("unknown", [])
            if isinstance(value, str) and value.strip()
            if (text := _narrative_text(value, "", 300))
        ][:5]
        suggested_evidence = [
            text
            for value in generated.get("suggested_evidence", [])
            if isinstance(value, str) and value.strip()
            if (text := _narrative_text(value, "", 200))
        ][:5]
        issues.append(
            {
                "id": item["id"],
                "rank": item["rank"],
                "title": item["title"],
                "scope": item["scope"],
                "metrics": item["metrics"],
                "known": item["known"],
                "evidence_explanation": _narrative_text(
                    generated.get("evidence_explanation"),
                    item["fallback_evidence_explanation"],
                    800,
                ),
                "unknown": unknown or item["fallback_unknown"],
                "recommendation": {
                    "label": "建议验证",
                    "validation_question": _narrative_text(
                        generated.get("validation_question"),
                        fallback_recommendation["validation_question"],
                        300,
                    ),
                    "rationale": _narrative_text(
                        generated.get("recommendation_rationale"),
                        fallback_recommendation["rationale"],
                        500,
                    ),
                    "suggested_evidence": (
                        suggested_evidence
                        or fallback_recommendation["suggested_evidence"]
                    ),
                },
                "readiness": item["readiness"],
                "evidence_ids": item["evidence_ids"],
            }
        )
    return InsightDecisionReportContent.model_validate(
        {
            "report_type": blueprint["report_type"],
            "title": blueprint["title"],
            "issues": issues,
            "caveats": blueprint["caveats"],
        }
    )


def _messages(evidence: dict[str, Any]) -> list[dict[str, str]]:
    schema = {
        "findings": [
            {
                "id": "使用 fixed_blueprint 中的 finding id",
                "interpretation": "证据解释",
                "implication": "业务含义",
            }
        ],
        "actions": [
            {
                "id": "使用 fixed_blueprint 中的 action id",
                "action": "行动",
                "rationale": "行动理由",
                "success_signal": "验证是否有效的信号",
            }
        ],
        "further_questions": ["仍需回答的问题"],
    }
    return [
        {
            "role": "system",
            "content": (
                "你是资深电商退货分析负责人。请用中文生成面向产品和业务负责人的"
                "退货原因洞察报告。系统已经固定事实、结论、报告结构和证据引用；你只负责"
                "解释这些事实的业务含义，并提出可验证的行动假设。解释必须结合商品热点、"
                "趋势、伴随原因、语义观点或原始评论中的至少一类诊断证据，不能只改写结论。"
                "优先使用 business_issues.cases 中的具体 SKU、分子分母、整体基线、"
                "提升倍数、趋势和已过滤评论上下文，"
                "每项解释先说明信号集中在哪里，再说明仍需验证什么。"
                "明确区分已验证事实、待验证解释和行动假设。"
                "行动必须说明验证对象和判断是否有效的条件。只能使用 evidence 中已有事实，"
                "不要引入新数字，不要把样本占比称为真实退货率，不要推断因果，也不要把"
                "总量最大直接等同于最高行动优先级。"
                "不得输出或修改 evidence_ids、标题、结论和优先级。只返回 JSON，不要返回 Markdown。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "output_schema": schema,
                    "fixed_blueprint": evidence["blueprint"],
                    "evidence": {
                        "source": evidence["source"],
                        "catalog": evidence["catalog"],
                        "analysis": evidence["analysis"],
                    },
                },
                ensure_ascii=False,
            ),
        },
    ]


def _assemble_content(
    evidence: dict[str, Any],
    payload: Any,
) -> InsightReportContent:
    if not isinstance(payload, dict):
        raise ValueError("模型返回的报告解释不是 JSON 对象")
    blueprint = evidence["blueprint"]
    finding_text = _items_by_id(payload.get("findings"))
    action_text = _items_by_id(payload.get("actions"))
    findings = []
    for item in blueprint["findings"]:
        generated = finding_text.get(item["id"], {})
        findings.append(
            {
                "id": item["id"],
                "kind": item["kind"],
                "title": item["title"],
                "conclusion": item["conclusion"],
                "interpretation": _text(
                    generated.get("interpretation"),
                    "该信号来自当前分类结果版本中的重复退货反馈，仍需回看原始评论确认具体情境。",
                    800,
                ),
                "implication": _text(
                    generated.get("implication"),
                    "应把该信号作为排查入口，并通过商品、批次或订单维度验证其影响范围。",
                    500,
                ),
                "evidence_ids": item["evidence_ids"],
            }
        )
    actions = []
    for item in blueprint["actions"]:
        generated = action_text.get(item["id"], {})
        actions.append(
            {
                "id": item["id"],
                "priority": item["priority"],
                "target": item["target"],
                "action": _text(generated.get("action"), item["fallback_action"], 300),
                "rationale": _text(
                    generated.get("rationale"), item["fallback_rationale"], 500
                ),
                "success_signal": _text(
                    generated.get("success_signal"),
                    item["fallback_success_signal"],
                    300,
                ),
                "evidence_ids": item["evidence_ids"],
            }
        )
    questions = [
        _text(value, "", 300)
        for value in payload.get("further_questions", [])
        if isinstance(value, str) and value.strip()
    ][:5]
    return InsightReportContent.model_validate(
        {
            "title": blueprint["title"],
            "executive_summary": blueprint["executive_summary"],
            "findings": findings,
            "actions": actions,
            "further_questions": questions or blueprint["further_questions"],
            "caveats": blueprint["caveats"],
        }
    )


def _items_by_id(value: Any) -> dict[str, dict[str, Any]]:
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items() if isinstance(item, dict)}
    if not isinstance(value, list):
        return {}
    return {
        str(item["id"]): item
        for item in value
        if isinstance(item, dict) and item.get("id")
    }


def _text(value: Any, fallback: str, limit: int) -> str:
    text = str(value or "").strip() or fallback
    return text[:limit]


def _narrative_text(value: Any, fallback: str, limit: int) -> str:
    text = str(value or "").strip()
    if not text or re.search(r"\d", text):
        return fallback
    return text[:limit]


def _validate_evidence_refs(
    content: InsightReportContent,
    known_ids: set[str],
) -> None:
    references = (
        [
            evidence_id
            for item in content.executive_summary
            for evidence_id in item.evidence_ids
        ]
        + [
            evidence_id
            for item in content.findings
            for evidence_id in item.evidence_ids
        ]
        + [evidence_id for item in content.actions for evidence_id in item.evidence_ids]
    )
    unknown = sorted(set(references) - known_ids)
    if unknown:
        raise ValueError(f"报告引用了不存在的证据: {', '.join(unknown)}")


def _validate_issue_evidence_refs(
    content: InsightDecisionReportContent,
    known_ids: set[str],
) -> None:
    references = [
        evidence_id for issue in content.issues for evidence_id in issue.evidence_ids
    ]
    unknown = sorted(set(references) - known_ids)
    if unknown:
        raise ValueError(f"报告引用了不存在的证据: {', '.join(unknown)}")
