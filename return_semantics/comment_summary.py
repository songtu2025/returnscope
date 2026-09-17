from __future__ import annotations

from collections.abc import Iterable
from itertools import combinations

from return_semantics.schemas import (
    CommentSummary,
    CommentSummaryStatus,
    LabelDefinition,
    SemanticRelation,
    SemanticRelationType,
    SemanticUnit,
    SentimentCode,
    TaxonomyConfig,
)


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _semantic_topic(
    left: SemanticUnit,
    right: SemanticUnit,
    taxonomy: TaxonomyConfig,
    labels: dict[str, LabelDefinition],
) -> str | None:
    if left.label_code == right.label_code:
        return left.label_code
    for codes in taxonomy.validation_rules.conflicting_label_sets:
        if left.label_code in codes and right.label_code in codes:
            return "|".join(sorted(codes))
    for contract in taxonomy.validation_rules.dimension_contracts:
        verdicts = set(contract.verdict_label_codes)
        if left.label_code in verdicts and right.label_code in verdicts:
            return contract.parent_code
    return None


def _is_explicit_variant(variant_ref: str) -> bool:
    return variant_ref != "UNSPECIFIED"


def _relation_for_pair(
    left: SemanticUnit,
    right: SemanticUnit,
    left_ref: str,
    right_ref: str,
    taxonomy: TaxonomyConfig,
    labels: dict[str, LabelDefinition],
) -> SemanticRelation | None:
    if _semantic_topic(left, right, taxonomy, labels) is None:
        return None
    relation_type: SemanticRelationType | None = None
    reason = ""
    if left.experiencer_ref != right.experiencer_ref:
        relation_type = SemanticRelationType.MULTI_ACTOR
        reason = "同一主题来自不同使用者"
    elif left.product_ref != right.product_ref:
        relation_type = SemanticRelationType.MULTI_PRODUCT
        reason = "同一主题针对不同商品"
    elif left.variant_ref != right.variant_ref:
        if not (
            _is_explicit_variant(left.variant_ref)
            and _is_explicit_variant(right.variant_ref)
        ):
            return None
        relation_type = SemanticRelationType.MULTI_PRODUCT
        reason = "同一主题针对不同规格"
    elif left.sentiment != right.sentiment:
        events_differ = left.event_ref != right.event_ref
        operations_differ = (
            left.operation.strip().casefold() != right.operation.strip().casefold()
        )
        conditions_differ = (
            left.condition.strip().casefold() != right.condition.strip().casefold()
        )
        references_differ = left.reference_basis != right.reference_basis
        if (
            events_differ
            or operations_differ
            or left.part != right.part
            or conditions_differ
            or references_differ
        ):
            relation_type = SemanticRelationType.MIXED
            reason = "同一主题在不同事件、操作、部位或条件下表现不同"
        else:
            relation_type = SemanticRelationType.CONFLICT
            reason = "同一语义范围内存在相反方向"
    if relation_type is None:
        return None
    return SemanticRelation(
        relation_type=relation_type,
        fact_ids=[left_ref, right_ref],
        label_codes=_unique([left.label_code, right.label_code]),
        reason=reason,
    )


def compile_comment_semantics(
    units: list[SemanticUnit],
    taxonomy: TaxonomyConfig,
    labels: dict[str, LabelDefinition],
) -> tuple[list[SemanticRelation], CommentSummary]:
    """把已确认原子事实编译为评论级关系和摘要。"""
    indexed_units = list(enumerate(units, start=1))
    relations: list[SemanticRelation] = []
    seen_relations: set[str] = set()
    for (left_index, left), (right_index, right) in combinations(indexed_units, 2):
        relation = _relation_for_pair(
            left,
            right,
            left.fact_id or f"UNIT:{left_index}",
            right.fact_id or f"UNIT:{right_index}",
            taxonomy,
            labels,
        )
        if relation is None:
            continue
        signature = relation.model_dump_json()
        if signature not in seen_relations:
            relations.append(relation)
            seen_relations.add(signature)

    positive_codes = _unique(
        unit.label_code for unit in units if unit.sentiment == SentimentCode.POSITIVE
    )
    negative_codes = _unique(
        unit.label_code for unit in units if unit.sentiment == SentimentCode.NEGATIVE
    )
    if any(
        relation.relation_type == SemanticRelationType.CONFLICT
        for relation in relations
    ):
        status = CommentSummaryStatus.CONFLICT
    elif positive_codes and negative_codes:
        status = CommentSummaryStatus.MIXED
    elif negative_codes:
        status = CommentSummaryStatus.NEGATIVE
    elif positive_codes:
        status = CommentSummaryStatus.POSITIVE
    else:
        status = CommentSummaryStatus.NO_CONFIRMED
    summary = CommentSummary(
        status=status,
        fact_ids=_unique(
            fact_id
            for unit in units
            for fact_id in (unit.fact_ids or ([unit.fact_id] if unit.fact_id else []))
        ),
        positive_label_codes=positive_codes,
        negative_label_codes=negative_codes,
    )
    return relations, summary
