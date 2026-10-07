from __future__ import annotations

from return_semantics.fact_extraction import _evidence, _fact_context
from return_semantics.fact_mapping import _mapping_can_form_terminal
from return_semantics.fact_relations import mapping_disposition
from return_semantics.schemas import (
    ExtractedFact,
    FactMapping,
    ModelClassification,
    SemanticDisposition,
    TaxonomyConfig,
    UnknownSemantic,
)


def _is_current_product(fact: ExtractedFact, mapping: FactMapping) -> bool:
    if not fact.product_ref.startswith("OTHER:"):
        return True
    if mapping.label_codes:
        raise ValueError("其他商品的对照事实不能映射到当前商品标签")
    return False


def _unmapped_semantic(
    fact: ExtractedFact,
    evidence: str,
    reason: str,
    disposition: SemanticDisposition,
) -> UnknownSemantic:
    return UnknownSemantic(
        opinion=fact.opinion,
        evidence=evidence,
        reason=reason,
        disposition=disposition,
        **_fact_context(fact),
    )


def _suppressed_mapping_outcome(
    fact: ExtractedFact, mapping: FactMapping, evidence: str, taxonomy: TaxonomyConfig
) -> UnknownSemantic | None:
    if not _is_current_product(fact, mapping):
        return _unmapped_semantic(
            fact,
            evidence,
            "其他商品的对照事实不映射当前商品标签",
            SemanticDisposition.OUT_OF_SCOPE,
        )
    if (
        mapping.label_codes
        and mapping.evidence_relation == "INFERRED"
        and _mapping_can_form_terminal(fact, mapping)
    ):
        return _unmapped_semantic(
            fact,
            evidence,
            mapping.reason or "标签属性不是事实的直接或等价含义",
            SemanticDisposition.EXPECTED_ABSTENTION,
        )
    if (
        mapping.label_codes
        and mapping.label_codes[0] in taxonomy.validation_rules.fallback_label_codes
        and (not mapping.fallback_is_independent)
    ):
        return _unmapped_semantic(
            fact,
            evidence,
            mapping.reason or "概括或重复事实不单独生成兜底标签",
            SemanticDisposition.EXPECTED_ABSTENTION,
        )
    return None


def _fact_mapping_outcome(
    fact: ExtractedFact, mapping: FactMapping, evidence: str, taxonomy: TaxonomyConfig
) -> tuple[UnknownSemantic | None, bool]:
    """返回当前映射的非终态结果，以及是否跳过标签编译。"""
    outcome = _suppressed_mapping_outcome(fact, mapping, evidence, taxonomy)
    if outcome is not None:
        return (outcome, True)
    if not mapping.label_codes:
        return (
            _unmapped_semantic(
                fact,
                evidence,
                mapping.reason or "没有符合该事实的末端标签",
                mapping_disposition(fact, mapping),
            ),
            False,
        )
    if not _mapping_can_form_terminal(fact, mapping):
        return (
            _unmapped_semantic(
                fact,
                evidence,
                "该事实不能形成已确认的终态标签",
                mapping_disposition(fact, mapping),
            ),
            False,
        )
    return (None, False)


def _unresolved_fact_outcomes(
    result: ModelClassification,
    terminal_ids: set[str],
) -> tuple[dict[str, UnknownSemantic], list[UnknownSemantic]]:
    unresolved_by_id: dict[str, UnknownSemantic] = {}
    unbound_items: list[UnknownSemantic] = []
    for item in result.unknown_semantics:
        if item.fact_id is None:
            unbound_items.append(item)
        elif item.fact_id not in terminal_ids:
            unresolved_by_id.setdefault(item.fact_id, item)

    return unresolved_by_id, unbound_items


def _missing_fact_outcome(
    fact: ExtractedFact,
    mapping: FactMapping,
    comment: str,
) -> UnknownSemantic:
    disposition = (
        SemanticDisposition.MAPPING_UNCERTAIN
        if mapping.label_codes
        else mapping_disposition(fact, mapping)
    )
    reason = (
        "候选映射已接受但未进入最终维度结论"
        if mapping.label_codes
        else mapping.reason or "该事实未形成终态标签"
    )
    return _unmapped_semantic(
        fact,
        _evidence(fact, comment),
        reason,
        disposition,
    )


def _terminal_fact_ids(result: ModelClassification) -> set[str]:
    return {
        fact_id
        for unit in result.semantic_units
        for fact_id in (unit.fact_ids or ([unit.fact_id] if unit.fact_id else []))
    }


def _complete_fact_outcomes(
    result: ModelClassification,
    *,
    comment: str,
    ignored_reasons: dict[str, str] | None = None,
) -> None:
    """保证每个抽取事实恰好进入终态、忽略或未知中的一个。"""
    facts_by_id = {fact.fact_id: fact for fact in result.extracted_facts}
    mappings_by_id = {mapping.fact_id: mapping for mapping in result.fact_mappings}
    terminal_ids = _terminal_fact_ids(result)
    ignored_reasons = ignored_reasons or {}
    unresolved_by_id, unbound_items = _unresolved_fact_outcomes(result, terminal_ids)

    for fact_id, fact in facts_by_id.items():
        if fact_id in terminal_ids:
            continue
        if fact_id in ignored_reasons:
            unresolved_by_id[fact_id] = _unmapped_semantic(
                fact,
                _evidence(fact, comment),
                ignored_reasons[fact_id],
                SemanticDisposition.EVIDENCE_ONLY,
            )
            continue
        if fact_id in unresolved_by_id:
            continue
        mapping = mappings_by_id[fact_id]
        unresolved_by_id[fact_id] = _missing_fact_outcome(fact, mapping, comment)

    result.unknown_semantics = [
        *unbound_items,
        *(
            unresolved_by_id[fact.fact_id]
            for fact in result.extracted_facts
            if fact.fact_id in unresolved_by_id
        ),
    ]
    outcome_ids = terminal_ids | set(unresolved_by_id)
    if outcome_ids != set(facts_by_id) or terminal_ids & set(unresolved_by_id):
        raise ValueError("每个抽取事实必须且只能进入一个最终状态")


def _append_suppressed_fallback_outcomes(
    result: ModelClassification,
    fact_ids: set[str],
    comment: str,
) -> None:
    facts_by_id = {fact.fact_id: fact for fact in result.extracted_facts}
    result.unknown_semantics.extend(
        _unmapped_semantic(
            facts_by_id[fact_id],
            _evidence(facts_by_id[fact_id], comment),
            "兜底候选已由同一证据与作用域中的具体事实解释",
            SemanticDisposition.EXPECTED_ABSTENTION,
        )
        for fact_id in fact_ids
    )


def _normalize_fact_mapping_outcomes(result: ModelClassification) -> None:
    """将映射同步为终态、忽略、未知三组互斥的事实去向。"""
    terminal_ids = _terminal_fact_ids(result)
    outcomes = {
        item.fact_id: item
        for item in result.unknown_semantics
        if item.fact_id is not None
    }
    normalized: list[FactMapping] = []
    for mapping in result.fact_mappings:
        if mapping.fact_id in terminal_ids:
            if not mapping.label_codes:
                raise ValueError("终态事实必须保留唯一标签映射")
            updates: dict[str, object] = {
                "candidate_label_codes": [],
                "disposition": None,
            }
        else:
            outcome = outcomes.get(mapping.fact_id)
            if outcome is None:
                raise ValueError("非终态事实必须具有忽略或未知处置")
            candidates = list(
                dict.fromkeys([*mapping.candidate_label_codes, *mapping.label_codes])
            )[:1]
            updates = {
                "label_codes": [],
                "candidate_label_codes": candidates,
                "disposition": outcome.disposition,
                "reason": outcome.reason,
                "fallback_is_independent": False,
            }
        normalized.append(
            FactMapping.model_validate({**mapping.model_dump(mode="json"), **updates})
        )
    result.fact_mappings = normalized
