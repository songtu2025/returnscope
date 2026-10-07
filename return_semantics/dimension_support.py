from __future__ import annotations

from dataclasses import dataclass

from return_semantics.fact_extraction import (
    _decision_evidence,
    _decision_evidence_source,
    _fact_assertion,
    _validate_decision_scope,
)
from return_semantics.fact_mapping import (
    _mapping_can_form_terminal,
    _validate_context_dimension,
)
from return_semantics.schemas import (
    AssertionCode,
    DimensionContract,
    DimensionDecision,
    ExtractedFact,
    FactMapping,
    FactRole,
    ModelClassification,
    SemanticUnit,
    TaxonomyConfig,
)


@dataclass(frozen=True, kw_only=True)
class _DimensionDecisionContext:
    contracts: dict[str, DimensionContract]
    facts_by_id: dict[str, ExtractedFact]
    mappings_by_id: dict[str, FactMapping]
    taxonomy: TaxonomyConfig
    comment: str


def _decision_context(
    classification: ModelClassification,
    contracts: dict[str, DimensionContract],
    taxonomy: TaxonomyConfig,
    comment: str,
) -> _DimensionDecisionContext:
    return _DimensionDecisionContext(
        contracts=contracts,
        facts_by_id={fact.fact_id: fact for fact in classification.extracted_facts},
        mappings_by_id={
            mapping.fact_id: mapping for mapping in classification.fact_mappings
        },
        taxonomy=taxonomy,
        comment=comment,
    )


def _validate_verdict_facts(
    verdict_facts: list[ExtractedFact],
    mappings_by_id: dict[str, FactMapping],
) -> None:
    if any(
        not _mapping_can_form_terminal(fact, mappings_by_id[fact.fact_id])
        or _fact_assertion(fact) != AssertionCode.AFFIRMED
        for fact in verdict_facts
    ):
        raise ValueError("未确认事实不能支持维度结论")
    sentiments = {fact.sentiment for fact in verdict_facts}
    if len(sentiments) != 1:
        raise ValueError("同一维度结论的支持事实方向必须一致")
    subjects = {fact.subject for fact in verdict_facts}
    if len(subjects) != 1:
        raise ValueError("同一维度结论的支持事实主体必须一致")


def _validated_verdict_facts(
    decision: DimensionDecision,
    facts_by_id: dict[str, ExtractedFact],
    mappings_by_id: dict[str, FactMapping],
) -> tuple[list[ExtractedFact], ExtractedFact]:
    supporting = [facts_by_id[fact_id] for fact_id in decision.supporting_fact_ids]
    verdict_facts = [
        fact
        for fact in supporting
        if decision.verdict_label_code in mappings_by_id[fact.fact_id].label_codes
    ]
    if len(verdict_facts) != len(supporting):
        raise ValueError("支持事实必须全部候选映射到维度结论标签")
    if any(fact.fact_role == FactRole.CONTEXT for fact in verdict_facts):
        raise ValueError("上下文事实不能直接支持维度结论")
    conclusion_facts = [
        fact
        for fact in verdict_facts
        if fact.fact_role == FactRole.CONCLUSION
        or mappings_by_id[fact.fact_id].adjudication_action in {"ACCEPT", "REPLACE"}
    ]
    if not conclusion_facts:
        raise ValueError("维度结论至少需要一个明确结论或经裁决晋升的事实")
    _validate_verdict_facts(verdict_facts, mappings_by_id)
    anchor = conclusion_facts[0]
    return verdict_facts, anchor


def _decision_unit(
    decision: DimensionDecision,
    contract: DimensionContract,
    facts_by_id: dict[str, ExtractedFact],
    mappings_by_id: dict[str, FactMapping],
    comment: str,
) -> SemanticUnit:
    verdict_facts, anchor = _validated_verdict_facts(
        decision, facts_by_id, mappings_by_id
    )
    return SemanticUnit(
        subject=anchor.subject,
        label_code=decision.verdict_label_code,
        opinion="；".join(dict.fromkeys(fact.opinion for fact in verdict_facts)),
        sentiment=anchor.sentiment,
        assertion=AssertionCode.AFFIRMED,
        part=decision.scope.part,
        evidence=_decision_evidence(verdict_facts, comment),
        implicit=False,
        fact_id=anchor.fact_id,
        fact_ids=[fact.fact_id for fact in verdict_facts],
        actor_ref=decision.scope.experiencer_ref,
        source_ref=decision.scope.source_ref,
        experiencer_ref=decision.scope.experiencer_ref,
        product_ref=decision.scope.product_ref,
        variant_ref=decision.scope.variant_ref,
        event_ref=decision.scope.event_ref,
        reference_basis=decision.scope.reference_basis,
        statement_type=anchor.statement_type,
        operation=decision.scope.operation,
        condition=decision.scope.condition,
        evidence_source=_decision_evidence_source(verdict_facts),
        fact_role=anchor.fact_role,
        causal_attribution=anchor.causal_attribution,
        causal_attribution_reason=anchor.causal_attribution_reason,
        decision_reason=decision.reason,
        context_fact_ids=decision.context_fact_ids,
    )


def _compile_one_dimension_decision(
    decision: DimensionDecision,
    *,
    context: _DimensionDecisionContext,
) -> tuple[tuple, list[str], SemanticUnit]:
    contracts = context.contracts
    facts_by_id = context.facts_by_id
    mappings_by_id = context.mappings_by_id
    taxonomy = context.taxonomy
    comment = context.comment
    contract = contracts.get(decision.parent_code)
    if contract is None:
        raise ValueError(f"维度结论引用了未配置父级: {decision.parent_code}")
    if decision.verdict_label_code not in contract.verdict_label_codes:
        raise ValueError(f"维度结论标签不在契约中: {decision.verdict_label_code}")
    all_fact_ids = [*decision.supporting_fact_ids, *decision.context_fact_ids]
    if len(all_fact_ids) != len(set(all_fact_ids)):
        raise ValueError("维度结论的支持与上下文事实不能重复")
    unknown_fact_ids = sorted(set(all_fact_ids) - facts_by_id.keys())
    if unknown_fact_ids:
        raise ValueError(f"维度结论引用了未知事实: {unknown_fact_ids}")
    supporting = [facts_by_id[fact_id] for fact_id in decision.supporting_fact_ids]
    context_facts = [facts_by_id[fact_id] for fact_id in decision.context_fact_ids]
    _validate_context_dimension(context_facts, contract, taxonomy, mappings_by_id)
    scope_key = (
        decision.parent_code,
        *_validate_decision_scope(
            decision,
            contract,
            [*supporting, *context_facts],
        ),
    )
    unit = _decision_unit(
        decision,
        contract,
        facts_by_id,
        mappings_by_id,
        comment,
    )
    return scope_key, all_fact_ids, unit
