from __future__ import annotations

import unicodedata
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TypeVar

from return_semantics.schemas import (
    DimensionDecision,
    DimensionScope,
    ExtractedFact,
    FactRole,
    ProcessingStatus,
    SemanticDisposition,
    SemanticUnit,
    UnknownSemantic,
    ValidatedClassification,
)

MANUAL_ONLY_REASONS = (
    "Amazon 原因与评论方向冲突",
    "评论包含相反标签",
    "评论包含需核对的标签组合",
    "标签规则要求人工复核",
    "语义边界需人工确认",
    "待确认事实 ",
    "fact_v2尚未完成Listing承诺关系核验",
)

_IGNORED_DISPOSITIONS = {
    SemanticDisposition.EXPECTED_ABSTENTION,
    SemanticDisposition.EVIDENCE_ONLY,
    SemanticDisposition.OUT_OF_SCOPE,
}

_AuditItem = TypeVar("_AuditItem")


@dataclass(frozen=True)
class _AuditConclusion:
    event_ref: str
    business_key: tuple[object, ...]
    evidence: tuple[tuple[str, tuple[str, ...]], ...]


def should_run_secondary(result: ValidatedClassification) -> bool:
    if result.status != ProcessingStatus.SECONDARY_REVIEW:
        return False
    return not any(
        blocker in reason
        for reason in result.review_reasons
        for blocker in MANUAL_ONLY_REASONS
    )


def _normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value)).casefold()
    return "".join(character for character in text if character.isalnum())


def _evidence_signature(
    spans: Iterable[tuple[object, object]],
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    by_source: dict[str, set[str]] = defaultdict(set)
    for source, text in spans:
        normalized = _normalize_text(text)
        if normalized:
            by_source[str(source)].add(normalized)
    return tuple(
        (source, tuple(sorted(values))) for source, values in sorted(by_source.items())
    )


def _fragment_sets_cover(
    source: tuple[str, ...],
    target: tuple[str, ...],
) -> bool:
    return all(
        any(fragment in candidate or candidate in fragment for candidate in target)
        for fragment in source
    )


def _evidence_matches(
    first: tuple[tuple[str, tuple[str, ...]], ...],
    second: tuple[tuple[str, tuple[str, ...]], ...],
) -> bool:
    if first == second:
        return True
    first_by_source = dict(first)
    second_by_source = dict(second)
    if first_by_source.keys() != second_by_source.keys():
        return False
    return all(
        _fragment_sets_cover(first_by_source[source], second_by_source[source])
        or _fragment_sets_cover(second_by_source[source], first_by_source[source])
        for source in first_by_source
    )


def _scope_signature(scope: DimensionScope) -> tuple[object, ...]:
    return (
        scope.source_ref,
        scope.experiencer_ref,
        scope.product_ref,
        scope.variant_ref,
        scope.reference_basis.value,
        scope.part,
        scope.operation,
        _normalize_text(scope.condition),
    )


def _unit_scope_signature(unit: SemanticUnit) -> tuple[object, ...]:
    return (
        unit.actor_ref,
        unit.source_ref,
        unit.experiencer_ref,
        unit.product_ref,
        unit.variant_ref,
        unit.reference_basis.value,
        unit.part,
        unit.operation,
        _normalize_text(unit.condition),
    )


def _unit_decision_key(unit: SemanticUnit) -> tuple[object, ...]:
    return (
        unit.label_code,
        unit.event_ref,
        unit.source_ref,
        unit.experiencer_ref,
        unit.product_ref,
        unit.variant_ref,
        unit.reference_basis.value,
        unit.part,
        unit.operation,
        _normalize_text(unit.condition),
    )


def _decision_unit_key(decision: DimensionDecision) -> tuple[object, ...]:
    scope = decision.scope
    return (
        decision.verdict_label_code,
        scope.event_ref,
        scope.source_ref,
        scope.experiencer_ref,
        scope.product_ref,
        scope.variant_ref,
        scope.reference_basis.value,
        scope.part,
        scope.operation,
        _normalize_text(scope.condition),
    )


def _fact_evidence(
    facts: Iterable[ExtractedFact],
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    return _evidence_signature(
        (span.source.value, span.text) for fact in facts for span in fact.evidence_spans
    )


def _dimension_conclusion(
    decision: DimensionDecision,
    facts_by_id: dict[str, ExtractedFact],
    unit: SemanticUnit | None,
) -> _AuditConclusion:
    supporting_facts = [
        facts_by_id[fact_id]
        for fact_id in decision.supporting_fact_ids
        if fact_id in facts_by_id
    ]
    evidence = _fact_evidence(supporting_facts)
    if not evidence and unit is not None:
        evidence = _evidence_signature(((unit.evidence_source.value, unit.evidence),))
    return _AuditConclusion(
        event_ref=decision.scope.event_ref,
        business_key=(
            "DIMENSION",
            decision.parent_code,
            decision.verdict_label_code,
            _scope_signature(decision.scope),
            tuple(sorted({fact.actor_ref for fact in supporting_facts})),
            tuple(sorted({fact.sentiment.value for fact in supporting_facts})),
            (
                (
                    unit.sentiment.value,
                    unit.assertion.value,
                    unit.claim_relation.value,
                    unit.claim_id or "",
                )
                if unit is not None
                else ()
            ),
        ),
        evidence=evidence,
    )


def _unit_conclusion(unit: SemanticUnit) -> _AuditConclusion:
    return _AuditConclusion(
        event_ref=unit.event_ref,
        business_key=(
            "LABEL",
            unit.label_code,
            unit.sentiment.value,
            unit.assertion.value,
            unit.subject.value,
            _unit_scope_signature(unit),
            unit.implicit,
            unit.claim_relation.value,
            unit.claim_id or "",
        ),
        evidence=_evidence_signature(((unit.evidence_source.value, unit.evidence),)),
    )


def _orphan_fact_conclusion(fact: ExtractedFact) -> _AuditConclusion:
    return _AuditConclusion(
        event_ref=fact.event_ref,
        business_key=(
            "UNRESOLVED_FACT",
            fact.actor_ref,
            fact.source_ref,
            fact.experiencer_ref,
            fact.product_ref,
            fact.variant_ref,
            fact.reference_basis.value,
            fact.subject.value,
            fact.statement_type,
            fact.sentiment.value,
            fact.part,
            fact.operation,
            _normalize_text(fact.condition),
            fact.is_primary_reason,
        ),
        evidence=_fact_evidence((fact,)),
    )


def _unknown_conclusion(unknown: UnknownSemantic) -> _AuditConclusion:
    return _AuditConclusion(
        event_ref=unknown.event_ref,
        business_key=(
            "UNKNOWN",
            unknown.disposition.value,
            unknown.actor_ref,
            unknown.source_ref,
            unknown.experiencer_ref,
            unknown.product_ref,
            unknown.variant_ref,
            unknown.reference_basis.value,
            unknown.statement_type,
            unknown.operation,
            _normalize_text(unknown.condition),
            unknown.evidence_source.value,
        ),
        evidence=_evidence_signature(
            ((unknown.evidence_source.value, unknown.evidence),)
        ),
    )


def _audit_conclusions(result: ValidatedClassification) -> list[_AuditConclusion]:
    facts_by_id = {fact.fact_id: fact for fact in result.extracted_facts}
    mappings_by_id = {mapping.fact_id: mapping for mapping in result.fact_mappings}
    decision_unit_counts = Counter(
        _decision_unit_key(decision) for decision in result.dimension_decisions
    )
    units_by_key: dict[tuple[object, ...], list[SemanticUnit]] = defaultdict(list)
    for unit in result.semantic_units:
        units_by_key[_unit_decision_key(unit)].append(unit)

    conclusions: list[_AuditConclusion] = []
    for decision in result.dimension_decisions:
        units = units_by_key[_decision_unit_key(decision)]
        unit = units.pop() if units else None
        conclusions.append(_dimension_conclusion(decision, facts_by_id, unit))

    remaining_decision_units = Counter(decision_unit_counts)
    for unit in result.semantic_units:
        key = _unit_decision_key(unit)
        if remaining_decision_units[key]:
            remaining_decision_units[key] -= 1
            continue
        conclusions.append(_unit_conclusion(unit))

    decision_fact_ids = {
        fact_id
        for decision in result.dimension_decisions
        for fact_id in (*decision.supporting_fact_ids, *decision.context_fact_ids)
    }
    for fact in result.extracted_facts:
        mapping = mappings_by_id.get(fact.fact_id)
        if fact.fact_id in decision_fact_ids or fact.fact_role != FactRole.CONCLUSION:
            continue
        if mapping is not None and (
            mapping.label_codes or mapping.disposition in _IGNORED_DISPOSITIONS
        ):
            continue
        conclusions.append(_orphan_fact_conclusion(fact))

    conclusions.extend(
        _unknown_conclusion(unknown)
        for unknown in result.unknown_semantics
        if unknown.disposition not in _IGNORED_DISPOSITIONS
    )
    return conclusions


def _conclusion_matches(
    first: _AuditConclusion,
    second: _AuditConclusion,
) -> bool:
    return first.business_key == second.business_key and _evidence_matches(
        first.evidence,
        second.evidence,
    )


def _unordered_match(
    first: list[_AuditItem],
    second: list[_AuditItem],
    matches: Callable[[_AuditItem, _AuditItem], bool],
) -> bool:
    if len(first) != len(second):
        return False
    if not first:
        return True
    candidate = first[0]
    return any(
        matches(candidate, other)
        and _unordered_match(
            first[1:],
            second[:index] + second[index + 1 :],
            matches,
        )
        for index, other in enumerate(second)
    )


def _event_groups(result: ValidatedClassification) -> list[list[_AuditConclusion]]:
    groups: dict[str, list[_AuditConclusion]] = defaultdict(list)
    for conclusion in _audit_conclusions(result):
        groups[conclusion.event_ref].append(conclusion)
    return list(groups.values())


def _event_group_matches(
    first: list[_AuditConclusion],
    second: list[_AuditConclusion],
) -> bool:
    return _unordered_match(
        first,
        second,
        _conclusion_matches,
    )


def classifications_match(
    first: ValidatedClassification,
    second: ValidatedClassification,
) -> bool:
    if tuple(sorted(first.primary_label_codes)) != tuple(
        sorted(second.primary_label_codes)
    ):
        return False
    return _unordered_match(
        _event_groups(first),
        _event_groups(second),
        _event_group_matches,
    )


def reconcile_secondary(
    primary: ValidatedClassification,
    secondary: ValidatedClassification,
) -> ValidatedClassification:
    model_name = f"{primary.model_name} + {secondary.model_name}"
    if (primary.extracted_facts or secondary.extracted_facts) and any(
        blocker in reason
        for result in (primary, secondary)
        for reason in result.review_reasons
        for blocker in MANUAL_ONLY_REASONS
    ):
        return primary.model_copy(
            update={
                "status": ProcessingStatus.MANUAL_REVIEW,
                "review_reasons": list(
                    dict.fromkeys(primary.review_reasons + secondary.review_reasons)
                ),
                "model_name": model_name,
            }
        )
    if secondary.status in {
        ProcessingStatus.MANUAL_REVIEW,
        ProcessingStatus.UNKNOWN_SEMANTIC,
        ProcessingStatus.MODEL_ERROR,
    }:
        return primary.model_copy(
            update={
                "status": ProcessingStatus.MANUAL_REVIEW,
                "review_reasons": primary.review_reasons
                + ["二次模型结果未通过程序校验"],
                "model_name": model_name,
            }
        )

    if classifications_match(primary, secondary):
        return primary.model_copy(
            update={
                "status": ProcessingStatus.AUTO_APPROVED,
                "review_reasons": ["二次模型结果一致"],
                "model_name": model_name,
            }
        )

    return primary.model_copy(
        update={
            "status": ProcessingStatus.MANUAL_REVIEW,
            "review_reasons": primary.review_reasons + ["两次模型的语义结果不一致"],
            "model_name": model_name,
        }
    )
