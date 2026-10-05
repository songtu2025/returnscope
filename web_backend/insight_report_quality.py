from __future__ import annotations

from typing import Any

from web_backend.insight_report_contracts import ReportQualityGate
from web_backend.insight_reports.quality_context import (
    _apply_quality_metadata,
    _prepare_live_quality,
)
from web_backend.insight_reports.quality_filtering import (
    _sanitize_analysis,
    _sanitize_catalog,
)
from web_backend.insight_reports.quality_narrative import (
    _apply_actions,
    _apply_summaries,
    _decision_readiness,
    _quality_gate_status,
)


def _evaluate_live_quality(
    content: dict[str, Any],
    evidence: dict[str, Any],
    text_quality: dict[str, Any],
) -> dict[str, Any]:
    context = _prepare_live_quality(content, evidence, text_quality)
    _apply_quality_metadata(context)
    _sanitize_analysis(context)
    _sanitize_catalog(context)
    quality_issues = _apply_summaries(context)
    _apply_actions(context)
    decision_readiness = _decision_readiness(context)
    quality_gate = ReportQualityGate.model_validate(
        {
            "status": _quality_gate_status(context),
            "issues": quality_issues,
            "text_quality": context.text_quality,
            "product_mapping": context.product_mapping,
            "consistency": context.consistency,
            "decision_readiness": decision_readiness,
        }
    ).model_dump()
    return {
        "content": context.content,
        "evidence": context.evidence,
        "quality_gate": quality_gate,
    }
