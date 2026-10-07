from __future__ import annotations

from return_semantics.dimension_contracts import (
    _contract_branch_code as _contract_branch_code,
)
from return_semantics.dimension_contracts import (
    _contract_label_codes as _contract_label_codes,
)
from return_semantics.dimension_contracts import _decision_payload as _decision_payload
from return_semantics.dimension_contracts import (
    _record_downgraded_facts as _record_downgraded_facts,
)
from return_semantics.dimension_contracts import (
    _validate_context_dimension as _validate_context_dimension,
)
from return_semantics.fact_extraction import (
    _allowed_labels_by_fact,
)
from return_semantics.fact_mapping_adjudication import (
    _adjudicated_mapping as _adjudicated_mapping,
)
from return_semantics.fact_mapping_adjudication import (
    _normalized_adjudication as _normalized_adjudication,
)
from return_semantics.fact_mapping_adjudication import (
    _validated_mapping_label as _validated_mapping_label,
)
from return_semantics.fact_mapping_models import (
    EvidenceLabelAdjudication as EvidenceLabelAdjudication,
)
from return_semantics.fact_mapping_models import (
    EvidenceLabelAdjudications as EvidenceLabelAdjudications,
)
from return_semantics.fact_mapping_models import FactDecisions as FactDecisions
from return_semantics.fact_mapping_models import FactMappings as FactMappings
from return_semantics.fact_mapping_models import ModelFactMapping as ModelFactMapping
from return_semantics.fact_mapping_models import ModelFactMappings as ModelFactMappings
from return_semantics.fact_mapping_prompts import (
    _adjudication_messages as _adjudication_messages,
)
from return_semantics.fact_mapping_prompts import _mapping_messages as _mapping_messages
from return_semantics.fact_relations import can_form_terminal_label
from return_semantics.fact_units import _fact_identity as _fact_identity
from return_semantics.fact_units import (
    _overlapping_fact_identity as _overlapping_fact_identity,
)
from return_semantics.fact_units import _retain_fact_unit as _retain_fact_unit
from return_semantics.schemas import (
    ExtractedFact,
    FactMapping,
    ModelClassification,
    TaxonomyConfig,
)
from return_semantics.taxonomy_hierarchy import label_path


def _mapping_can_form_terminal(fact: ExtractedFact, mapping: FactMapping) -> bool:
    adjudicated = mapping.adjudication_action in {"ACCEPT", "REPLACE"}
    return can_form_terminal_label(
        fact,
        allow_ambiguous_experiencer=adjudicated,
        allow_evidence=adjudicated,
    )


def _can_be_adjudicated(fact: ExtractedFact) -> bool:
    return can_form_terminal_label(
        fact,
        allow_ambiguous_experiencer=True,
        allow_evidence=True,
    )


def _validate_coverage(items: list, facts: list[ExtractedFact]) -> None:
    identifiers = [item.fact_id for item in items]
    if len(set(identifiers)) != len(identifiers) or set(identifiers) != {
        fact.fact_id for fact in facts
    }:
        raise ValueError("每个事实必须且只能有一条路由或映射记录")


def _mapping_payload(facts: list[ExtractedFact], taxonomy: TaxonomyConfig) -> dict:
    allowed = _allowed_labels_by_fact(facts, taxonomy)
    selected = {code for codes in allowed.values() for code in codes}
    return {
        "facts": [fact.model_dump(mode="json") for fact in facts],
        "allowed_labels_by_fact": allowed,
        "labels": [
            {**label.model_dump(mode="json"), "path": label_path(taxonomy, label.code)}
            for label in taxonomy.labels
            if label.code in selected
        ],
        "instructions": taxonomy.instructions,
        "dimension_contracts": [
            contract.model_dump(mode="json")
            for contract in taxonomy.validation_rules.dimension_contracts
        ],
        "fallback_label_codes": taxonomy.validation_rules.fallback_label_codes,
        "schema": ModelFactMappings.model_json_schema(),
    }


def _parse_model_fact_mappings(payload: dict) -> FactMappings:
    """忽略模型回传的程序审计字段，其余结构仍按严格契约校验。"""
    normalized = dict(payload)
    if isinstance(normalized.get("mappings"), list):
        normalized["mappings"] = [
            {
                key: value
                for key, value in item.items()
                if key not in {"candidate_label_codes", "adjudication_action"}
            }
            if isinstance(item, dict)
            else item
            for item in normalized["mappings"]
        ]
    writable = ModelFactMappings.model_validate(normalized)
    return FactMappings(
        mappings=[
            FactMapping.model_validate(mapping.model_dump(mode="json"))
            for mapping in writable.mappings
        ]
    )


def _adjudication_payload(
    classification: ModelClassification,
    taxonomy: TaxonomyConfig,
    comment: str,
    allowed: dict[str, list[str]],
) -> dict:
    candidate_facts = [
        fact
        for fact in classification.extracted_facts
        if _can_be_adjudicated(fact) and fact.product_ref.startswith("CURRENT")
    ]
    fact_ids = {fact.fact_id for fact in candidate_facts}
    label_codes = {code for fact_id in fact_ids for code in allowed.get(fact_id, [])}
    return {
        "comment": comment,
        "facts": [fact.model_dump(mode="json") for fact in candidate_facts],
        "current_mappings": [
            mapping.model_dump(mode="json")
            for mapping in classification.fact_mappings
            if mapping.fact_id in fact_ids
        ],
        "allowed_labels_by_fact": {
            fact_id: allowed.get(fact_id, []) for fact_id in fact_ids
        },
        "labels": [
            {**label.model_dump(mode="json"), "path": label_path(taxonomy, label.code)}
            for label in taxonomy.labels
            if label.code in label_codes
        ],
        "schema": EvidenceLabelAdjudications.model_json_schema(),
    }


# 保留已有入口的模块归属，避免移动实现影响反射和序列化。
for _entry in (
    FactMappings,
    ModelFactMapping,
    ModelFactMappings,
    EvidenceLabelAdjudication,
    EvidenceLabelAdjudications,
    FactDecisions,
    _fact_identity,
    _retain_fact_unit,
    _overlapping_fact_identity,
    _contract_label_codes,
    _decision_payload,
    _contract_branch_code,
    _validate_context_dimension,
    _record_downgraded_facts,
    _adjudication_messages,
    _mapping_messages,
    _adjudicated_mapping,
    _normalized_adjudication,
    _validated_mapping_label,
):
    _entry.__module__ = __name__
del _entry
