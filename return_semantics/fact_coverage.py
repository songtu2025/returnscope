from __future__ import annotations

from dataclasses import dataclass

from return_semantics.fact_evidence import _restore_evidence_spans, _validate_facts
from return_semantics.fact_routing import (
    _allowed_labels_by_fact,
    _normalize_fact_branch_codes,
)
from return_semantics.schemas import (
    ExtractedFact,
    FactExtraction,
    FactExtractionSource,
    ReviewDiagnostic,
    TaxonomyConfig,
)


@dataclass(frozen=True)
class CoverageFactRejection:
    raw_fact: object
    diagnostic: ReviewDiagnostic


@dataclass(frozen=True)
class CoverageMergeResult:
    facts: list[ExtractedFact]
    added: int
    rejected: int
    diagnostics: list[ReviewDiagnostic]
    rejections: tuple[CoverageFactRejection, ...] = ()


@dataclass(frozen=True, kw_only=True)
class _CoverageCandidateContext:
    accepted: list[ExtractedFact]
    known_ids: set[str]
    known_identities: set[tuple]
    taxonomy: TaxonomyConfig
    comment: str


def validate_coverage_correction(
    payload: FactExtraction | dict,
    expected_count: int,
) -> FactExtraction | dict:
    """修复结果必须逐项回应失败候选，不能静默丢弃事实。"""
    facts = (
        payload.facts if isinstance(payload, FactExtraction) else payload.get("facts")
    )
    if not isinstance(facts, list) or len(facts) != expected_count:
        raise ValueError(f"覆盖审计修复必须返回 {expected_count} 条候选事实")
    return payload


def _coverage_fact_identity(fact: ExtractedFact) -> tuple:
    return (
        fact.actor_ref,
        fact.source_ref,
        fact.experiencer_ref,
        fact.product_ref,
        fact.variant_ref,
        fact.reference_basis,
        fact.subject,
        fact.opinion.strip().casefold(),
        fact.sentiment,
        fact.part,
        fact.operation.strip().casefold(),
        fact.condition.strip().casefold(),
        tuple((span.source, span.text) for span in fact.evidence_spans),
    )


def _coverage_failure_diagnostic(
    raw_fact: object,
    exc: TypeError | ValueError,
) -> ReviewDiagnostic:
    evidence = ""
    if isinstance(raw_fact, dict):
        spans = raw_fact.get("evidence_spans")
        if isinstance(spans, list):
            evidence = " | ".join(
                str(span.get("text") or "").strip()
                for span in spans
                if isinstance(span, dict) and str(span.get("text") or "").strip()
            )
    return ReviewDiagnostic(
        code="COVERAGE_AUDIT_FAILED",
        evidence_text=evidence,
        detail=f"覆盖审计候选事实未通过校验：{exc}",
        action="SYSTEM_RERUN",
    )


def _coverage_raw_facts(additions: FactExtraction | dict) -> list[object]:
    if isinstance(additions, FactExtraction):
        raw_facts: list[object] = list(additions.facts)
    elif isinstance(additions, dict):
        if set(additions) != {"facts"} or not isinstance(additions["facts"], list):
            raise ValueError("覆盖审计输出必须是只包含facts数组的对象")
        raw_facts = additions["facts"]
    else:
        raise ValueError("覆盖审计输出必须是对象")
    return raw_facts


def _validated_coverage_candidate(
    raw_fact: object, *, context: _CoverageCandidateContext
) -> tuple[ExtractedFact, tuple]:
    if isinstance(raw_fact, ExtractedFact):
        fact = raw_fact.model_copy(
            update={"extraction_source": FactExtractionSource.COVERAGE}
        )
    elif isinstance(raw_fact, dict):
        fact = ExtractedFact.model_validate(
            {**raw_fact, "extraction_source": FactExtractionSource.COVERAGE}
        )
    else:
        raise ValueError("新增事实必须是对象")
    fact = _normalize_fact_branch_codes([fact], context.taxonomy)[0]
    fact = _restore_evidence_spans([fact], context.comment)[0]
    if fact.fact_id in context.known_ids:
        raise ValueError("覆盖审计不得复用现有事实编号")
    identity = _coverage_fact_identity(fact)
    if identity in context.known_identities:
        raise ValueError("覆盖审计不得新增已覆盖的重复命题")
    candidate = [*context.accepted, fact]
    _validate_facts(candidate, context.comment, context.taxonomy)
    _allowed_labels_by_fact(candidate, context.taxonomy)
    return (fact, identity)


def merge_coverage_facts(
    existing_facts: list[ExtractedFact],
    additions: FactExtraction | dict,
    *,
    comment: str,
    taxonomy: TaxonomyConfig,
) -> CoverageMergeResult:
    """逐项隔离非法新增事实，保留同批次中的其他合法事实。"""
    raw_facts = _coverage_raw_facts(additions)
    accepted = list(existing_facts)
    known_ids = {fact.fact_id for fact in accepted}
    known_identities = {_coverage_fact_identity(fact) for fact in accepted}
    rejected = 0
    diagnostics: list[ReviewDiagnostic] = []
    rejections: list[CoverageFactRejection] = []
    context = _CoverageCandidateContext(
        accepted=accepted,
        known_ids=known_ids,
        known_identities=known_identities,
        taxonomy=taxonomy,
        comment=comment,
    )
    for raw_fact in raw_facts:
        try:
            fact, identity = _validated_coverage_candidate(raw_fact, context=context)
        except (TypeError, ValueError) as exc:
            rejected += 1
            diagnostic = _coverage_failure_diagnostic(raw_fact, exc)
            diagnostics.append(diagnostic)
            rejections.append(
                CoverageFactRejection(raw_fact=raw_fact, diagnostic=diagnostic)
            )
            continue
        accepted.append(fact)
        known_ids.add(fact.fact_id)
        known_identities.add(identity)
    return CoverageMergeResult(
        facts=accepted,
        added=len(accepted) - len(existing_facts),
        rejected=rejected,
        diagnostics=diagnostics,
        rejections=tuple(rejections),
    )
