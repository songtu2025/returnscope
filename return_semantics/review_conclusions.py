from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from return_semantics.review_evidence import (
    _IGNORED_DISPOSITIONS,
    _decision_unit_key,
    _evidence_matches,
    _evidence_signature,
    _fact_evidence,
    _normalize_text,
    _scope_signature,
    _unit_decision_key,
    _unit_scope_signature,
    _unordered_match,
    _unresolved_conclusion_facts,
)
from return_semantics.schemas import (
    DimensionDecision,
    ExtractedFact,
    SemanticUnit,
    UnknownSemantic,
    ValidatedClassification,
)


@dataclass(frozen=True)
class _AuditConclusion:
    event_ref: str
    business_key: tuple[object, ...]
    evidence: tuple[tuple[str, tuple[str, ...]], ...]


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
        matched_unit = units.pop() if units else None
        conclusions.append(_dimension_conclusion(decision, facts_by_id, matched_unit))

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
    for fact in _unresolved_conclusion_facts(
        result.extracted_facts, mappings_by_id, decision_fact_ids
    ):
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
    return _unordered_match(
        _event_groups(first),
        _event_groups(second),
        _event_group_matches,
    )
