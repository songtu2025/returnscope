from __future__ import annotations

from return_semantics.analysis_context import RETURNS_CONTEXT, AnalysisContext
from return_semantics.schemas import (
    ModelClassification,
    ProcessingStatus,
    ReviewDiagnostic,
    SemanticDisposition,
    SemanticRelationType,
)
from return_semantics.validator_labels import _conflict_reasons
from return_semantics.validator_state import _ValidationContext, _ValidationState


def _append_required_label_reviews(
    context: _ValidationContext,
    state: _ValidationState,
) -> None:
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
    _append_required_label_reviews(context, state)
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
