from __future__ import annotations

from dataclasses import dataclass

from return_semantics.fact_adjudication import (
    _adjudicated_fact_mappings,
    _adjudications_by_fact,
)
from return_semantics.fact_extraction import (
    _evidence,
    _fact_assertion,
    _fact_context,
    _validate_facts,
)
from return_semantics.fact_mapping import (
    EvidenceLabelAdjudications,
    FactMappings,
    _fact_identity,
    _mapping_can_form_terminal,
    _retain_fact_unit,
    _validate_coverage,
    _validated_mapping_label,
)
from return_semantics.fact_outcomes import (
    _append_suppressed_fallback_outcomes as _append_suppressed_fallback_outcomes,
)
from return_semantics.fact_outcomes import (
    _complete_fact_outcomes as _complete_fact_outcomes,
)
from return_semantics.fact_outcomes import (
    _fact_mapping_outcome as _fact_mapping_outcome,
)
from return_semantics.fact_outcomes import _is_current_product as _is_current_product
from return_semantics.fact_outcomes import (
    _normalize_fact_mapping_outcomes as _normalize_fact_mapping_outcomes,
)
from return_semantics.fact_outcomes import _unmapped_semantic as _unmapped_semantic
from return_semantics.fact_relations import (
    isolate_invalid_fact_relations,
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
)
from return_semantics.semantic_guardrails import apply_fallback_precedence


@dataclass(frozen=True, kw_only=True)
class _FactCompilationContext:
    taxonomy: TaxonomyConfig
    labels: dict[str, LabelDefinition]
    allowed: dict[str, list[str]]
    recover_mapping_errors: bool
    comment: str


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
    decisions = _adjudications_by_fact(
        classification, adjudications, recover_invalid_actions
    )
    mappings, recovery_count = _adjudicated_fact_mappings(
        classification,
        decisions,
        taxonomy=taxonomy,
        allowed=allowed,
        recover_invalid_actions=recover_invalid_actions,
    )
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


def _compile_fact_units(
    result: ModelClassification,
    facts: list[ExtractedFact],
    by_id: dict[str, FactMapping],
    *,
    context: _FactCompilationContext,
) -> None:
    seen: dict[tuple, int] = {}
    for fact in facts:
        mapping = by_id[fact.fact_id]
        evidence = _evidence(fact, context.comment)
        outcome, skip_labels = _fact_mapping_outcome(
            fact, mapping, evidence, context.taxonomy
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
            context.labels,
            context.allowed,
            context.recover_mapping_errors,
            context.comment,
        )


def _finalize_fact_classification(
    result: ModelClassification,
    comment: str,
    taxonomy: TaxonomyConfig,
) -> None:
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
    _compile_fact_units(
        result,
        facts,
        by_id,
        context=_FactCompilationContext(
            taxonomy=taxonomy,
            labels=labels,
            allowed=allowed,
            recover_mapping_errors=recover_mapping_errors,
            comment=comment,
        ),
    )
    _finalize_fact_classification(result, comment, taxonomy)
    return result


def _fact_semantic_unit(
    fact: ExtractedFact,
    mapping: FactMapping,
    code: str,
    evidence: str,
    assertion: AssertionCode,
) -> SemanticUnit:
    return SemanticUnit(
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
        unit = _fact_semantic_unit(fact, mapping, code, evidence, assertion)
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


# 保留已有辅助入口的模块归属，避免移动实现影响反射和序列化。
for _entry in (
    _fact_mapping_outcome,
    _unmapped_semantic,
    _complete_fact_outcomes,
    _append_suppressed_fallback_outcomes,
    _normalize_fact_mapping_outcomes,
    _is_current_product,
):
    _entry.__module__ = __name__
del _entry
