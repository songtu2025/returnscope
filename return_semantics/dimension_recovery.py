from __future__ import annotations

from return_semantics.dimension_support import (
    _compile_one_dimension_decision,
    _DimensionDecisionContext,
)
from return_semantics.fact_extraction import _fact_assertion
from return_semantics.fact_mapping import (
    _contract_label_codes,
    _mapping_can_form_terminal,
)
from return_semantics.schemas import (
    AssertionCode,
    DimensionContract,
    DimensionDecision,
    FactMapping,
    ModelClassification,
    SemanticUnit,
)


def _referenced_facts_match_scope(
    decision: DimensionDecision,
    contract: DimensionContract,
    context: _DimensionDecisionContext,
    managed_codes: set[str],
) -> bool:
    facts_by_id = context.facts_by_id
    mappings_by_id = context.mappings_by_id
    all_fact_ids = [*decision.supporting_fact_ids, *decision.context_fact_ids]
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
            return False
    return True


def _matching_dimension_candidates(
    decision: DimensionDecision,
    contract: DimensionContract,
    context: _DimensionDecisionContext,
    managed_codes: set[str],
) -> list[tuple[str, str]]:
    facts_by_id = context.facts_by_id
    mappings_by_id = context.mappings_by_id
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
    return matching_candidates


def _recover_unique_dimension_candidate(
    decision: DimensionDecision,
    *,
    context: _DimensionDecisionContext,
) -> tuple[DimensionDecision, tuple, list[str], SemanticUnit] | None:
    """忽略误列为支持项的无标签证据，保留唯一明确维度候选。"""
    contracts = context.contracts
    facts_by_id = context.facts_by_id
    taxonomy = context.taxonomy
    all_fact_ids = [*decision.supporting_fact_ids, *decision.context_fact_ids]
    if any(fact_id not in facts_by_id for fact_id in all_fact_ids):
        return None
    contract = contracts.get(decision.parent_code)
    if contract is None:
        return None
    managed_codes = _contract_label_codes(taxonomy, contract)
    if not _referenced_facts_match_scope(decision, contract, context, managed_codes):
        return None
    matching_candidates = _matching_dimension_candidates(
        decision, contract, context, managed_codes
    )
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
        context=context,
    )
    return recovered, scope_key, referenced_ids, unit


def _compile_or_recover_dimension_decision(
    decision: DimensionDecision,
    *,
    context: _DimensionDecisionContext,
    recover_invalid_decisions: bool,
) -> tuple[tuple[DimensionDecision, tuple, list[str], SemanticUnit] | None, str | None]:
    try:
        scope_key, all_fact_ids, unit = _compile_one_dimension_decision(
            decision,
            context=context,
        )
    except ValueError as exc:
        if not recover_invalid_decisions:
            raise
        try:
            recovered = _recover_unique_dimension_candidate(
                decision,
                context=context,
            )
        except ValueError:
            recovered = None
        return recovered, str(exc)
    return (decision, scope_key, all_fact_ids, unit), None


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
