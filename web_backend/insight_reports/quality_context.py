from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from web_backend.insight_report_consistency import _report_consistency
from web_backend.insight_reports.quality_issues import source_quality_issues

PRODUCT_EVIDENCE_MARKERS = (
    ".hotspot.",
    ".variant.",
    "business_issue.",
    "issue_case.",
)
TEXT_EVIDENCE_MARKERS = (".sample.", ".opinion.")


@dataclass
class _LiveQualityEvaluation:
    content: dict[str, Any]
    evidence: dict[str, Any]
    text_quality: dict[str, Any]
    source: dict[str, Any]
    analysis: dict[str, Any]
    catalog: dict[str, Any]
    consistency: dict[str, Any]
    product_mapping: dict[str, Any]
    review_bias: dict[str, Any]
    source_issues: list[dict[str, Any]]
    product_names: list[str]
    text_trusted: bool
    mapping_trusted: bool
    pending_count: int


def _prepare_live_quality(
    content: dict[str, Any],
    evidence: dict[str, Any],
    text_quality: dict[str, Any],
) -> _LiveQualityEvaluation:
    safe_content = deepcopy(content)
    safe_evidence = deepcopy(evidence)
    source = safe_evidence.setdefault("source", {})
    analysis = safe_evidence.setdefault("analysis", {})
    catalog = safe_evidence.setdefault("catalog", {})
    consistency = _report_consistency(
        safe_content,
        safe_evidence,
        require_information_diagnostics=True,
    )
    product_mapping = source.get("product_mapping", {})
    text_trusted = text_quality.get("status") != "needs_review"
    mapping_trusted = product_mapping.get("status") != "needs_review"
    pending_count = int(source.get("pending_review_record_count") or 0)
    review_bias = analysis.get("review_bias", {})
    source_issues: list[dict[str, Any]] = []
    if not text_trusted:
        source_issues.append(
            {
                "code": "text_quality",
                "label": "评论文本质量未通过",
                "detail": str(text_quality.get("note") or "评论文本质量需要核对。"),
                "evidence_ids": ["text_quality", "scope"],
            }
        )
    source_issues.extend(
        source_quality_issues(
            product_mapping, review_bias, pending_count, mapping_trusted=mapping_trusted
        )
    )
    product_names = [
        str(item.get("value") or "")
        for item in analysis.get("product_reason_matrix", [])
        if item.get("value")
    ]
    return _LiveQualityEvaluation(
        content=safe_content,
        evidence=safe_evidence,
        text_quality=text_quality,
        source=source,
        analysis=analysis,
        catalog=catalog,
        consistency=consistency,
        product_mapping=product_mapping,
        review_bias=review_bias,
        source_issues=source_issues,
        product_names=product_names,
        text_trusted=text_trusted,
        mapping_trusted=mapping_trusted,
        pending_count=pending_count,
    )


def _apply_quality_metadata(context: _LiveQualityEvaluation) -> None:
    context.source["text_quality"] = context.text_quality
    context.source["quality_issue_codes"] = [
        item["code"] for item in context.source_issues
    ]
    context.source["report_status"] = (
        "provisional" if context.source_issues else "final"
    )
    context.analysis["text_quality"] = context.text_quality
    context.catalog["text_quality"] = {
        "label": "评论文本质量",
        "value": str(context.text_quality.get("note") or "未发现明显编码异常"),
        "data": context.text_quality,
    }
