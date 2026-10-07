from __future__ import annotations

from return_semantics.analysis_context import RETURNS_CONTEXT, AnalysisContext
from return_semantics.comment_summary import compile_comment_semantics
from return_semantics.schemas import ClaimDefinition as ClaimDefinition
from return_semantics.schemas import CommentSummary as CommentSummary
from return_semantics.schemas import LabelDefinition as LabelDefinition
from return_semantics.schemas import (
    ListingClaimsConfig,
    ModelClassification,
    SemanticDisposition,
    TaxonomyConfig,
    ValidatedClassification,
)
from return_semantics.schemas import ReviewDiagnostic as ReviewDiagnostic
from return_semantics.schemas import SemanticRelation as SemanticRelation
from return_semantics.schemas import SemanticUnit as SemanticUnit
from return_semantics.schemas import UnknownSemantic as UnknownSemantic
from return_semantics.semantic_guardrails import (
    apply_fallback_precedence,
)
from return_semantics.validator_labels import (
    _conflict_reasons as _conflict_reasons,
)
from return_semantics.validator_labels import (
    _has_evidence_overlap as _has_evidence_overlap,
)
from return_semantics.validator_labels import (
    _is_problem_unit as _is_problem_unit,
)
from return_semantics.validator_labels import (
    _project_label_codes as _project_label_codes,
)
from return_semantics.validator_labels import (
    _project_primary_codes as _project_primary_codes,
)
from return_semantics.validator_labels import (
    _validate_primary_codes as _validate_primary_codes,
)
from return_semantics.validator_reviews import (
    _append_classification_reviews as _append_classification_reviews,
)
from return_semantics.validator_reviews import (
    _status_for as _status_for,
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


def _prepare_validation(
    request: _ValidationRequest,
) -> tuple[_ValidationContext, _ValidationState]:
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
    return context, state


def _unknown_review_reasons(state: _ValidationState) -> list[str]:
    return [
        f"未知语义: {item.reason}"
        if item.disposition == SemanticDisposition.TAXONOMY_GAP
        else f"未映射语义[{item.disposition.value}]: {item.reason}"
        for item in state.unknown_semantics
        if item.disposition
        in {SemanticDisposition.TAXONOMY_GAP, SemanticDisposition.MAPPING_UNCERTAIN}
    ]


def _classification_result(
    request: _ValidationRequest,
    state: _ValidationState,
) -> ValidatedClassification:
    model_result = request.model_result
    return ValidatedClassification(
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
        + _unknown_review_reasons(state),
        model_name=request.model_name,
        prompt_version=request.prompt_version,
        taxonomy_version=request.taxonomy.version,
    )


def _validate_classification(
    request: _ValidationRequest,
) -> tuple[ValidatedClassification, list[str]]:
    context, state = _prepare_validation(request)
    _validate_units(request.model_result, context, state)
    apply_fallback_precedence(
        state.valid_units,
        set(request.taxonomy.validation_rules.fallback_label_codes),
    )
    _validate_unknown_evidence(
        state.unknown_semantics,
        request.comment,
        state.hard_reasons,
    )
    state.problem_codes, state.positive_codes = _project_label_codes(
        state.valid_units,
        request.taxonomy,
        context.labels,
    )
    state.semantic_relations, state.comment_summary = compile_comment_semantics(
        state.valid_units,
        request.taxonomy,
        context.labels,
    )
    state.primary_codes = _validate_primary_codes(
        _project_primary_codes(request.model_result, request.taxonomy),
        state.problem_codes,
        request.taxonomy,
        state,
    )
    _append_classification_reviews(
        request.reason,
        request.analysis_context,
        request.model_result,
        context,
        state,
    )
    state.hard_reasons = _unique(state.hard_reasons)
    state.soft_reasons = _unique(state.soft_reasons)

    result = _classification_result(request, state)
    return result, state.hard_reasons


for _entry in (
    _is_problem_unit,
    _project_label_codes,
    _project_primary_codes,
    _validate_primary_codes,
    _has_evidence_overlap,
    _conflict_reasons,
    _append_classification_reviews,
    _status_for,
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
