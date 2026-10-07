from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from return_semantics.fact_extraction import (
    CoverageMergeResult,
    FactPipelineCancelled,
    coverage_audit_messages,
    coverage_correction_messages,
    merge_coverage_facts,
    validate_coverage_correction,
)
from return_semantics.schemas import ExtractedFact, ReviewDiagnostic, TaxonomyConfig


@dataclass(frozen=True, kw_only=True)
class _CoverageAuditContext:
    comment: str
    taxonomy: TaxonomyConfig
    call: Callable
    metrics: dict[str, int]


def _coverage_audit_failed(
    facts: list[ExtractedFact],
    exc: Exception,
) -> CoverageMergeResult:
    return CoverageMergeResult(
        facts=facts,
        added=0,
        rejected=0,
        diagnostics=[
            ReviewDiagnostic(
                code="COVERAGE_AUDIT_FAILED",
                detail=f"覆盖审计未完成：{exc}",
                action="SYSTEM_RERUN",
            )
        ],
    )


def _coverage_repair_failed(
    merged: CoverageMergeResult,
    exc: Exception,
) -> CoverageMergeResult:
    return CoverageMergeResult(
        facts=merged.facts,
        added=merged.added,
        rejected=merged.rejected,
        diagnostics=[
            diagnostic.model_copy(
                update={
                    "detail": (f"{diagnostic.detail}；覆盖审计自动修复未完成：{exc}")
                }
            )
            for diagnostic in merged.diagnostics
        ],
        rejections=merged.rejections,
    )


def _repair_fact_coverage(
    merged: CoverageMergeResult,
    *,
    original_count: int,
    context: _CoverageAuditContext,
) -> CoverageMergeResult:
    context.metrics["coverage_audit_repair_calls"] = 1
    try:
        response = context.call(
            coverage_correction_messages(
                context.comment,
                merged.facts,
                merged.rejections,
                context.taxonomy,
            )
        )
        validate_coverage_correction(response, merged.rejected)
        repaired = merge_coverage_facts(
            merged.facts,
            response,
            comment=context.comment,
            taxonomy=context.taxonomy,
        )
    except FactPipelineCancelled:
        raise
    except Exception as exc:
        merged = _coverage_repair_failed(merged, exc)
    else:
        context.metrics["coverage_audit_repaired_facts"] = repaired.added
        merged = CoverageMergeResult(
            facts=repaired.facts,
            added=len(repaired.facts) - original_count,
            rejected=repaired.rejected,
            diagnostics=repaired.diagnostics,
            rejections=repaired.rejections,
        )
    return merged


def _audit_fact_coverage(
    facts: list[ExtractedFact],
    *,
    comment: str,
    taxonomy: TaxonomyConfig,
    call: Callable,
    metrics: dict[str, int],
) -> CoverageMergeResult:
    metrics["coverage_audit_added_facts"] = 0
    metrics["coverage_audit_rejected_facts"] = 0
    metrics["coverage_audit_failures"] = 0
    metrics["coverage_audit_repair_calls"] = 0
    metrics["coverage_audit_repaired_facts"] = 0
    try:
        response = call(coverage_audit_messages(comment, facts, taxonomy))
        merged = merge_coverage_facts(
            facts,
            response,
            comment=comment,
            taxonomy=taxonomy,
        )
    except FactPipelineCancelled:
        raise
    except Exception as exc:
        metrics["coverage_audit_failures"] += 1
        return _coverage_audit_failed(facts, exc)
    if merged.rejections:
        context = _CoverageAuditContext(
            comment=comment, taxonomy=taxonomy, call=call, metrics=metrics
        )
        merged = _repair_fact_coverage(
            merged, original_count=len(facts), context=context
        )

    metrics["coverage_audit_added_facts"] = merged.added
    metrics["coverage_audit_rejected_facts"] = merged.rejected
    if merged.rejected:
        metrics["coverage_audit_failures"] = 1
    return merged
