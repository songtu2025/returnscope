from __future__ import annotations

from return_semantics.fact_extraction import (
    _evidence,
    _fact_assertion,
    _fact_context,
    _validate_facts,
)
from return_semantics.fact_mapping import (
    EvidenceLabelAdjudication,
    EvidenceLabelAdjudications,
    FactMappings,
    _adjudicated_mapping,
    _can_be_adjudicated,
    _fact_identity,
    _mapping_can_form_terminal,
    _normalized_adjudication,
    _retain_fact_unit,
    _validate_coverage,
    _validated_mapping_label,
)
from return_semantics.fact_relations import (
    isolate_invalid_fact_relations,
    mapping_disposition,
    validate_fact_relations,
)
from return_semantics.schemas import (
    AssertionCode,
    ExtractedFact,
    FactMapping,
    LabelDefinition,
    ModelClassification,
    SemanticDisposition,
    SemanticUnit,
    TaxonomyConfig,
    UnknownSemantic,
)
from return_semantics.semantic_guardrails import apply_fallback_precedence


def compile_evidence_label_adjudications(
    classification: ModelClassification,
    adjudications: EvidenceLabelAdjudications,
    *,
    comment: str,
    taxonomy: TaxonomyConfig,
    allowed: dict[str, list[str]],
    recover_invalid_actions: bool = False,
    recovery_metrics: dict[str, int] | None = None,
) -> ModelClassification:
    """裁决为每个可终态事实确定唯一映射或处置，并重建结果。"""
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

    facts_by_id = {fact.fact_id: fact for fact in classification.extracted_facts}
    labels_by_code = {label.code: label for label in taxonomy.labels}
    fallback_codes = set(taxonomy.validation_rules.fallback_label_codes)
    mappings = []
    recovery_count = 0
    for mapping in classification.fact_mappings:
        if mapping.fact_id not in candidate_ids:
            mappings.append(mapping)
            continue
        item, recovered_format = _normalized_adjudication(
            mapping,
            decisions[mapping.fact_id],
            allowed_codes=allowed[mapping.fact_id],
        )
        try:
            resolved = _adjudicated_mapping(
                mapping,
                item,
                fact=facts_by_id[item.fact_id],
                labels_by_code=labels_by_code,
                allowed=allowed,
                fallback_codes=fallback_codes,
            )
        except ValueError as exc:
            if not recover_invalid_actions:
                raise
            resolved = _adjudicated_mapping(
                mapping,
                EvidenceLabelAdjudication(
                    fact_id=mapping.fact_id,
                    action="REVIEW",
                    reason=f"该事实的裁决动作无法唯一恢复：{exc}",
                ),
                fact=facts_by_id[mapping.fact_id],
                labels_by_code=labels_by_code,
                allowed=allowed,
                fallback_codes=fallback_codes,
            )
        else:
            recovery_count += int(recovered_format)
        mappings.append(resolved)
    result = compile_fact_classification(
        classification.extracted_facts,
        FactMappings(mappings=mappings),
        comment=comment,
        taxonomy=taxonomy,
        allowed=allowed,
        recover_mapping_errors=True,
    )
    if recovery_metrics is not None and recovery_count:
        recovery_metrics["adjudication_format_recoveries"] = (
            recovery_metrics.get("adjudication_format_recoveries", 0) + recovery_count
        )
    return result


def compile_fact_classification(
    facts: list[ExtractedFact],
    mappings: FactMappings,
    *,
    comment: str,
    taxonomy: TaxonomyConfig,
    allowed: dict[str, list[str]],
    recover_mapping_errors: bool = False,
) -> ModelClassification:
    """映射只能选择标签，最终观点和证据始终取自抽取事实。"""
    _validate_facts(facts, comment, taxonomy)
    _validate_coverage(mappings.mappings, facts)
    effective_mappings = mappings.mappings
    if recover_mapping_errors:
        effective_mappings = isolate_invalid_fact_relations(facts, effective_mappings)
    else:
        validate_fact_relations(facts, effective_mappings)
    by_id = {item.fact_id: item for item in effective_mappings}
    labels = {label.code: label for label in taxonomy.labels}
    result = ModelClassification(
        extracted_facts=facts, fact_mappings=effective_mappings
    )
    seen: dict[tuple, int] = {}
    for fact in facts:
        mapping = by_id[fact.fact_id]
        evidence = _evidence(fact, comment)
        outcome, skip_labels = _fact_mapping_outcome(
            fact,
            mapping,
            evidence,
            taxonomy,
        )
        if outcome is not None:
            result.unknown_semantics.append(outcome)
        if skip_labels:
            continue
        _append_fact_units(
            result,
            seen,
            fact,
            mapping,
            evidence,
            labels,
            allowed,
            recover_mapping_errors,
            comment,
        )
    suppressed_fallback_ids = apply_fallback_precedence(
        result.semantic_units,
        set(taxonomy.validation_rules.fallback_label_codes),
    )
    _append_suppressed_fallback_outcomes(result, suppressed_fallback_ids, comment)
    _complete_fact_outcomes(result, comment=comment)
    _normalize_fact_mapping_outcomes(result)
    retained_codes = {unit.label_code for unit in result.semantic_units}
    result.primary_label_codes = [
        code for code in result.primary_label_codes if code in retained_codes
    ]
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
    return result


def _fact_mapping_outcome(
    fact: ExtractedFact,
    mapping: FactMapping,
    evidence: str,
    taxonomy: TaxonomyConfig,
) -> tuple[UnknownSemantic | None, bool]:
    """返回当前映射的非终态结果，以及是否跳过标签编译。"""
    if not _is_current_product(fact, mapping):
        return (
            _unmapped_semantic(
                fact,
                evidence,
                "其他商品的对照事实不映射当前商品标签",
                SemanticDisposition.OUT_OF_SCOPE,
            ),
            True,
        )
    if (
        mapping.label_codes
        and mapping.evidence_relation == "INFERRED"
        and _mapping_can_form_terminal(fact, mapping)
    ):
        return (
            _unmapped_semantic(
                fact,
                evidence,
                mapping.reason or "标签属性不是事实的直接或等价含义",
                SemanticDisposition.EXPECTED_ABSTENTION,
            ),
            True,
        )
    if (
        mapping.label_codes
        and mapping.label_codes[0] in taxonomy.validation_rules.fallback_label_codes
        and not mapping.fallback_is_independent
    ):
        return (
            _unmapped_semantic(
                fact,
                evidence,
                mapping.reason or "概括或重复事实不单独生成兜底标签",
                SemanticDisposition.EXPECTED_ABSTENTION,
            ),
            True,
        )
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
    return None, False


def _append_fact_units(
    result: ModelClassification,
    seen: dict[tuple, int],
    fact: ExtractedFact,
    mapping: FactMapping,
    evidence: str,
    labels: dict[str, LabelDefinition],
    allowed: dict[str, list[str]],
    recover_mapping_errors: bool,
    comment: str,
) -> None:
    for code in dict.fromkeys(mapping.label_codes):
        try:
            _validated_mapping_label(fact, code, labels, allowed)
        except ValueError as exc:
            if not recover_mapping_errors:
                raise
            result.unknown_semantics.append(
                _unmapped_semantic(
                    fact,
                    evidence,
                    str(exc),
                    SemanticDisposition.MAPPING_UNCERTAIN,
                )
            )
            continue
        if not _mapping_can_form_terminal(fact, mapping):
            continue
        assertion = _fact_assertion(fact)
        unit = SemanticUnit(
            subject=fact.subject,
            label_code=code,
            opinion=fact.opinion,
            sentiment=fact.sentiment,
            assertion=assertion,
            part=fact.part,
            evidence=evidence,
            implicit=False,
            decision_reason=mapping.reason or "原子事实直接支持该末端标签",
            **_fact_context(fact),
            fact_ids=[fact.fact_id],
        )
        _retain_fact_unit(
            result.semantic_units,
            seen,
            _fact_identity(fact, code),
            unit,
            comment,
        )
        if (
            fact.is_primary_reason
            and assertion == AssertionCode.AFFIRMED
            and code not in result.primary_label_codes
        ):
            result.primary_label_codes.append(code)


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


def _complete_fact_outcomes(
    result: ModelClassification,
    *,
    comment: str,
    ignored_reasons: dict[str, str] | None = None,
) -> None:
    """保证每个抽取事实恰好进入终态、忽略或未知中的一个。"""
    facts_by_id = {fact.fact_id: fact for fact in result.extracted_facts}
    mappings_by_id = {mapping.fact_id: mapping for mapping in result.fact_mappings}
    terminal_ids = {
        fact_id
        for unit in result.semantic_units
        for fact_id in (unit.fact_ids or ([unit.fact_id] if unit.fact_id else []))
    }
    ignored_reasons = ignored_reasons or {}
    unresolved_by_id: dict[str, UnknownSemantic] = {}
    unbound_items: list[UnknownSemantic] = []
    for item in result.unknown_semantics:
        if item.fact_id is None:
            unbound_items.append(item)
        elif item.fact_id not in terminal_ids:
            unresolved_by_id.setdefault(item.fact_id, item)

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
        unresolved_by_id[fact_id] = _unmapped_semantic(
            fact,
            _evidence(fact, comment),
            reason,
            disposition,
        )

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
    terminal_ids = {
        fact_id
        for unit in result.semantic_units
        for fact_id in (unit.fact_ids or ([unit.fact_id] if unit.fact_id else []))
    }
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


def _is_current_product(fact: ExtractedFact, mapping: FactMapping) -> bool:
    if not fact.product_ref.startswith("OTHER:"):
        return True
    if mapping.label_codes:
        raise ValueError("其他商品的对照事实不能映射到当前商品标签")
    return False
