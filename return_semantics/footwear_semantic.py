from __future__ import annotations

from return_semantics.evidence_location import restore_unique_source_excerpt
from return_semantics.schemas import (
    AssertionCode,
    ClaimRelation,
    ModelClassification,
    SemanticUnit,
    TaxonomyConfig,
)
from return_semantics.semantic_guardrails import normalize_semantic_unit

_SPECIFIC_BREAKAGES = {
    "QUALITY_SEAM_FAILURE_U1",
    "QUALITY_TEAR_U1",
    "QUALITY_SEPARATION_U1",
    "QUALITY_HOLE_U1",
    "QUALITY_FRAYING_U2",
}
_GENERIC_BREAKAGE = "QUALITY_FALLING_APART_U1"
_DISPLAY_FIELDS = {"opinion", "decision_reason", "causal_attribution_reason"}


def _restore_units(result: ModelClassification, comment: str) -> ModelClassification:
    units = [
        item.model_copy(
            update={"evidence": restore_unique_source_excerpt(item.evidence, comment)}
        )
        for item in result.semantic_units
    ]
    unknowns = [
        item.model_copy(
            update={"evidence": restore_unique_source_excerpt(item.evidence, comment)}
        )
        for item in result.unknown_semantics
    ]
    return result.model_copy(
        update={"semantic_units": units, "unknown_semantics": unknowns}
    )


def _specific_breakage_scopes(
    units: list[SemanticUnit], taxonomy: TaxonomyConfig, comment: str
) -> set[str]:
    eligible = {
        (label.code, direction)
        for label in taxonomy.labels
        if label.code in _SPECIFIC_BREAKAGES
        for direction in label.allowed_sentiments
    }
    return {
        unit.model_dump_json(exclude=_DISPLAY_FIELDS | {"label_code"})
        for unit in units
        if (unit.label_code, unit.sentiment) in eligible
        and unit.evidence in comment
        and unit.part in taxonomy.allowed_parts
        and unit.assertion == AssertionCode.AFFIRMED
        and unit.claim_relation == ClaimRelation.NONE
        and unit.claim_id is None
        and normalize_semantic_unit(unit, taxonomy)[0] is not None
    }


def normalize_footwear_semantics(
    result: ModelClassification, comment: str, taxonomy: TaxonomyConfig
) -> ModelClassification:
    """仅合并同引文同范围的重复表达和已有具体失效方式的笼统标签。"""
    restored = _restore_units(result, comment)
    scopes = _specific_breakage_scopes(restored.semantic_units, taxonomy, comment)
    retained: dict[str, SemanticUnit] = {}
    for unit in restored.semantic_units:
        if (
            unit.label_code == _GENERIC_BREAKAGE
            and unit.model_dump_json(exclude=_DISPLAY_FIELDS | {"label_code"}) in scopes
        ):
            continue
        retained.setdefault(unit.model_dump_json(exclude=_DISPLAY_FIELDS), unit)
    units = list(retained.values())
    primary = restored.primary_label_codes
    if any(
        unit.label_code == _GENERIC_BREAKAGE for unit in restored.semantic_units
    ) and not any(unit.label_code == _GENERIC_BREAKAGE for unit in units):
        primary = [code for code in primary if code != _GENERIC_BREAKAGE]
    return restored.model_copy(
        update={"semantic_units": units, "primary_label_codes": primary}
    )
