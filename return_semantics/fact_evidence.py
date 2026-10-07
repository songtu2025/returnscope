from __future__ import annotations

import re

from return_semantics.schemas import (
    AssertionCode,
    DimensionContract,
    DimensionDecision,
    DimensionScope,
    EvidenceSource,
    ExtractedFact,
    TaxonomyConfig,
)

_SCOPE_DEFAULTS = DimensionScope()


_UNCERTAIN_STATEMENT_TYPES = {
    "PREDICTION",
    "HYPOTHESIS",
    "NOT_TESTED",
    "ADVICE",
    "PRODUCT_CLAIM",
    "APPEARANCE_INFERENCE",
}


def _validate_one_fact(
    fact: ExtractedFact, comment: str, taxonomy: TaxonomyConfig
) -> None:
    _validate_reference(fact.actor_ref, {"REVIEWER"}, {"OTHER"})
    _validate_reference(fact.source_ref, {"REVIEWER"}, {"OTHER"})
    _validate_reference(fact.experiencer_ref, {"REVIEWER"}, {"OTHER"})
    if fact.actor_ref != fact.experiencer_ref:
        raise ValueError("actor_ref必须与experiencer_ref一致")
    _validate_reference(fact.product_ref, {"CURRENT"}, {"CURRENT", "OTHER"})
    if not fact.variant_ref.strip():
        raise ValueError(f"事实规格引用不能为空: {fact.fact_id}")
    if fact.part not in taxonomy.allowed_parts:
        raise ValueError(f"事实部位不适用于当前品类: {fact.fact_id}: {fact.part}")
    if any((span.text not in comment for span in fact.evidence_spans)):
        raise ValueError(f"事实证据不在原评论中: {fact.fact_id}")


def _restore_evidence_spans(
    facts: list[ExtractedFact], comment: str
) -> list[ExtractedFact]:
    """仅在忽略大小写后唯一匹配时，还原证据在原文中的真实写法。"""
    restored = []
    for fact in facts:
        spans = []
        for span in fact.evidence_spans:
            if span.text in comment:
                spans.append(span)
                continue
            matches = list(re.finditer(re.escape(span.text), comment, re.IGNORECASE))
            spans.append(
                span.model_copy(update={"text": matches[0].group(0)})
                if len(matches) == 1
                else span
            )
        restored.append(fact.model_copy(update={"evidence_spans": spans}))
    return restored


def _validate_facts(
    facts: list[ExtractedFact], comment: str, taxonomy: TaxonomyConfig
) -> None:
    identifiers = [fact.fact_id for fact in facts]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("事实编号重复")
    product_refs = {fact.product_ref for fact in facts}
    if "CURRENT" in product_refs and any(
        (ref.startswith("CURRENT:") for ref in product_refs)
    ):
        raise ValueError("单一商品CURRENT不能与多件商品CURRENT编号混用")
    for fact in facts:
        _validate_one_fact(fact, comment, taxonomy)


def _validate_reference(
    reference: str, standalone: set[str], prefixes: set[str]
) -> None:
    if reference in standalone:
        return
    prefix, separator, identifier = reference.partition(":")
    if (
        not separator
        or prefix not in prefixes
        or not identifier.isascii()
        or not identifier.isdecimal()
        or identifier.startswith("0")
    ):
        raise ValueError(f"事实对象引用不符合协议，须使用规范正整数编号: {reference}")


def _evidence(fact: ExtractedFact, comment: str) -> str:
    starts = [comment.index(span.text) for span in fact.evidence_spans]
    ends = [
        start + len(span.text)
        for start, span in zip(starts, fact.evidence_spans, strict=True)
    ]
    return comment[min(starts) : max(ends)]


def _evidence_source(fact: ExtractedFact) -> EvidenceSource:
    sources = {span.source for span in fact.evidence_spans}
    if len(sources) == 1:
        return sources.pop()
    if sources == {EvidenceSource.TITLE, EvidenceSource.BODY}:
        return EvidenceSource.TITLE_AND_BODY
    return EvidenceSource.COMMENT


def _fact_context(fact: ExtractedFact) -> dict:
    return {
        "fact_id": fact.fact_id,
        "actor_ref": fact.actor_ref,
        "source_ref": fact.source_ref,
        "experiencer_ref": fact.experiencer_ref,
        "product_ref": fact.product_ref,
        "variant_ref": fact.variant_ref,
        "event_ref": fact.event_ref,
        "reference_basis": fact.reference_basis,
        "statement_type": fact.statement_type,
        "operation": fact.operation,
        "condition": fact.condition,
        "evidence_source": _evidence_source(fact),
        "fact_role": fact.fact_role,
        "causal_attribution": fact.causal_attribution,
        "causal_attribution_reason": fact.causal_attribution_reason,
    }


def _validate_decision_scope(
    decision: DimensionDecision,
    contract: DimensionContract,
    scoped_facts: list[ExtractedFact],
) -> tuple:
    scope_fields = set(contract.scope_fields)
    for field_name in DimensionScope.model_fields:
        value = getattr(decision.scope, field_name)
        if field_name not in scope_fields and value != getattr(
            _SCOPE_DEFAULTS, field_name
        ):
            raise ValueError(f"未纳入契约的作用域字段必须留空: {field_name}")
    for fact in scoped_facts:
        for field_name in contract.scope_fields:
            if getattr(fact, field_name) != getattr(decision.scope, field_name):
                raise ValueError(
                    f"维度结论作用域与事实不一致: {fact.fact_id}: {field_name}"
                )
    return tuple(getattr(decision.scope, field) for field in contract.scope_fields)


def _decision_evidence(facts: list[ExtractedFact], comment: str) -> str:
    evidence = [_evidence(fact, comment) for fact in facts]
    starts = [comment.index(value) for value in evidence]
    ends = [start + len(value) for start, value in zip(starts, evidence, strict=True)]
    return comment[min(starts) : max(ends)]


def _decision_evidence_source(facts: list[ExtractedFact]) -> EvidenceSource:
    sources = {_evidence_source(fact) for fact in facts}
    if len(sources) == 1:
        return sources.pop()
    if sources <= {
        EvidenceSource.TITLE,
        EvidenceSource.BODY,
        EvidenceSource.TITLE_AND_BODY,
    }:
        return EvidenceSource.TITLE_AND_BODY
    return EvidenceSource.COMMENT


def _fact_assertion(fact: ExtractedFact) -> AssertionCode:
    if fact.statement_type in _UNCERTAIN_STATEMENT_TYPES:
        return AssertionCode.UNCERTAIN
    if fact.statement_type == "NEGATED":
        return AssertionCode.NEGATED
    return fact.assertion
