from __future__ import annotations

from return_semantics.schemas import (
    AssertionCode,
    CausalAttributionCode,
    ExperiencerResolution,
    ExtractedFact,
    FactMapping,
    FactRelationType,
    FactRole,
    FactSpecificity,
    SemanticDisposition,
    SubjectCode,
)

EXPECTED_ABSTENTION_TYPES = frozenset(
    {
        "PREDICTION",
        "HYPOTHESIS",
        "NOT_TESTED",
        "PRODUCT_CLAIM",
        "APPEARANCE_INFERENCE",
        "ADVICE",
        "NEGATED",
        "INTENT",
    }
)

_RELATION_DISPOSITIONS = {
    FactRelationType.COVERED_BY: SemanticDisposition.EXPECTED_ABSTENTION,
    FactRelationType.CAUSED_BY: SemanticDisposition.EXPECTED_ABSTENTION,
    FactRelationType.SUPPORTS: SemanticDisposition.EVIDENCE_ONLY,
    FactRelationType.QUALIFIES: SemanticDisposition.EVIDENCE_ONLY,
}

_RELATION_SOURCE_ROLES = {
    FactRelationType.COVERED_BY: FactRole.CONCLUSION,
    FactRelationType.CAUSED_BY: FactRole.CONCLUSION,
    FactRelationType.SUPPORTS: FactRole.EVIDENCE,
    FactRelationType.QUALIFIES: FactRole.CONTEXT,
}

_CORE_SCOPE_FIELDS = (
    "source_ref",
    "experiencer_ref",
    "product_ref",
    "variant_ref",
)

_SAME_EVENT_RELATIONS = frozenset(
    {
        FactRelationType.COVERED_BY,
        FactRelationType.SUPPORTS,
        FactRelationType.QUALIFIES,
    }
)


def validate_fact_relations(
    facts: list[ExtractedFact],
    mappings: list[FactMapping],
) -> None:
    """校验结构化事实关系的引用、方向和核心作用域。"""
    facts_by_id = {fact.fact_id: fact for fact in facts}
    mappings_by_id = {mapping.fact_id: mapping for mapping in mappings}
    for mapping in mappings:
        _validate_fact_relation(mapping, facts_by_id, mappings_by_id)


def isolate_invalid_fact_relations(
    facts: list[ExtractedFact],
    mappings: list[FactMapping],
) -> list[FactMapping]:
    """仅降级非法关系，保留同一评论中的其他有效映射。"""
    facts_by_id = {fact.fact_id: fact for fact in facts}
    mappings_by_id = {mapping.fact_id: mapping for mapping in mappings}
    isolated: list[FactMapping] = []
    for mapping in mappings:
        try:
            _validate_fact_relation(mapping, facts_by_id, mappings_by_id)
        except ValueError as exc:
            fact = facts_by_id[mapping.fact_id]
            disposition = (
                SemanticDisposition.EVIDENCE_ONLY
                if fact.fact_role in {FactRole.EVIDENCE, FactRole.CONTEXT}
                else SemanticDisposition.MAPPING_UNCERTAIN
            )
            reason = "；".join(
                value for value in (mapping.reason.strip(), str(exc)) if value
            )
            mapping = mapping.model_copy(
                update={
                    "candidate_label_codes": list(
                        dict.fromkeys(
                            [*mapping.candidate_label_codes, *mapping.label_codes]
                        )
                    )[:1],
                    "label_codes": [],
                    "reason": reason,
                    "disposition": disposition,
                    "relation_type": FactRelationType.NONE,
                    "related_fact_ids": [],
                }
            )
        isolated.append(mapping)
    return isolated


def _validate_fact_relation(
    mapping: FactMapping,
    facts_by_id: dict[str, ExtractedFact],
    mappings_by_id: dict[str, FactMapping],
) -> None:
    if mapping.relation_type == FactRelationType.NONE:
        return
    if mapping.label_codes:
        raise ValueError(f"关联事实不能同时生成候选标签: {mapping.fact_id}")
    source_fact = facts_by_id[mapping.fact_id]
    required_role = _RELATION_SOURCE_ROLES[mapping.relation_type]
    if source_fact.fact_role != required_role:
        raise ValueError(
            f"事实关系与来源角色不一致: {mapping.fact_id}: "
            f"{mapping.relation_type} 需要 {required_role}"
        )
    for related_fact_id in mapping.related_fact_ids:
        target_fact = facts_by_id.get(related_fact_id)
        if target_fact is None:
            raise ValueError(f"事实关系引用了未知事实: {related_fact_id}")
        _validate_compatible_scope(source_fact, target_fact, mapping.relation_type)
        if not can_form_terminal_label(target_fact):
            raise ValueError(f"事实关系必须指向已确认结论事实: {related_fact_id}")
        if (
            mapping.relation_type == FactRelationType.COVERED_BY
            and mappings_by_id[related_fact_id].relation_type != FactRelationType.NONE
        ):
            raise ValueError(f"覆盖关系不能形成引用链: {related_fact_id}")


def mapping_disposition(
    fact: ExtractedFact,
    mapping: FactMapping,
) -> SemanticDisposition:
    """按事实状态和结构化关系确定最终处置，不解释模型理由文本。"""
    if (
        fact.statement_type in EXPECTED_ABSTENTION_TYPES
        or fact.assertion != AssertionCode.AFFIRMED
        or fact.specificity == FactSpecificity.GENERAL_EVALUATION
    ):
        return SemanticDisposition.EXPECTED_ABSTENTION
    if mapping.adjudication_action == "ABSTAIN":
        return SemanticDisposition.EXPECTED_ABSTENTION
    if (
        fact.experiencer_resolution == ExperiencerResolution.AMBIGUOUS
        or mapping.adjudication_action == "REVIEW"
    ):
        return SemanticDisposition.MAPPING_UNCERTAIN
    if _is_customer_caused_product_effect(fact):
        return SemanticDisposition.EXPECTED_ABSTENTION
    if fact.product_ref.startswith("OTHER:"):
        return SemanticDisposition.OUT_OF_SCOPE
    if mapping.relation_type != FactRelationType.NONE:
        return _RELATION_DISPOSITIONS[mapping.relation_type]
    if fact.fact_role != FactRole.CONCLUSION:
        if mapping.disposition == SemanticDisposition.EXPECTED_ABSTENTION:
            return SemanticDisposition.EXPECTED_ABSTENTION
        return SemanticDisposition.EVIDENCE_ONLY
    if mapping.disposition in {
        SemanticDisposition.EXPECTED_ABSTENTION,
        SemanticDisposition.EVIDENCE_ONLY,
        SemanticDisposition.OUT_OF_SCOPE,
    }:
        return SemanticDisposition.MAPPING_UNCERTAIN
    return mapping.disposition or SemanticDisposition.TAXONOMY_GAP


def can_form_terminal_label(
    fact: ExtractedFact,
    *,
    allow_ambiguous_experiencer: bool = False,
    allow_evidence: bool = False,
) -> bool:
    """只有已发生、具体且可独立聚合的事实可以形成终态标签。"""
    return (
        (
            fact.fact_role == FactRole.CONCLUSION
            or (allow_evidence and fact.fact_role == FactRole.EVIDENCE)
        )
        and fact.statement_type not in EXPECTED_ABSTENTION_TYPES
        and fact.assertion == AssertionCode.AFFIRMED
        and fact.specificity == FactSpecificity.SPECIFIC
        and (
            allow_ambiguous_experiencer
            or fact.experiencer_resolution != ExperiencerResolution.AMBIGUOUS
        )
        and not _is_customer_caused_product_effect(fact)
    )


def _is_customer_caused_product_effect(fact: ExtractedFact) -> bool:
    """用户明确造成的商品状态不能直接作为商品固有缺陷。"""
    return (
        fact.subject == SubjectCode.PRODUCT
        and fact.causal_attribution == CausalAttributionCode.CUSTOMER_ACTION
    )


def _validate_compatible_scope(
    source_fact: ExtractedFact,
    target_fact: ExtractedFact,
    relation_type: FactRelationType,
) -> None:
    scope_fields = list(_CORE_SCOPE_FIELDS)
    if relation_type in _SAME_EVENT_RELATIONS:
        scope_fields.extend(("event_ref", "subject"))
    mismatches = [
        field_name
        for field_name in scope_fields
        if getattr(source_fact, field_name) != getattr(target_fact, field_name)
    ]
    if mismatches:
        fields = ", ".join(mismatches)
        raise ValueError(
            f"事实关系作用域不相容: {source_fact.fact_id} -> "
            f"{target_fact.fact_id}: {fields}"
        )
