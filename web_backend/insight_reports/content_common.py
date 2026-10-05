from __future__ import annotations

import re
from typing import Any

from web_backend.insight_report_contracts import (
    InsightDecisionReportContent,
    InsightReportContent,
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
