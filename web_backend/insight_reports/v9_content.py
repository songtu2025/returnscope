from __future__ import annotations

import json
from typing import Any

from web_backend.insight_report_contracts import ConciseInsightReportContent
from web_backend.insight_reports.content_common import _items_by_id
from web_backend.insight_reports.v8_content import (
    _EMPTY_EXPLANATION,
    _UNVERIFIED,
    evaluate_theme_quality,
)


def concise_messages(evidence: dict[str, Any]) -> list[dict[str, str]]:
    brief = evidence["blueprint"]["concise"]
    return [
        {
            "role": "system",
            "content": (
                "为产品团队写结论优先的简明洞察。只补每条洞察的产品含义和每条行动的执行建议，"
                "各用一句中文，不复述标题、已有数字或证据原文，不新增因果、地点、版本、指标或事实。"
                "句子应说清取舍或对照验证对象。引用仅列入 evidence_ids，不把编号或数字写进叙述。"
                "只返回 JSON。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "report": {
                        key: brief[key]
                        for key in ("title", "judgment", "insights", "actions")
                    },
                    "output": {
                        "insights": [
                            {
                                "id": "既有编号",
                                "meaning": "产品含义",
                                "evidence_ids": ["对应已给证据"],
                            }
                        ],
                        "actions": [
                            {
                                "id": "既有编号",
                                "action": "验证建议",
                                "evidence_ids": ["对应已给证据"],
                            }
                        ],
                    },
                },
                ensure_ascii=False,
            ),
        },
    ]


def assemble_concise_content(
    evidence: dict[str, Any], payload: Any
) -> ConciseInsightReportContent:
    if not isinstance(payload, dict):
        raise ValueError("模型返回的简明洞察不是 JSON 对象")
    brief = evidence["blueprint"]["concise"]
    return ConciseInsightReportContent.model_validate(
        {
            **brief,
            "insights": _with_narrative(
                brief["insights"], payload.get("insights"), "meaning"
            ),
            "actions": _with_narrative(
                brief["actions"], payload.get("actions"), "action"
            ),
        }
    )


def _with_narrative(
    items: list[dict[str, Any]], payload: Any, field: str
) -> list[dict[str, Any]]:
    supplied = _items_by_id(payload)
    return [
        {**item, field: _bounded_text(item, supplied.get(item["id"], {}), field)}
        for item in items
    ]


def _bounded_text(item: dict[str, Any], proposal: dict[str, Any], field: str) -> str:
    text, refs = proposal.get(field), proposal.get("evidence_ids")
    if (
        isinstance(text, str)
        and 12 <= len(text.strip()) <= 85
        and isinstance(refs, list)
        and refs
        and all(isinstance(ref, str) and ref in item["evidence_ids"] for ref in refs)
        and not _UNVERIFIED.search(text)
        and not _EMPTY_EXPLANATION.search(text)
        and item["title"] not in text
    ):
        return text.strip()
    return item[field]


def evaluate_concise_quality(
    content: dict[str, Any], evidence: dict[str, Any], text_quality: dict[str, Any]
) -> dict[str, Any]:
    result = evaluate_theme_quality(content, evidence, text_quality)
    notes = evidence["blueprint"]["concise"]["boundaries"]
    extra = notes[len(evidence["blueprint"]["boundaries"]) :]
    result["content"]["boundaries"].extend(extra)
    return result
