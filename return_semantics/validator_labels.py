from __future__ import annotations

from itertools import product

from return_semantics.schemas import (
    LabelDefinition,
    ModelClassification,
    SemanticUnit,
    SentimentCode,
    TaxonomyConfig,
)
from return_semantics.validator_state import _unique, _ValidationState


def _is_problem_unit(
    unit: SemanticUnit,
    taxonomy: TaxonomyConfig,
    labels: dict[str, LabelDefinition],
) -> bool:
    if unit.sentiment == SentimentCode.NEGATIVE:
        return True
    if unit.sentiment != SentimentCode.NEUTRAL:
        return False
    neutral_labels = taxonomy.validation_rules.neutral_reason_labels
    if neutral_labels is not None:
        return unit.label_code in neutral_labels
    return labels[unit.label_code].group in {"其他", "其他原因"}


def _project_label_codes(
    valid_units: list[SemanticUnit],
    taxonomy: TaxonomyConfig,
    labels: dict[str, LabelDefinition],
) -> tuple[list[str], list[str]]:
    problem_codes = _unique(
        unit.label_code
        for unit in valid_units
        if _is_problem_unit(unit, taxonomy, labels)
    )
    positive_codes = _unique(
        unit.label_code
        for unit in valid_units
        if unit.sentiment == SentimentCode.POSITIVE
    )
    return problem_codes, positive_codes


def _project_primary_codes(
    model_result: ModelClassification,
    taxonomy: TaxonomyConfig,
) -> list[str]:
    primary_codes = _unique(model_result.primary_label_codes)
    if taxonomy.recognition_profile != "fact_v2":
        return primary_codes
    primary_facts = {
        fact.fact_id for fact in model_result.extracted_facts if fact.is_primary_reason
    }
    explicit_codes = {
        code
        for mapping in model_result.fact_mappings
        if mapping.fact_id in primary_facts
        for code in mapping.label_codes
    }
    return [code for code in primary_codes if code in explicit_codes]


def _validate_primary_codes(
    primary_codes: list[str],
    problem_codes: list[str],
    taxonomy: TaxonomyConfig,
    state: _ValidationState,
) -> list[str]:
    invalid_primary = set(primary_codes).difference(problem_codes)
    hard_invalid_primary = invalid_primary.difference(state.guardrail_removed_codes)
    if hard_invalid_primary:
        state.hard_reasons.append(f"主因不属于问题标签: {sorted(hard_invalid_primary)}")
    if invalid_primary:
        primary_codes = [code for code in primary_codes if code in problem_codes]
    if (
        taxonomy.recognition_profile != "fact_v2"
        and len(problem_codes) == 1
        and not primary_codes
    ):
        primary_codes = problem_codes.copy()
    return primary_codes


def _has_evidence_overlap(
    codes: list[str],
    valid_units: list[SemanticUnit],
    comment: str,
) -> bool:
    candidates = [
        [unit for unit in valid_units if unit.label_code == code] for code in codes
    ]
    return any(
        len({unit.part for unit in units} - {"UNSPECIFIED"}) <= 1
        and max(comment.index(unit.evidence) for unit in units)
        < min(comment.index(unit.evidence) + len(unit.evidence) for unit in units)
        for units in product(*candidates)
    )


def _conflict_reasons(
    valid_units: list[SemanticUnit],
    taxonomy: TaxonomyConfig,
    comment: str,
) -> list[str]:
    all_label_codes = {unit.label_code for unit in valid_units}
    reasons: list[str] = []
    for codes in taxonomy.validation_rules.conflicting_label_sets:
        conflict_set = set(codes)
        if not conflict_set.issubset(all_label_codes):
            continue
        if (
            taxonomy.validation_rules.conflict_scope == "evidence"
            and not _has_evidence_overlap(codes, valid_units, comment)
        ):
            continue
        message = (
            "评论包含需核对的标签组合"
            if taxonomy.validation_rules.conflict_scope == "evidence"
            else "评论包含相反标签"
        )
        reasons.append(f"{message}: {sorted(conflict_set)}")
    return reasons
