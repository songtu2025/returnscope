from __future__ import annotations

import json
from typing import Any

from web_backend.insight_report_contracts import InsightDecisionReportContent
from web_backend.insight_reports.content_common import _items_by_id, _narrative_text


def _messages_v6(evidence: dict[str, Any]) -> list[dict[str, str]]:
    is_returns = evidence.get("source", {}).get("analysis_context") == "returns"
    referenced_ids = {
        evidence_id
        for issue in evidence["blueprint"]["issues"]
        for evidence_id in issue["evidence_ids"]
    }
    referenced_catalog = {
        evidence_id: item
        for evidence_id, item in evidence["catalog"].items()
        if evidence_id in referenced_ids
    }
    role = "电商退货分析负责人" if is_returns else "用户反馈语义分析负责人"
    sample_boundary = (
        "不得把退货样本内占比称为退货率"
        if is_returns
        else "不得把反馈样本内占比称为总体发生率"
    )
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
                f"你是资深{role}。系统已经确定问题列表、排序、"
                "范围、指标、已知事实、证据引用和可信状态。你只负责用中文解释"
                "这些证据、列出尚未回答的问题，并给出验证建议。不得增加或修改"
                "任何数字，不得改写问题 id、排序、范围、指标、已知事实、证据引用"
                f"和可信状态。{sample_boundary}，不得推断因果，"
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
                        "catalog": referenced_catalog,
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
