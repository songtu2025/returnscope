from __future__ import annotations

import unicodedata
from collections import defaultdict
from collections.abc import Callable, Iterable
from typing import TypeVar

from return_semantics.schemas import (
    DimensionDecision,
    DimensionScope,
    ExtractedFact,
    FactMapping,
    FactRole,
    SemanticDisposition,
    SemanticUnit,
    ValidatedClassification,
)

_IGNORED_DISPOSITIONS = {
    SemanticDisposition.EXPECTED_ABSTENTION,
    SemanticDisposition.EVIDENCE_ONLY,
    SemanticDisposition.OUT_OF_SCOPE,
}

_AuditItem = TypeVar("_AuditItem")


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


def _represented_fact_ids(result: ValidatedClassification) -> set[str]:
    represented = {
        fact_id
        for unit in result.semantic_units
        for fact_id in (unit.fact_ids or ([unit.fact_id] if unit.fact_id else []))
    }
    represented.update(
        unknown.fact_id for unknown in result.unknown_semantics if unknown.fact_id
    )
    return represented


def _unresolved_conclusion_facts(
    facts: Iterable[ExtractedFact],
    mappings_by_id: dict[str, FactMapping],
    represented_fact_ids: set[str],
) -> Iterable[ExtractedFact]:
    for fact in facts:
        mapping = mappings_by_id.get(fact.fact_id)
        if (
            fact.fact_id in represented_fact_ids
            or fact.fact_role != FactRole.CONCLUSION
        ):
            continue
        if mapping is not None and (
            mapping.label_codes or mapping.disposition in _IGNORED_DISPOSITIONS
        ):
            continue
        yield fact
