from __future__ import annotations

from return_semantics.fact_mapping_models import FactDecisions
from return_semantics.schemas import (
    DimensionContract,
    DimensionDecision,
    ExtractedFact,
    FactMapping,
    TaxonomyConfig,
)
from return_semantics.taxonomy_hierarchy import label_path, label_path_codes


def _contract_label_codes(
    taxonomy: TaxonomyConfig,
    contract: DimensionContract,
) -> set[str]:
    return {
        label.code
        for label in taxonomy.labels
        if contract.parent_code in label_path_codes(taxonomy, label.code)[:-1]
    }


def _decision_payload(
    facts: list[ExtractedFact],
    mappings: list[FactMapping],
    taxonomy: TaxonomyConfig,
) -> dict:
    labels = {label.code: label for label in taxonomy.labels}
    return {
        "facts": [fact.model_dump(mode="json") for fact in facts],
        "mappings": [mapping.model_dump(mode="json") for mapping in mappings],
        "contracts": [
            {
                **contract.model_dump(mode="json"),
                "verdict_labels": [
                    {
                        **labels[code].model_dump(mode="json"),
                        "path": label_path(taxonomy, code),
                    }
                    for code in contract.verdict_label_codes
                ],
            }
            for contract in taxonomy.validation_rules.dimension_contracts
        ],
        "instructions": taxonomy.instructions,
        "schema": FactDecisions.model_json_schema(),
    }


def _contract_branch_code(
    taxonomy: TaxonomyConfig,
    parent_code: str,
) -> str:
    parents = {category.code: category.parent_code for category in taxonomy.categories}
    current = parent_code
    while parents.get(current) is not None:
        current = str(parents[current])
    return current


def _validate_context_dimension(
    context_facts: list[ExtractedFact],
    contract: DimensionContract,
    taxonomy: TaxonomyConfig,
    mappings_by_id: dict[str, FactMapping],
) -> None:
    managed_codes = _contract_label_codes(taxonomy, contract)
    branch_code = _contract_branch_code(taxonomy, contract.parent_code)
    for fact in context_facts:
        mapping = mappings_by_id[fact.fact_id]
        candidate_codes = mapping.label_codes or mapping.candidate_label_codes
        if candidate_codes and any(
            code not in managed_codes for code in candidate_codes
        ):
            raise ValueError(f"维度上下文候选标签不属于配置父级: {fact.fact_id}")
        if not candidate_codes and branch_code not in fact.candidate_branch_codes:
            raise ValueError(f"维度上下文事实不属于配置父级分支: {fact.fact_id}")


def _record_downgraded_facts(
    decision: DimensionDecision,
    mappings_by_id: dict[str, FactMapping],
    reason: str,
    downgraded_fact_reasons: dict[str, str],
) -> None:
    for fact_id in decision.supporting_fact_ids:
        mapping = mappings_by_id.get(fact_id)
        if mapping is not None and mapping.label_codes:
            downgraded_fact_reasons[fact_id] = reason
