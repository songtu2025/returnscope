from __future__ import annotations

from return_semantics.schemas import (
    AssertionCode,
    ClaimDefinition,
    ClaimRelation,
    LabelDefinition,
    ModelClassification,
    SemanticDisposition,
    SemanticUnit,
    SentimentCode,
    TaxonomyConfig,
    UnknownSemantic,
)
from return_semantics.semantic_guardrails import (
    normalize_semantic_unit,
    unknown_semantic_from_unit,
)
from return_semantics.validator_state import _ValidationContext, _ValidationState


def _basic_unit_error(
    unit: SemanticUnit,
    comment: str,
    labels: dict[str, LabelDefinition],
    allowed_parts: set[str],
) -> str | None:
    label = labels.get(unit.label_code)
    if label is None:
        return f"未知标签: {unit.label_code}"
    if unit.evidence not in comment:
        return f"证据不在原评论中: {unit.label_code}"
    if unit.sentiment not in label.allowed_sentiments:
        return f"标签情感方向无效: {unit.label_code}"
    if unit.part not in allowed_parts:
        return f"部位不适用于当前品类: {unit.part}"
    return None


def _requires_boundary_review(
    unit: SemanticUnit,
    taxonomy: TaxonomyConfig,
) -> bool:
    if taxonomy.recognition_profile not in {"semantic_v1", "fact_v2"}:
        return False
    evidence_boundary = any(
        rule.label_code == unit.label_code and rule.semantic_requirement
        for rule in taxonomy.validation_rules.evidence_requirements
    )
    claim_boundary = any(
        rule.label_code == unit.label_code
        and rule.semantic_requirement
        and rule.claim_id == unit.claim_id
        for rule in taxonomy.validation_rules.claim_evidence_requirements
    )
    return evidence_boundary or claim_boundary


def _claim_error(
    unit: SemanticUnit,
    label: LabelDefinition,
    claim_map: dict[str, ClaimDefinition],
) -> str | None:
    if unit.claim_relation == ClaimRelation.NONE:
        if unit.claim_id is not None:
            return f"无承诺关系却提供了承诺编号: {unit.label_code}"
        return None
    claim = claim_map.get(unit.claim_id or "")
    if claim is None:
        return f"承诺编号无效: {unit.claim_id}"
    if unit.label_code not in claim.allowed_label_codes:
        return f"标签与承诺不匹配: {unit.label_code}, {unit.claim_id}"
    if unit.claim_id not in label.allowed_claim_ids:
        return f"标签未允许该承诺: {unit.label_code}, {unit.claim_id}"
    if (
        unit.sentiment == SentimentCode.POSITIVE
        and unit.claim_relation == ClaimRelation.CONTRADICTS
    ):
        return f"正面语义不能反驳承诺: {unit.label_code}"
    if (
        unit.sentiment == SentimentCode.NEGATIVE
        and unit.claim_relation == ClaimRelation.SUPPORTS
    ):
        return f"负面语义不能支持承诺: {unit.label_code}"
    return None


def _record_unit_signature(
    unit: SemanticUnit,
    recognition_profile: str,
    seen_units: set[str],
) -> bool:
    signature = unit.model_dump_json(
        exclude=(
            {
                "fact_id",
                "fact_ids",
                "actor_ref",
                "source_ref",
                "experiencer_ref",
                "product_ref",
                "variant_ref",
                "event_ref",
                "reference_basis",
                "statement_type",
                "operation",
                "condition",
                "evidence_source",
            }
            if recognition_profile != "fact_v2"
            else None
        )
    )
    if recognition_profile != "fact_v2" and signature in seen_units:
        return False
    seen_units.add(signature)
    return True


def _append_abstained_unit(unit: SemanticUnit, state: _ValidationState) -> None:
    if unit.fact_id is None:
        state.soft_reasons.append(f"语义并非已确认事实: {unit.label_code}")
    state.unknown_semantics.append(
        unknown_semantic_from_unit(
            unit,
            opinion=unit.opinion,
            reason=f"{unit.statement_type}不形成已确认标签",
            disposition=SemanticDisposition.EXPECTED_ABSTENTION,
        )
    )


def _process_affirmed_unit(
    unit: SemanticUnit,
    context: _ValidationContext,
    state: _ValidationState,
) -> None:
    if _requires_boundary_review(unit, context.taxonomy):
        state.soft_reasons.append(f"语义边界需人工确认: {unit.label_code}")

    original_label_code = unit.label_code
    normalized_unit, unknown = normalize_semantic_unit(unit, context.taxonomy)
    if unknown is not None:
        state.unknown_semantics.append(unknown)
        state.guardrail_removed_codes.add(original_label_code)
        return
    if normalized_unit is None:
        return

    error = _claim_error(
        normalized_unit,
        context.labels[original_label_code],
        context.claim_map,
    )
    if error is not None:
        state.hard_reasons.append(error)
        return
    if normalized_unit.implicit:
        state.soft_reasons.append(f"存在隐含语义: {normalized_unit.label_code}")
    state.valid_units.append(normalized_unit)


def _process_unit(
    unit: SemanticUnit,
    context: _ValidationContext,
    seen_units: set[str],
    state: _ValidationState,
) -> None:
    if not _record_unit_signature(
        unit,
        context.taxonomy.recognition_profile,
        seen_units,
    ):
        return
    error = _basic_unit_error(
        unit,
        context.comment,
        context.labels,
        context.allowed_parts,
    )
    if error is not None:
        state.hard_reasons.append(error)
        return
    if unit.assertion != AssertionCode.AFFIRMED:
        _append_abstained_unit(unit, state)
        return
    _process_affirmed_unit(unit, context, state)


def _validate_units(
    model_result: ModelClassification,
    context: _ValidationContext,
    state: _ValidationState,
) -> None:
    seen_units: set[str] = set()
    for unit in model_result.semantic_units:
        _process_unit(
            unit,
            context,
            seen_units,
            state,
        )


def _validate_unknown_evidence(
    unknown_semantics: list[UnknownSemantic],
    comment: str,
    hard_reasons: list[str],
) -> None:
    for unknown in unknown_semantics:
        if unknown.evidence not in comment:
            hard_reasons.append("未知语义证据不在原评论中")
