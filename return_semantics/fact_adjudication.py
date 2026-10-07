from __future__ import annotations

from dataclasses import dataclass

from return_semantics.fact_mapping import (
    EvidenceLabelAdjudication,
    EvidenceLabelAdjudications,
    _adjudicated_mapping,
    _can_be_adjudicated,
    _normalized_adjudication,
)
from return_semantics.schemas import (
    ExtractedFact,
    FactMapping,
    LabelDefinition,
    ModelClassification,
    TaxonomyConfig,
)


@dataclass(frozen=True, kw_only=True)
class _FactAdjudicationContext:
    facts_by_id: dict[str, ExtractedFact]
    labels_by_code: dict[str, LabelDefinition]
    allowed: dict[str, list[str]]
    fallback_codes: set[str]
    recover_invalid_actions: bool


def _adjudications_by_fact(
    classification: ModelClassification,
    adjudications: EvidenceLabelAdjudications,
    recover_invalid_actions: bool,
) -> dict[str, EvidenceLabelAdjudication]:
    candidate_ids = {
        fact.fact_id
        for fact in classification.extracted_facts
        if _can_be_adjudicated(fact) and fact.product_ref.startswith("CURRENT")
    }
    grouped_decisions: dict[str, list[EvidenceLabelAdjudication]] = {}
    for item in adjudications.adjudications:
        grouped_decisions.setdefault(item.fact_id, []).append(item)
    valid_coverage = set(grouped_decisions) == candidate_ids and all(
        len(items) == 1 for items in grouped_decisions.values()
    )
    if not valid_coverage and not recover_invalid_actions:
        raise ValueError("每个可形成终态的具体事实必须且只能有一条最终裁决")
    decisions = {
        fact_id: (
            grouped_decisions[fact_id][0]
            if len(grouped_decisions.get(fact_id, [])) == 1
            else EvidenceLabelAdjudication(
                fact_id=fact_id,
                action="REVIEW",
                reason="该事实缺少唯一裁决动作",
            )
        )
        for fact_id in candidate_ids
    }

    return decisions


def _resolve_adjudicated_mapping(
    mapping: FactMapping,
    item: EvidenceLabelAdjudication,
    *,
    context: _FactAdjudicationContext,
) -> tuple[FactMapping, int]:
    item, recovered_format = _normalized_adjudication(
        mapping, item, allowed_codes=context.allowed[mapping.fact_id]
    )
    try:
        resolved = _adjudicated_mapping(
            mapping,
            item,
            fact=context.facts_by_id[item.fact_id],
            labels_by_code=context.labels_by_code,
            allowed=context.allowed,
            fallback_codes=context.fallback_codes,
        )
    except ValueError as exc:
        if not context.recover_invalid_actions:
            raise
        resolved = _adjudicated_mapping(
            mapping,
            EvidenceLabelAdjudication(
                fact_id=mapping.fact_id,
                action="REVIEW",
                reason=f"该事实的裁决动作无法唯一恢复：{exc}",
            ),
            fact=context.facts_by_id[mapping.fact_id],
            labels_by_code=context.labels_by_code,
            allowed=context.allowed,
            fallback_codes=context.fallback_codes,
        )
    else:
        return (resolved, int(recovered_format))
    return (resolved, 0)


def _adjudicated_fact_mappings(
    classification: ModelClassification,
    decisions: dict[str, EvidenceLabelAdjudication],
    *,
    taxonomy: TaxonomyConfig,
    allowed: dict[str, list[str]],
    recover_invalid_actions: bool,
) -> tuple[list[FactMapping], int]:
    facts_by_id = {fact.fact_id: fact for fact in classification.extracted_facts}
    labels_by_code = {label.code: label for label in taxonomy.labels}
    fallback_codes = set(taxonomy.validation_rules.fallback_label_codes)
    context = _FactAdjudicationContext(
        facts_by_id=facts_by_id,
        labels_by_code=labels_by_code,
        allowed=allowed,
        fallback_codes=fallback_codes,
        recover_invalid_actions=recover_invalid_actions,
    )
    mappings = []
    recovery_count = 0
    for mapping in classification.fact_mappings:
        if mapping.fact_id not in decisions:
            mappings.append(mapping)
            continue
        resolved, recovered_format = _resolve_adjudicated_mapping(
            mapping,
            decisions[mapping.fact_id],
            context=context,
        )
        recovery_count += recovered_format
        mappings.append(resolved)
    return mappings, recovery_count
