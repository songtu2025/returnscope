from __future__ import annotations

from dataclasses import dataclass

from return_semantics.review_conclusions import _audit_conclusions as _audit_conclusions
from return_semantics.review_conclusions import _AuditConclusion as _AuditConclusion
from return_semantics.review_conclusions import (
    _conclusion_matches as _conclusion_matches,
)
from return_semantics.review_conclusions import (
    _dimension_conclusion as _dimension_conclusion,
)
from return_semantics.review_conclusions import (
    _event_group_matches as _event_group_matches,
)
from return_semantics.review_conclusions import _event_groups as _event_groups
from return_semantics.review_conclusions import (
    _orphan_fact_conclusion as _orphan_fact_conclusion,
)
from return_semantics.review_conclusions import _unit_conclusion as _unit_conclusion
from return_semantics.review_conclusions import (
    _unknown_conclusion as _unknown_conclusion,
)
from return_semantics.review_conclusions import (
    classifications_match as classifications_match,
)
from return_semantics.review_evidence import (
    _IGNORED_DISPOSITIONS as _IGNORED_DISPOSITIONS,
)
from return_semantics.review_evidence import _AuditItem as _AuditItem
from return_semantics.review_evidence import _decision_unit_key as _decision_unit_key
from return_semantics.review_evidence import _evidence_matches as _evidence_matches
from return_semantics.review_evidence import _evidence_signature as _evidence_signature
from return_semantics.review_evidence import _fact_evidence as _fact_evidence
from return_semantics.review_evidence import (
    _fragment_sets_cover as _fragment_sets_cover,
)
from return_semantics.review_evidence import _normalize_text as _normalize_text
from return_semantics.review_evidence import (
    _represented_fact_ids,
    _unresolved_conclusion_facts,
)
from return_semantics.review_evidence import _scope_signature as _scope_signature
from return_semantics.review_evidence import _unit_decision_key as _unit_decision_key
from return_semantics.review_evidence import (
    _unit_scope_signature as _unit_scope_signature,
)
from return_semantics.review_evidence import _unordered_match as _unordered_match
from return_semantics.schemas import (
    ExtractedFact,
    ProcessingStatus,
    ReviewDiagnostic,
    SemanticUnit,
    UnknownSemantic,
    ValidatedClassification,
)

MANUAL_ONLY_REASONS = (
    "Amazon 原因与评论方向冲突",
    "评论包含相反标签",
    "评论包含需核对的标签组合",
    "标签规则要求人工复核",
    "语义边界需人工确认",
    "待确认事实 ",
    "fact_v2尚未完成Listing承诺关系核验",
)


_MODEL_MISMATCH_ACTION = "请业务员以原文证据为准，核对两次分析结果并选择正确标签。"


@dataclass(frozen=True)
class _ReviewOutcome:
    evidence_text: str
    evidence: tuple[tuple[str, tuple[str, ...]], ...]
    business_key: tuple[object, ...]
    result: str
    opinion: str
    scope_text: str


def should_run_secondary(result: ValidatedClassification) -> bool:
    if result.status != ProcessingStatus.SECONDARY_REVIEW:
        return False
    return not any(
        blocker in reason
        for reason in result.review_reasons
        for blocker in MANUAL_ONLY_REASONS
    )


def _unit_review_outcome(unit: SemanticUnit) -> _ReviewOutcome:
    scope_parts = [
        f"来源={unit.source_ref}",
        f"体验者={unit.experiencer_ref}",
        f"商品={unit.product_ref}",
        f"规格={unit.variant_ref}",
        f"主体={unit.subject.value}",
        f"部位={unit.part}",
        f"方向={unit.sentiment.value}",
        f"确定性={unit.assertion.value}",
    ]
    if unit.operation:
        scope_parts.append(f"操作={unit.operation}")
    if unit.condition:
        scope_parts.append(f"条件={unit.condition}")
    if unit.reference_basis.value != "NONE":
        scope_parts.append(f"比较基准={unit.reference_basis.value}")
    if unit.implicit:
        scope_parts.append("表达方式=隐含")
    if unit.claim_relation.value != "NONE":
        scope_parts.append(f"宣称关系={unit.claim_relation.value}")
    conclusion = _unit_conclusion(unit)
    return _ReviewOutcome(
        evidence_text=unit.evidence,
        evidence=conclusion.evidence,
        business_key=conclusion.business_key,
        result=unit.label_code,
        opinion=unit.opinion,
        scope_text="；".join(scope_parts),
    )


def _unknown_review_outcome(unknown: UnknownSemantic) -> _ReviewOutcome:
    scope_parts = [
        f"来源={unknown.source_ref}",
        f"体验者={unknown.experiencer_ref}",
        f"商品={unknown.product_ref}",
        f"规格={unknown.variant_ref}",
        f"陈述类型={unknown.statement_type}",
    ]
    if unknown.operation:
        scope_parts.append(f"操作={unknown.operation}")
    if unknown.condition:
        scope_parts.append(f"条件={unknown.condition}")
    if unknown.reference_basis.value != "NONE":
        scope_parts.append(f"比较基准={unknown.reference_basis.value}")
    conclusion = _unknown_conclusion(unknown)
    return _ReviewOutcome(
        evidence_text=unknown.evidence,
        evidence=conclusion.evidence,
        business_key=conclusion.business_key,
        result=unknown.disposition.value,
        opinion=unknown.opinion,
        scope_text="；".join(scope_parts),
    )


def _orphan_fact_review_outcome(fact: ExtractedFact) -> _ReviewOutcome:
    scope_parts = [
        f"来源={fact.source_ref}",
        f"体验者={fact.experiencer_ref}",
        f"商品={fact.product_ref}",
        f"规格={fact.variant_ref}",
        f"主体={fact.subject.value}",
        f"部位={fact.part}",
        f"方向={fact.sentiment.value}",
        f"陈述类型={fact.statement_type}",
    ]
    if fact.operation:
        scope_parts.append(f"操作={fact.operation}")
    if fact.condition:
        scope_parts.append(f"条件={fact.condition}")
    conclusion = _orphan_fact_conclusion(fact)
    return _ReviewOutcome(
        evidence_text=" | ".join(span.text for span in fact.evidence_spans),
        evidence=conclusion.evidence,
        business_key=conclusion.business_key,
        result="UNRESOLVED_FACT",
        opinion=fact.opinion,
        scope_text="；".join(scope_parts),
    )


def _review_outcomes(result: ValidatedClassification) -> list[_ReviewOutcome]:
    outcomes = [_unit_review_outcome(unit) for unit in result.semantic_units]
    outcomes.extend(
        _unknown_review_outcome(unknown)
        for unknown in result.unknown_semantics
        if unknown.disposition not in _IGNORED_DISPOSITIONS
    )
    represented_fact_ids = _represented_fact_ids(result)
    mappings_by_id = {mapping.fact_id: mapping for mapping in result.fact_mappings}
    for fact in _unresolved_conclusion_facts(
        result.extracted_facts, mappings_by_id, represented_fact_ids
    ):
        outcomes.append(_orphan_fact_review_outcome(fact))
    return outcomes


def _outcome_text(outcome: _ReviewOutcome) -> str:
    opinion = f"：{outcome.opinion}" if outcome.opinion else ""
    scope = f"（{outcome.scope_text}）" if outcome.scope_text else ""
    return f"{outcome.result}{opinion}{scope}"


def build_model_difference_diagnostics(
    primary: ValidatedClassification,
    secondary: ValidatedClassification,
) -> list[ReviewDiagnostic]:
    unmatched_secondary = _review_outcomes(secondary)
    unmatched_primary: list[_ReviewOutcome] = []
    for primary_outcome in _review_outcomes(primary):
        match_index = next(
            (
                index
                for index, secondary_outcome in enumerate(unmatched_secondary)
                if primary_outcome.business_key == secondary_outcome.business_key
                and _evidence_matches(
                    primary_outcome.evidence,
                    secondary_outcome.evidence,
                )
            ),
            None,
        )
        if match_index is None:
            unmatched_primary.append(primary_outcome)
        else:
            unmatched_secondary.pop(match_index)

    diagnostics: list[ReviewDiagnostic] = []
    for primary_outcome in unmatched_primary:
        match_index = next(
            (
                index
                for index, secondary_outcome in enumerate(unmatched_secondary)
                if _evidence_matches(
                    primary_outcome.evidence,
                    secondary_outcome.evidence,
                )
            ),
            None,
        )
        secondary_outcome = (
            unmatched_secondary.pop(match_index) if match_index is not None else None
        )
        diagnostics.append(
            ReviewDiagnostic(
                code="MODEL_RESULT_MISMATCH",
                evidence_text=primary_outcome.evidence_text,
                primary_result=_outcome_text(primary_outcome),
                secondary_result=(
                    _outcome_text(secondary_outcome) if secondary_outcome else ""
                ),
                detail=(
                    "两次模型对同一证据给出了不同标签、处置或业务作用域"
                    if secondary_outcome
                    else "复核模型未确认主模型识别的观点"
                ),
                action=_MODEL_MISMATCH_ACTION,
            )
        )
    diagnostics.extend(
        ReviewDiagnostic(
            code="MODEL_RESULT_MISMATCH",
            evidence_text=outcome.evidence_text,
            secondary_result=_outcome_text(outcome),
            detail="主模型未确认复核模型识别的观点",
            action=_MODEL_MISMATCH_ACTION,
        )
        for outcome in unmatched_secondary
    )
    if diagnostics:
        return diagnostics
    return [
        ReviewDiagnostic(
            code="MODEL_RESULT_MISMATCH",
            detail="两次模型的结构化语义结果不一致",
            action=_MODEL_MISMATCH_ACTION,
        )
    ]


def reconcile_secondary(
    primary: ValidatedClassification,
    secondary: ValidatedClassification,
) -> ValidatedClassification:
    model_name = f"{primary.model_name} + {secondary.model_name}"
    if (primary.extracted_facts or secondary.extracted_facts) and any(
        blocker in reason
        for result in (primary, secondary)
        for reason in result.review_reasons
        for blocker in MANUAL_ONLY_REASONS
    ):
        reasons = list(dict.fromkeys(primary.review_reasons + secondary.review_reasons))
        diagnostics = [
            *primary.review_diagnostics,
            *secondary.review_diagnostics,
        ]
        if not classifications_match(primary, secondary):
            reasons = list(dict.fromkeys([*reasons, "两次模型的语义结果不一致"]))
            diagnostics.extend(build_model_difference_diagnostics(primary, secondary))
        return primary.model_copy(
            update={
                "status": ProcessingStatus.MANUAL_REVIEW,
                "review_reasons": reasons,
                "review_diagnostics": diagnostics,
                "model_name": model_name,
            }
        )
    if secondary.status in {
        ProcessingStatus.MANUAL_REVIEW,
        ProcessingStatus.UNKNOWN_SEMANTIC,
        ProcessingStatus.MODEL_ERROR,
    }:
        return primary.model_copy(
            update={
                "status": ProcessingStatus.MANUAL_REVIEW,
                "review_reasons": primary.review_reasons
                + ["二次模型结果未通过程序校验"],
                "review_diagnostics": primary.review_diagnostics
                + [
                    ReviewDiagnostic(
                        code="SECONDARY_RESULT_INVALID",
                        detail="二次模型结果未通过程序校验",
                        action="SYSTEM_RERUN",
                    )
                ],
                "model_name": model_name,
            }
        )

    if classifications_match(primary, secondary):
        return primary.model_copy(
            update={
                "status": ProcessingStatus.AUTO_APPROVED,
                "review_reasons": ["二次模型结果一致"],
                "review_diagnostics": [
                    diagnostic
                    for diagnostic in primary.review_diagnostics
                    if diagnostic.code != "MODEL_RESULT_MISMATCH"
                ],
                "model_name": model_name,
            }
        )

    return primary.model_copy(
        update={
            "status": ProcessingStatus.MANUAL_REVIEW,
            "review_reasons": primary.review_reasons + ["两次模型的语义结果不一致"],
            "review_diagnostics": primary.review_diagnostics
            + build_model_difference_diagnostics(primary, secondary),
            "model_name": model_name,
        }
    )


# 既有入口直接复用拆出的实现，保留原导入和类型路径。
for _entry in (
    _normalize_text,
    _evidence_signature,
    _fragment_sets_cover,
    _evidence_matches,
    _scope_signature,
    _unit_scope_signature,
    _unit_decision_key,
    _decision_unit_key,
    _fact_evidence,
    _unordered_match,
    _AuditConclusion,
    _dimension_conclusion,
    _unit_conclusion,
    _orphan_fact_conclusion,
    _unknown_conclusion,
    _audit_conclusions,
    _conclusion_matches,
    _event_groups,
    _event_group_matches,
    classifications_match,
):
    _entry.__module__ = __name__
_AuditItem.__module__ = __name__
