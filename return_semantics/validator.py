from __future__ import annotations

from itertools import product

from return_semantics.analysis_context import RETURNS_CONTEXT, AnalysisContext
from return_semantics.comment_summary import compile_comment_semantics
from return_semantics.schemas import ClaimDefinition as ClaimDefinition
from return_semantics.schemas import CommentSummary as CommentSummary
from return_semantics.schemas import (
    LabelDefinition,
    ListingClaimsConfig,
    ModelClassification,
    ProcessingStatus,
    ReviewDiagnostic,
    SemanticDisposition,
    SemanticRelationType,
    SemanticUnit,
    SentimentCode,
    TaxonomyConfig,
    ValidatedClassification,
)
from return_semantics.schemas import SemanticRelation as SemanticRelation
from return_semantics.schemas import UnknownSemantic as UnknownSemantic
from return_semantics.semantic_guardrails import (
    apply_fallback_precedence,
)
from return_semantics.validator_state import (
    _unique as _unique,
)
from return_semantics.validator_state import (
    _ValidationContext as _ValidationContext,
)
from return_semantics.validator_state import (
    _ValidationRequest as _ValidationRequest,
)
from return_semantics.validator_state import (
    _ValidationState as _ValidationState,
)
from return_semantics.validator_units import (
    _basic_unit_error as _basic_unit_error,
)
from return_semantics.validator_units import (
    _claim_error as _claim_error,
)
from return_semantics.validator_units import (
    _process_unit as _process_unit,
)
from return_semantics.validator_units import (
    _record_unit_signature as _record_unit_signature,
)
from return_semantics.validator_units import (
    _requires_boundary_review as _requires_boundary_review,
)
from return_semantics.validator_units import (
    _validate_units as _validate_units,
)
from return_semantics.validator_units import (
    _validate_unknown_evidence as _validate_unknown_evidence,
)


def validate_classification(
    classification_key: str,
    comment: str,
    reason: str,
    model_result: ModelClassification,
    taxonomy: TaxonomyConfig,
    claims: ListingClaimsConfig,
    model_name: str,
    prompt_version: str,
    analysis_context: AnalysisContext = RETURNS_CONTEXT,
) -> ValidatedClassification:
    result, _ = _validate_classification(
        _ValidationRequest(
            classification_key,
            comment,
            reason,
            model_result,
            taxonomy,
            claims,
            model_name,
            prompt_version,
            analysis_context,
        )
    )
    return result


def collect_output_errors(
    model_result: ModelClassification,
    comment: str,
    taxonomy: TaxonomyConfig,
    claims: ListingClaimsConfig,
) -> list[str]:
    """复用正式校验提取硬错误，供纠正原始输出；软语义风险仍交复核。"""
    _, errors = _validate_classification(
        _ValidationRequest(
            "",
            comment,
            "",
            model_result,
            taxonomy,
            claims,
            "",
            "",
            "review",
        )
    )
    return errors


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


def _append_classification_reviews(
    reason: str,
    analysis_context: AnalysisContext,
    model_result: ModelClassification,
    context: _ValidationContext,
    state: _ValidationState,
) -> None:
    if analysis_context == RETURNS_CONTEXT:
        opposite_codes = set(
            context.taxonomy.validation_rules.opposite_reason_labels.get(reason, [])
        )
        if set(state.problem_codes).intersection(opposite_codes):
            state.soft_reasons.append("Amazon 原因与评论方向冲突")
    state.soft_reasons.extend(
        _conflict_reasons(
            state.valid_units,
            context.taxonomy,
            context.comment,
        )
    )
    if any(
        relation.relation_type == SemanticRelationType.CONFLICT
        for relation in state.semantic_relations
    ):
        state.soft_reasons.append("同一语义范围内存在相反的已确认事实")
    required_review_labels = set(
        context.taxonomy.validation_rules.required_review_labels
    )
    state.soft_reasons.extend(
        f"标签规则要求人工复核: {unit.label_code}；证据={unit.evidence}"
        for unit in state.valid_units
        if unit.label_code in required_review_labels
    )
    for unit in state.valid_units:
        if unit.label_code not in required_review_labels:
            continue
        label = context.labels[unit.label_code]
        readable_path = " → ".join(part for part in (label.group, label.name) if part)
        state.review_diagnostics.append(
            ReviewDiagnostic(
                code="LABEL_RULE_REVIEW_REQUIRED",
                evidence_text=unit.evidence,
                primary_result=f"{unit.label_code}: {readable_path}",
                detail="标签体系 required_review_labels 规则要求人工判断",
                action="请业务员核对原文证据是否足以支持该标签，并确认保留或修改标签。",
            )
        )
    if model_result.needs_review:
        state.soft_reasons.append("模型要求复核")
    if not state.valid_units and not state.unknown_semantics:
        state.soft_reasons.append("没有可确认的语义标签")
    if (
        state.positive_codes
        and not state.problem_codes
        and analysis_context == RETURNS_CONTEXT
    ):
        state.soft_reasons.append("只有正面信息，无法确认退货原因")


def _status_for(state: _ValidationState) -> ProcessingStatus:
    has_boundary_review = any(
        reason.startswith("语义边界需人工确认:") for reason in state.soft_reasons
    )
    if state.hard_reasons or has_boundary_review:
        return ProcessingStatus.MANUAL_REVIEW
    if any(
        item.disposition
        in {
            SemanticDisposition.TAXONOMY_GAP,
            SemanticDisposition.MAPPING_UNCERTAIN,
        }
        for item in state.unknown_semantics
    ):
        return ProcessingStatus.UNKNOWN_SEMANTIC
    if state.soft_reasons:
        return ProcessingStatus.SECONDARY_REVIEW
    return ProcessingStatus.AUTO_APPROVED


def _validate_classification(
    request: _ValidationRequest,
) -> tuple[ValidatedClassification, list[str]]:
    model_result = request.model_result
    taxonomy = request.taxonomy
    labels = {label.code: label for label in taxonomy.labels}
    context = _ValidationContext(
        request.comment,
        taxonomy,
        labels,
        set(taxonomy.allowed_parts),
        {claim.claim_id: claim for claim in request.claims.claims},
    )
    state = _ValidationState(
        soft_reasons=list(model_result.review_reasons),
        unknown_semantics=list(model_result.unknown_semantics),
        review_diagnostics=list(model_result.review_diagnostics),
    )
    _validate_units(model_result, context, state)
    apply_fallback_precedence(
        state.valid_units,
        set(taxonomy.validation_rules.fallback_label_codes),
    )
    _validate_unknown_evidence(
        state.unknown_semantics,
        request.comment,
        state.hard_reasons,
    )
    state.problem_codes, state.positive_codes = _project_label_codes(
        state.valid_units,
        taxonomy,
        labels,
    )
    state.semantic_relations, state.comment_summary = compile_comment_semantics(
        state.valid_units,
        taxonomy,
        labels,
    )
    state.primary_codes = _validate_primary_codes(
        _project_primary_codes(model_result, taxonomy),
        state.problem_codes,
        taxonomy,
        state,
    )
    _append_classification_reviews(
        request.reason,
        request.analysis_context,
        model_result,
        context,
        state,
    )
    state.hard_reasons = _unique(state.hard_reasons)
    state.soft_reasons = _unique(state.soft_reasons)

    result = ValidatedClassification(
        extracted_facts=model_result.extracted_facts,
        fact_mappings=model_result.fact_mappings,
        dimension_decisions=model_result.dimension_decisions,
        semantic_relations=state.semantic_relations,
        comment_summary=state.comment_summary,
        review_diagnostics=state.review_diagnostics,
        classification_key=request.classification_key,
        semantic_units=state.valid_units,
        unknown_semantics=state.unknown_semantics,
        problem_label_codes=state.problem_codes,
        positive_label_codes=state.positive_codes,
        primary_label_codes=state.primary_codes,
        status=_status_for(state),
        review_reasons=state.hard_reasons
        + state.soft_reasons
        + [
            (
                f"未知语义: {item.reason}"
                if item.disposition == SemanticDisposition.TAXONOMY_GAP
                else f"未映射语义[{item.disposition.value}]: {item.reason}"
            )
            for item in state.unknown_semantics
            if item.disposition
            in {
                SemanticDisposition.TAXONOMY_GAP,
                SemanticDisposition.MAPPING_UNCERTAIN,
            }
        ],
        model_name=request.model_name,
        prompt_version=request.prompt_version,
        taxonomy_version=taxonomy.version,
    )
    return result, state.hard_reasons


for _entry in (
    _unique,
    _ValidationState,
    _ValidationContext,
    _ValidationRequest,
    _basic_unit_error,
    _requires_boundary_review,
    _claim_error,
    _record_unit_signature,
    _process_unit,
    _validate_units,
    _validate_unknown_evidence,
):
    _entry.__module__ = __name__
