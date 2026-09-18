from __future__ import annotations

from return_semantics.schemas import (
    ClaimRelation,
    SemanticDisposition,
    SemanticUnit,
    TaxonomyConfig,
    UnknownSemantic,
)

_FALLBACK_SCOPE_FIELDS = (
    "source_ref",
    "experiencer_ref",
    "product_ref",
    "variant_ref",
    "subject",
)


def apply_fallback_precedence(
    units: list[SemanticUnit], fallback_codes: set[str]
) -> set[str]:
    """兜底标签只保留独立事实，并合并模型拆分的重复事实。"""
    if not fallback_codes:
        return set()
    specific_units = [unit for unit in units if unit.label_code not in fallback_codes]
    retained: list[SemanticUnit] = []
    suppressed_fact_ids: set[str] = set()
    for unit in units:
        specific = next(
            (
                item
                for item in specific_units
                if _same_fact_or_evidence_scope(unit, item)
            ),
            None,
        )
        if unit.label_code not in fallback_codes:
            retained.append(unit)
            continue
        if specific is not None:
            suppressed_fact_ids.update(
                unit.fact_ids or ([unit.fact_id] if unit.fact_id else [])
            )
            continue
        duplicate = next(
            (
                item
                for item in retained
                if item.label_code == unit.label_code
                and _same_fact_or_evidence_scope(unit, item)
            ),
            None,
        )
        if duplicate is None:
            retained.append(unit)
            continue
        duplicate.fact_ids = list(dict.fromkeys([*duplicate.fact_ids, *unit.fact_ids]))
    units[:] = retained
    return suppressed_fact_ids


def _same_fact_or_evidence_scope(left: SemanticUnit, right: SemanticUnit) -> bool:
    left_ids = set(left.fact_ids or ([left.fact_id] if left.fact_id else []))
    right_ids = set(right.fact_ids or ([right.fact_id] if right.fact_id else []))
    if left_ids.intersection(right_ids):
        return True
    if any(
        getattr(left, field_name) != getattr(right, field_name)
        for field_name in _FALLBACK_SCOPE_FIELDS
    ):
        return False
    left_evidence = " ".join(left.evidence.split()).casefold()
    right_evidence = " ".join(right.evidence.split()).casefold()
    return left_evidence in right_evidence or right_evidence in left_evidence


def unknown_semantic_from_unit(
    unit: SemanticUnit,
    *,
    opinion: str,
    reason: str,
    disposition: SemanticDisposition,
) -> UnknownSemantic:
    return UnknownSemantic(
        opinion=opinion,
        evidence=unit.evidence,
        reason=reason,
        disposition=disposition,
        fact_id=unit.fact_id,
        actor_ref=unit.actor_ref,
        source_ref=unit.source_ref,
        experiencer_ref=unit.experiencer_ref,
        product_ref=unit.product_ref,
        variant_ref=unit.variant_ref,
        event_ref=unit.event_ref,
        reference_basis=unit.reference_basis,
        statement_type=unit.statement_type,
        operation=unit.operation,
        condition=unit.condition,
        evidence_source=unit.evidence_source,
    )


def normalize_semantic_unit(
    unit: SemanticUnit,
    taxonomy: TaxonomyConfig,
) -> tuple[SemanticUnit | None, UnknownSemantic | None]:
    evidence = unit.evidence.lower()
    rules = taxonomy.validation_rules

    for evidence_rule in rules.evidence_requirements:
        if (
            taxonomy.recognition_profile == "semantic_v1"
            and evidence_rule.semantic_requirement
        ):
            continue
        if unit.label_code == evidence_rule.label_code and not any(
            cue.lower() in evidence for cue in evidence_rule.cues
        ):
            return None, unknown_semantic_from_unit(
                unit,
                opinion=evidence_rule.unknown_opinion,
                reason=evidence_rule.unknown_reason,
                disposition=SemanticDisposition.MAPPING_UNCERTAIN,
            )

    for implicit_rule in rules.implicit_evidence_rules:
        if (
            taxonomy.recognition_profile == "semantic_v1"
            and implicit_rule.semantic_requirement
        ):
            continue
        if unit.label_code == implicit_rule.label_code and any(
            cue.lower() in evidence for cue in implicit_rule.cues
        ):
            unit = unit.model_copy(update={"implicit": True})

    for claim_rule in rules.claim_evidence_requirements:
        if (
            taxonomy.recognition_profile == "semantic_v1"
            and claim_rule.semantic_requirement
        ):
            continue
        if (
            unit.label_code == claim_rule.label_code
            and unit.claim_id == claim_rule.claim_id
            and not any(cue.lower() in evidence for cue in claim_rule.cues)
        ):
            unit = unit.model_copy(
                update={
                    "claim_relation": ClaimRelation.NONE,
                    "claim_id": None,
                }
            )

    return unit, None
