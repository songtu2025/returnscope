from __future__ import annotations

from return_semantics.fact_classification import (
    _append_suppressed_fallback_outcomes,
    _complete_fact_outcomes,
    _normalize_fact_mapping_outcomes,
    _unmapped_semantic,
)
from return_semantics.fact_extraction import (
    _decision_evidence,
    _decision_evidence_source,
    _evidence,
    _fact_assertion,
    _validate_decision_scope,
)
from return_semantics.fact_mapping import (
    FactDecisions,
    _contract_label_codes,
    _mapping_can_form_terminal,
    _record_downgraded_facts,
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
    SemanticDisposition,
    SemanticUnit,
    TaxonomyConfig,
)
from return_semantics.semantic_guardrails import apply_fallback_precedence


def _decision_unit(
    decision: DimensionDecision,
    contract: DimensionContract,
    facts_by_id: dict[str, ExtractedFact],
    mappings_by_id: dict[str, FactMapping],
    comment: str,
) -> SemanticUnit:
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
    anchor = conclusion_facts[0]
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
    contracts: dict[str, DimensionContract],
    facts_by_id: dict[str, ExtractedFact],
    mappings_by_id: dict[str, FactMapping],
    taxonomy: TaxonomyConfig,
    comment: str,
) -> tuple[tuple, list[str], SemanticUnit]:
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


def _recover_unique_dimension_candidate(
    decision: DimensionDecision,
    *,
    contracts: dict[str, DimensionContract],
    facts_by_id: dict[str, ExtractedFact],
    mappings_by_id: dict[str, FactMapping],
    taxonomy: TaxonomyConfig,
    comment: str,
) -> tuple[DimensionDecision, tuple, list[str], SemanticUnit] | None:
    """忽略误列为支持项的无标签证据，保留唯一明确维度候选。"""
    all_fact_ids = [*decision.supporting_fact_ids, *decision.context_fact_ids]
    if any(fact_id not in facts_by_id for fact_id in all_fact_ids):
        return None
    contract = contracts.get(decision.parent_code)
    if contract is None:
        return None
    managed_codes = _contract_label_codes(taxonomy, contract)
    for fact_id in all_fact_ids:
        fact = facts_by_id[fact_id]
        mapping = mappings_by_id[fact_id]
        if (
            mapping.label_codes
            and mapping.label_codes[0] in managed_codes
            and any(
                getattr(fact, field_name) != getattr(decision.scope, field_name)
                for field_name in contract.scope_fields
            )
        ):
            return None
    matching_candidates = []
    for fact_id, fact in facts_by_id.items():
        mapping = mappings_by_id[fact_id]
        if (
            mapping.label_codes
            and mapping.label_codes[0] in managed_codes
            and _mapping_can_form_terminal(fact, mapping)
            and _fact_assertion(fact) == AssertionCode.AFFIRMED
            and all(
                getattr(fact, field_name) == getattr(decision.scope, field_name)
                for field_name in contract.scope_fields
            )
        ):
            matching_candidates.append((fact_id, mapping.label_codes[0]))
    mapped_codes = {code for _, code in matching_candidates}
    if len(mapped_codes) != 1:
        return None
    verdict_code = mapped_codes.pop()
    supporting_ids = [
        fact_id for fact_id, code in matching_candidates if code == verdict_code
    ]
    recovered = decision.model_copy(
        update={
            "verdict_label_code": verdict_code,
            "supporting_fact_ids": supporting_ids,
            "context_fact_ids": [],
        }
    )
    scope_key, referenced_ids, unit = _compile_one_dimension_decision(
        recovered,
        contracts=contracts,
        facts_by_id=facts_by_id,
        mappings_by_id=mappings_by_id,
        taxonomy=taxonomy,
        comment=comment,
    )
    return recovered, scope_key, referenced_ids, unit


def _compile_or_recover_dimension_decision(
    decision: DimensionDecision,
    *,
    contracts: dict[str, DimensionContract],
    facts_by_id: dict[str, ExtractedFact],
    mappings_by_id: dict[str, FactMapping],
    taxonomy: TaxonomyConfig,
    comment: str,
    recover_invalid_decisions: bool,
) -> tuple[tuple[DimensionDecision, tuple, list[str], SemanticUnit] | None, str | None]:
    try:
        scope_key, all_fact_ids, unit = _compile_one_dimension_decision(
            decision,
            contracts=contracts,
            facts_by_id=facts_by_id,
            mappings_by_id=mappings_by_id,
            taxonomy=taxonomy,
            comment=comment,
        )
    except ValueError as exc:
        if not recover_invalid_decisions:
            raise
        try:
            recovered = _recover_unique_dimension_candidate(
                decision,
                contracts=contracts,
                facts_by_id=facts_by_id,
                mappings_by_id=mappings_by_id,
                taxonomy=taxonomy,
                comment=comment,
            )
        except ValueError:
            recovered = None
        return recovered, str(exc)
    return (decision, scope_key, all_fact_ids, unit), None


def _collect_dimension_decisions(
    decisions: FactDecisions,
    *,
    contracts: dict[str, DimensionContract],
    facts_by_id: dict[str, ExtractedFact],
    mappings_by_id: dict[str, FactMapping],
    taxonomy: TaxonomyConfig,
    comment: str,
    recover_invalid_decisions: bool,
) -> tuple[
    list[DimensionDecision],
    list[SemanticUnit],
    dict[tuple, set[str]],
    dict[str, str],
]:
    seen_scopes: set[tuple] = set()
    referenced_by_scope: dict[tuple, set[str]] = {}
    decision_units: list[SemanticUnit] = []
    accepted_decisions: list[DimensionDecision] = []
    downgraded_fact_reasons: dict[str, str] = {}
    for decision in decisions.decisions:
        compiled, recovery_reason = _compile_or_recover_dimension_decision(
            decision,
            contracts=contracts,
            facts_by_id=facts_by_id,
            mappings_by_id=mappings_by_id,
            taxonomy=taxonomy,
            comment=comment,
            recover_invalid_decisions=recover_invalid_decisions,
        )
        if compiled is None:
            _record_downgraded_facts(
                decision,
                mappings_by_id,
                recovery_reason or "维度裁决无法恢复",
                downgraded_fact_reasons,
            )
            continue
        accepted_decision, scope_key, all_fact_ids, unit = compiled
        if scope_key in seen_scopes:
            if not recover_invalid_decisions:
                raise ValueError("同一维度作用域只能生成一个结论")
            _record_downgraded_facts(
                decision,
                mappings_by_id,
                recovery_reason or "同一维度作用域存在重复结论",
                downgraded_fact_reasons,
            )
            continue
        seen_scopes.add(scope_key)
        referenced_by_scope.setdefault(scope_key, set()).update(all_fact_ids)
        decision_units.append(unit)
        accepted_decisions.append(accepted_decision)
    return (
        accepted_decisions,
        decision_units,
        referenced_by_scope,
        downgraded_fact_reasons,
    )


def _omitted_managed_fact_ids(
    classification: ModelClassification,
    mappings_by_id: dict[str, FactMapping],
    managed_by_label: dict[str, DimensionContract],
    referenced_by_scope: dict[tuple, set[str]],
) -> list[str]:
    omitted_fact_ids = []
    for fact in classification.extracted_facts:
        mapping = mappings_by_id[fact.fact_id]
        if not mapping.label_codes:
            continue
        label_code = mapping.label_codes[0]
        contract = managed_by_label.get(label_code)
        if contract is None:
            continue
        if (
            not _mapping_can_form_terminal(fact, mapping)
            or _fact_assertion(fact) != AssertionCode.AFFIRMED
        ):
            continue
        scope_key = (
            contract.parent_code,
            *(getattr(fact, field) for field in contract.scope_fields),
        )
        if fact.fact_id not in referenced_by_scope.get(scope_key, set()):
            omitted_fact_ids.append(fact.fact_id)
    return omitted_fact_ids


def _downgrade_invalid_decisions(
    result: ModelClassification,
    downgraded_fact_reasons: dict[str, str],
    facts_by_id: dict[str, ExtractedFact],
    comment: str,
) -> None:
    result.fact_mappings = [
        FactMapping.model_validate(
            {
                **mapping.model_dump(mode="json"),
                "label_codes": [],
                "candidate_label_codes": list(
                    dict.fromkeys(
                        [*mapping.candidate_label_codes, *mapping.label_codes]
                    )
                )[:1],
                "disposition": SemanticDisposition.MAPPING_UNCERTAIN,
                "reason": downgraded_fact_reasons[mapping.fact_id],
            }
        )
        if mapping.fact_id in downgraded_fact_reasons
        else mapping
        for mapping in result.fact_mappings
    ]
    existing_unknown_ids = {
        item.fact_id for item in result.unknown_semantics if item.fact_id is not None
    }
    for fact_id, reason in downgraded_fact_reasons.items():
        if fact_id not in existing_unknown_ids:
            fact = facts_by_id[fact_id]
            result.unknown_semantics.append(
                _unmapped_semantic(
                    fact,
                    _evidence(fact, comment),
                    reason,
                    SemanticDisposition.MAPPING_UNCERTAIN,
                )
            )


def _finalize_dimension_decisions(
    result: ModelClassification,
    accepted_decisions: list[DimensionDecision],
    decision_units: list[SemanticUnit],
    managed_by_label: dict[str, DimensionContract],
    taxonomy: TaxonomyConfig,
    comment: str,
) -> None:
    explained_context_fact_ids = {
        fact_id
        for decision in accepted_decisions
        for fact_id in decision.context_fact_ids
    }
    result.semantic_units = [
        unit
        for unit in result.semantic_units
        if unit.label_code not in managed_by_label
    ]
    result.semantic_units.extend(decision_units)
    suppressed_fallback_ids = apply_fallback_precedence(
        result.semantic_units,
        set(taxonomy.validation_rules.fallback_label_codes),
    )
    _append_suppressed_fallback_outcomes(result, suppressed_fallback_ids, comment)
    _complete_fact_outcomes(
        result,
        comment=comment,
        ignored_reasons={
            fact_id: "已由维度裁决作为上下文解释"
            for fact_id in explained_context_fact_ids
        },
    )
    _normalize_fact_mapping_outcomes(result)
    surviving_codes = {unit.label_code for unit in result.semantic_units}
    primary_codes = [
        code for code in result.primary_label_codes if code in surviving_codes
    ]
    primary_fact_ids = {
        fact.fact_id for fact in result.extracted_facts if fact.is_primary_reason
    }
    for decision in accepted_decisions:
        if primary_fact_ids.intersection(decision.supporting_fact_ids):
            primary_codes.append(decision.verdict_label_code)
    result.primary_label_codes = list(dict.fromkeys(primary_codes))
    result.needs_review = bool(
        result.review_reasons
        or any(
            item.disposition
            in {
                SemanticDisposition.TAXONOMY_GAP,
                SemanticDisposition.MAPPING_UNCERTAIN,
            }
            for item in result.unknown_semantics
        )
    )


def compile_dimension_decisions(
    classification: ModelClassification,
    decisions: FactDecisions,
    *,
    comment: str,
    taxonomy: TaxonomyConfig,
    recover_invalid_decisions: bool = False,
) -> ModelClassification:
    """校验维度裁决，并只把裁决结果编译为受管维度的终态语义。"""
    contracts = {
        contract.parent_code: contract
        for contract in taxonomy.validation_rules.dimension_contracts
    }
    if not contracts:
        return classification
    facts_by_id = {fact.fact_id: fact for fact in classification.extracted_facts}
    mappings_by_id = {
        mapping.fact_id: mapping for mapping in classification.fact_mappings
    }
    managed_by_label = {
        code: contract
        for contract in contracts.values()
        for code in _contract_label_codes(taxonomy, contract)
    }
    accepted, units, referenced, downgraded = _collect_dimension_decisions(
        decisions,
        contracts=contracts,
        facts_by_id=facts_by_id,
        mappings_by_id=mappings_by_id,
        taxonomy=taxonomy,
        comment=comment,
        recover_invalid_decisions=recover_invalid_decisions,
    )
    omitted = _omitted_managed_fact_ids(
        classification,
        mappings_by_id,
        managed_by_label,
        referenced,
    )
    if omitted and not recover_invalid_decisions:
        raise ValueError(f"受管维度候选事实未进入同作用域裁决: {sorted(omitted)}")
    for fact_id in omitted:
        downgraded.setdefault(fact_id, "受管维度候选事实未进入同作用域裁决")

    result = classification.model_copy(deep=True)
    result.dimension_decisions = accepted
    if downgraded:
        _downgrade_invalid_decisions(result, downgraded, facts_by_id, comment)
    _finalize_dimension_decisions(
        result,
        accepted,
        units,
        managed_by_label,
        taxonomy,
        comment,
    )
    return result
