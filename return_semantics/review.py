from __future__ import annotations

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
from return_semantics.review_evidence import _scope_signature as _scope_signature
from return_semantics.review_evidence import _unit_decision_key as _unit_decision_key
from return_semantics.review_evidence import (
    _unit_scope_signature as _unit_scope_signature,
)
from return_semantics.review_evidence import _unordered_match as _unordered_match
from return_semantics.review_outcomes import (
    _MODEL_MISMATCH_ACTION as _MODEL_MISMATCH_ACTION,
)
from return_semantics.review_outcomes import (
    _orphan_fact_review_outcome as _orphan_fact_review_outcome,
)
from return_semantics.review_outcomes import _outcome_text as _outcome_text
from return_semantics.review_outcomes import _review_outcomes as _review_outcomes
from return_semantics.review_outcomes import _ReviewOutcome as _ReviewOutcome
from return_semantics.review_outcomes import (
    _unit_review_outcome as _unit_review_outcome,
)
from return_semantics.review_outcomes import (
    _unknown_review_outcome as _unknown_review_outcome,
)
from return_semantics.review_outcomes import (
    build_model_difference_diagnostics as build_model_difference_diagnostics,
)
from return_semantics.schemas import (
    ProcessingStatus,
    ReviewDiagnostic,
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


def should_run_secondary(result: ValidatedClassification) -> bool:
    if result.status != ProcessingStatus.SECONDARY_REVIEW:
        return False
    return not any(
        blocker in reason
        for reason in result.review_reasons
        for blocker in MANUAL_ONLY_REASONS
    )


def reconcile_secondary(
    primary: ValidatedClassification,
    secondary: ValidatedClassification,
) -> ValidatedClassification:
    model_name = f"{primary.model_name} + {secondary.model_name}"
    if _has_manual_review_blocker(primary, secondary):
        return _reconcile_manual_review(primary, secondary, model_name)
    if secondary.status in {
        ProcessingStatus.MANUAL_REVIEW,
        ProcessingStatus.UNKNOWN_SEMANTIC,
        ProcessingStatus.MODEL_ERROR,
    }:
        return _reconcile_invalid_secondary(primary, model_name)

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


def _has_manual_review_blocker(
    primary: ValidatedClassification,
    secondary: ValidatedClassification,
) -> bool:
    if not (primary.extracted_facts or secondary.extracted_facts):
        return False
    return any(
        blocker in reason
        for result in (primary, secondary)
        for reason in result.review_reasons
        for blocker in MANUAL_ONLY_REASONS
    )


def _reconcile_manual_review(
    primary: ValidatedClassification,
    secondary: ValidatedClassification,
    model_name: str,
) -> ValidatedClassification:
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


def _reconcile_invalid_secondary(
    primary: ValidatedClassification,
    model_name: str,
) -> ValidatedClassification:
    return primary.model_copy(
        update={
            "status": ProcessingStatus.MANUAL_REVIEW,
            "review_reasons": primary.review_reasons + ["二次模型结果未通过程序校验"],
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


# 既有入口直接复用拆出的实现，保留原导入和类型路径。
for _entry in (
    _ReviewOutcome,
    _unit_review_outcome,
    _unknown_review_outcome,
    _orphan_fact_review_outcome,
    _review_outcomes,
    _outcome_text,
    build_model_difference_diagnostics,
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
