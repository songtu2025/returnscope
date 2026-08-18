from __future__ import annotations

from return_semantics.schemas import (
    ProcessingStatus,
    ValidatedClassification,
)

MANUAL_ONLY_REASONS = (
    "Amazon 原因与评论方向冲突",
    "评论包含相反标签",
)


def should_run_secondary(result: ValidatedClassification) -> bool:
    if result.status != ProcessingStatus.SECONDARY_REVIEW:
        return False
    return not any(
        blocker in reason
        for reason in result.review_reasons
        for blocker in MANUAL_ONLY_REASONS
    )


def _signature(result: ValidatedClassification) -> tuple[object, ...]:
    units = sorted(
        (
            unit.label_code,
            unit.sentiment.value,
            unit.part.value,
            unit.evidence,
            unit.claim_relation.value,
            unit.claim_id or "",
        )
        for unit in result.semantic_units
    )
    return (
        tuple(units),
        tuple(sorted(result.problem_label_codes)),
        tuple(sorted(result.positive_label_codes)),
        tuple(sorted(result.primary_label_codes)),
    )


def classifications_match(
    first: ValidatedClassification,
    second: ValidatedClassification,
) -> bool:
    return _signature(first) == _signature(second)


def reconcile_secondary(
    primary: ValidatedClassification,
    secondary: ValidatedClassification,
) -> ValidatedClassification:
    model_name = f"{primary.model_name} + {secondary.model_name}"
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
                "model_name": model_name,
            }
        )

    if _signature(primary) == _signature(secondary):
        return primary.model_copy(
            update={
                "status": ProcessingStatus.AUTO_APPROVED,
                "review_reasons": ["二次模型结果一致"],
                "model_name": model_name,
            }
        )

    return primary.model_copy(
        update={
            "status": ProcessingStatus.MANUAL_REVIEW,
            "review_reasons": primary.review_reasons + ["两次模型的语义结果不一致"],
            "model_name": model_name,
        }
    )
