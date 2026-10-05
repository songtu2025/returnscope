from __future__ import annotations

import json
from typing import Any

from web_backend.insight_report_contracts import InsightReportContent
from web_backend.insight_reports.content_common import _items_by_id, _text


def _messages(evidence: dict[str, Any]) -> list[dict[str, str]]:
    is_returns = evidence.get("source", {}).get("analysis_context") == "returns"
    role = "电商退货分析负责人" if is_returns else "用户反馈语义分析负责人"
    report_name = "退货原因洞察报告" if is_returns else "用户反馈语义洞察报告"
    sample_boundary = (
        "不要把样本占比称为真实退货率" if is_returns else "不要把样本占比称为总体发生率"
    )
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
                f"你是资深{role}。请用中文生成面向产品和业务负责人的"
                f"{report_name}。系统已经固定事实、结论、报告结构和证据引用；你只负责"
                "解释这些事实的业务含义，并提出可验证的行动假设。解释必须结合商品热点、"
                "趋势、伴随原因、语义观点或原始评论中的至少一类诊断证据，不能只改写结论。"
                "优先使用 business_issues.cases 中的具体 SKU、分子分母、整体基线、"
                "提升倍数、趋势和已过滤评论上下文，"
                "每项解释先说明信号集中在哪里，再说明仍需验证什么。"
                "明确区分已验证事实、待验证解释和行动假设。"
                "行动必须说明验证对象和判断是否有效的条件。只能使用 evidence 中已有事实，"
                f"不要引入新数字，{sample_boundary}，不要推断因果，也不要把"
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
    is_returns = evidence.get("source", {}).get("analysis_context") == "returns"
    feedback_label = "退货反馈" if is_returns else "用户反馈"
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
                    f"该信号来自当前分类结果版本中的重复{feedback_label}，"
                    "仍需回看原始反馈确认具体情境。",
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
