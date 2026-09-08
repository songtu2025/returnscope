from __future__ import annotations

from return_semantics.schemas import (
    ClaimRelation,
    SemanticUnit,
    TaxonomyConfig,
    UnknownSemantic,
)


def normalize_semantic_unit(
    unit: SemanticUnit,
    taxonomy: TaxonomyConfig,
) -> tuple[SemanticUnit | None, UnknownSemantic | None]:
    evidence = unit.evidence.lower()
    rules = taxonomy.validation_rules

    for rule in rules.evidence_requirements:
        if taxonomy.recognition_profile == "semantic_v1" and rule.semantic_requirement:
            continue
        if unit.label_code == rule.label_code and not any(
            cue.lower() in evidence for cue in rule.cues
        ):
            return None, UnknownSemantic(
                opinion=rule.unknown_opinion,
                evidence=unit.evidence,
                reason=rule.unknown_reason,
            )

    for rule in rules.implicit_evidence_rules:
        if taxonomy.recognition_profile == "semantic_v1" and rule.semantic_requirement:
            continue
        if unit.label_code == rule.label_code and any(
            cue.lower() in evidence for cue in rule.cues
        ):
            unit = unit.model_copy(update={"implicit": True})

    for rule in rules.claim_evidence_requirements:
        if taxonomy.recognition_profile == "semantic_v1" and rule.semantic_requirement:
            continue
        if (
            unit.label_code == rule.label_code
            and unit.claim_id == rule.claim_id
            and not any(cue.lower() in evidence for cue in rule.cues)
        ):
            unit = unit.model_copy(
                update={
                    "claim_relation": ClaimRelation.NONE,
                    "claim_id": None,
                }
            )

    return unit, None
