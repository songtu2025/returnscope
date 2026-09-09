from __future__ import annotations

from return_semantics.schemas import (
    ProcessingStatus,
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


def _signature(result: ValidatedClassification) -> tuple[object, ...]:
    units = sorted(
        (
            unit.label_code,
            unit.sentiment.value,
            unit.part,
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
        _fact_signature(result),
    )


def _fact_signature(result: ValidatedClassification) -> tuple:
    """事实编号由各次抽取生成，不用于判断两次识别是否一致。"""
    mappings = {item.fact_id: tuple(item.label_codes) for item in result.fact_mappings}
    events: dict[str, list[tuple]] = {}
    for fact in result.extracted_facts:
        events.setdefault(fact.event_ref, []).append(
            (
                fact.actor_ref,
                fact.product_ref,
                fact.subject.value,
                fact.statement_type,
                fact.sentiment.value,
                fact.part,
                fact.condition,
                fact.is_primary_reason,
                tuple(sorted(span.text for span in fact.evidence_spans)),
                mappings.get(fact.fact_id, ()),
            )
        )
    return tuple(sorted(tuple(sorted(group)) for group in events.values()))


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
    if (primary.extracted_facts or secondary.extracted_facts) and any(
        blocker in reason
        for result in (primary, secondary)
        for reason in result.review_reasons
        for blocker in MANUAL_ONLY_REASONS
    ):
        return primary.model_copy(
            update={
                "status": ProcessingStatus.MANUAL_REVIEW,
                "review_reasons": list(
                    dict.fromkeys(primary.review_reasons + secondary.review_reasons)
                ),
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
