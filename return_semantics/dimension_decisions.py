from __future__ import annotations

from return_semantics.dimension_recovery import (
    _compile_or_recover_dimension_decision,
    _omitted_managed_fact_ids,
)
from return_semantics.dimension_recovery import (
    _recover_unique_dimension_candidate as _recover_unique_dimension_candidate,
)
from return_semantics.dimension_support import (
    _compile_one_dimension_decision as _compile_one_dimension_decision,
)
from return_semantics.dimension_support import (
    _decision_context,
    _DimensionDecisionContext,
)
from return_semantics.dimension_support import _decision_unit as _decision_unit
from return_semantics.fact_classification import (
    _append_suppressed_fallback_outcomes,
    _complete_fact_outcomes,
    _normalize_fact_mapping_outcomes,
    _unmapped_semantic,
)
from return_semantics.fact_extraction import _evidence
from return_semantics.fact_mapping import (
    FactDecisions,
    _contract_label_codes,
    _record_downgraded_facts,
)
from return_semantics.schemas import (
    DimensionContract,
    DimensionDecision,
    ExtractedFact,
    FactMapping,
    ModelClassification,
    SemanticDisposition,
    SemanticUnit,
    TaxonomyConfig,
)
from return_semantics.semantic_guardrails import apply_fallback_precedence


def _collect_dimension_decisions(
    decisions: FactDecisions,
    *,
    context: _DimensionDecisionContext,
    recover_invalid_decisions: bool,
) -> tuple[
    list[DimensionDecision],
    list[SemanticUnit],
    dict[tuple, set[str]],
    dict[str, str],
]:
    mappings_by_id = context.mappings_by_id
    seen_scopes: set[tuple] = set()
    referenced: dict[tuple, set[str]] = {}
    units: list[SemanticUnit] = []
    accepted: list[DimensionDecision] = []
    downgraded: dict[str, str] = {}
    for decision in decisions.decisions:
        compiled, recovery_reason = _compile_or_recover_dimension_decision(
            decision,
            context=context,
            recover_invalid_decisions=recover_invalid_decisions,
        )
        if compiled is None:
            _record_downgraded_facts(
                decision,
                mappings_by_id,
                recovery_reason or "维度裁决无法恢复",
                downgraded,
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
                downgraded,
            )
            continue
        seen_scopes.add(scope_key)
        referenced.setdefault(scope_key, set()).update(all_fact_ids)
        units.append(unit)
        accepted.append(accepted_decision)
    return accepted, units, referenced, downgraded


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


def _project_dimension_primary_codes(
    result: ModelClassification,
    accepted_decisions: list[DimensionDecision],
) -> None:
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


def _finalize_dimension_decisions(
    result: ModelClassification,
    accepted_decisions: list[DimensionDecision],
    decision_units: list[SemanticUnit],
    managed_by_label: dict[str, DimensionContract],
    *,
    context: _DimensionDecisionContext,
) -> None:
    taxonomy = context.taxonomy
    comment = context.comment
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
    _project_dimension_primary_codes(result, accepted_decisions)
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
    context = _decision_context(classification, contracts, taxonomy, comment)
    managed_by_label = {
        code: contract
        for contract in contracts.values()
        for code in _contract_label_codes(taxonomy, contract)
    }
    accepted, units, referenced, downgraded = _collect_dimension_decisions(
        decisions,
        context=context,
        recover_invalid_decisions=recover_invalid_decisions,
    )
    omitted = _omitted_managed_fact_ids(
        classification,
        context.mappings_by_id,
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
        _downgrade_invalid_decisions(result, downgraded, context.facts_by_id, comment)
    _finalize_dimension_decisions(
        result,
        accepted,
        units,
        managed_by_label,
        context=context,
    )
    return result


# 保留已有辅助入口的模块归属，避免移动实现影响反射和序列化。
for _entry in (
    _DimensionDecisionContext,
    _decision_unit,
    _compile_one_dimension_decision,
    _recover_unique_dimension_candidate,
    _compile_or_recover_dimension_decision,
    _omitted_managed_fact_ids,
):
    _entry.__module__ = __name__
del _entry
