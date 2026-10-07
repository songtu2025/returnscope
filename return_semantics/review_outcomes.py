from __future__ import annotations

from dataclasses import dataclass

from return_semantics.review_conclusions import (
    _orphan_fact_conclusion,
    _unit_conclusion,
    _unknown_conclusion,
)
from return_semantics.review_evidence import (
    _IGNORED_DISPOSITIONS,
    _evidence_matches,
    _represented_fact_ids,
    _unresolved_conclusion_facts,
)
from return_semantics.schemas import (
    ExtractedFact,
    ReviewDiagnostic,
    SemanticUnit,
    UnknownSemantic,
    ValidatedClassification,
)

_MODEL_MISMATCH_ACTION = "请业务员以原文证据为准，核对两次分析结果并选择正确标签。"


@dataclass(frozen=True)
class _ReviewOutcome:
    evidence_text: str
    evidence: tuple[tuple[str, tuple[str, ...]], ...]
    business_key: tuple[object, ...]
    result: str
    opinion: str
    scope_text: str


def _unit_review_outcome(unit: SemanticUnit) -> _ReviewOutcome:
    scope_parts = [
        f"来源={unit.source_ref}",
        f"体验者={unit.experiencer_ref}",
        f"商品={unit.product_ref}",
        f"规格={unit.variant_ref}",
        f"主体={unit.subject.value}",
        f"部位={unit.part}",
        f"方向={unit.sentiment.value}",
        f"确定性={unit.assertion.value}",
    ]
    if unit.operation:
        scope_parts.append(f"操作={unit.operation}")
    if unit.condition:
        scope_parts.append(f"条件={unit.condition}")
    if unit.reference_basis.value != "NONE":
        scope_parts.append(f"比较基准={unit.reference_basis.value}")
    if unit.implicit:
        scope_parts.append("表达方式=隐含")
    if unit.claim_relation.value != "NONE":
        scope_parts.append(f"宣称关系={unit.claim_relation.value}")
    conclusion = _unit_conclusion(unit)
    return _ReviewOutcome(
        evidence_text=unit.evidence,
        evidence=conclusion.evidence,
        business_key=conclusion.business_key,
        result=unit.label_code,
        opinion=unit.opinion,
        scope_text="；".join(scope_parts),
    )


def _unknown_review_outcome(unknown: UnknownSemantic) -> _ReviewOutcome:
    scope_parts = [
        f"来源={unknown.source_ref}",
        f"体验者={unknown.experiencer_ref}",
        f"商品={unknown.product_ref}",
        f"规格={unknown.variant_ref}",
        f"陈述类型={unknown.statement_type}",
    ]
    if unknown.operation:
        scope_parts.append(f"操作={unknown.operation}")
    if unknown.condition:
        scope_parts.append(f"条件={unknown.condition}")
    if unknown.reference_basis.value != "NONE":
        scope_parts.append(f"比较基准={unknown.reference_basis.value}")
    conclusion = _unknown_conclusion(unknown)
    return _ReviewOutcome(
        evidence_text=unknown.evidence,
        evidence=conclusion.evidence,
        business_key=conclusion.business_key,
        result=unknown.disposition.value,
        opinion=unknown.opinion,
        scope_text="；".join(scope_parts),
    )


def _orphan_fact_review_outcome(fact: ExtractedFact) -> _ReviewOutcome:
    scope_parts = [
        f"来源={fact.source_ref}",
        f"体验者={fact.experiencer_ref}",
        f"商品={fact.product_ref}",
        f"规格={fact.variant_ref}",
        f"主体={fact.subject.value}",
        f"部位={fact.part}",
        f"方向={fact.sentiment.value}",
        f"陈述类型={fact.statement_type}",
    ]
    if fact.operation:
        scope_parts.append(f"操作={fact.operation}")
    if fact.condition:
        scope_parts.append(f"条件={fact.condition}")
    conclusion = _orphan_fact_conclusion(fact)
    return _ReviewOutcome(
        evidence_text=" | ".join(span.text for span in fact.evidence_spans),
        evidence=conclusion.evidence,
        business_key=conclusion.business_key,
        result="UNRESOLVED_FACT",
        opinion=fact.opinion,
        scope_text="；".join(scope_parts),
    )


def _review_outcomes(result: ValidatedClassification) -> list[_ReviewOutcome]:
    outcomes = [_unit_review_outcome(unit) for unit in result.semantic_units]
    outcomes.extend(
        _unknown_review_outcome(unknown)
        for unknown in result.unknown_semantics
        if unknown.disposition not in _IGNORED_DISPOSITIONS
    )
    represented_fact_ids = _represented_fact_ids(result)
    mappings_by_id = {mapping.fact_id: mapping for mapping in result.fact_mappings}
    for fact in _unresolved_conclusion_facts(
        result.extracted_facts, mappings_by_id, represented_fact_ids
    ):
        outcomes.append(_orphan_fact_review_outcome(fact))
    return outcomes


def _outcome_text(outcome: _ReviewOutcome) -> str:
    opinion = f"：{outcome.opinion}" if outcome.opinion else ""
    scope = f"（{outcome.scope_text}）" if outcome.scope_text else ""
    return f"{outcome.result}{opinion}{scope}"


def build_model_difference_diagnostics(
    primary: ValidatedClassification,
    secondary: ValidatedClassification,
) -> list[ReviewDiagnostic]:
    unmatched_secondary = _review_outcomes(secondary)
    unmatched_primary: list[_ReviewOutcome] = []
    for primary_outcome in _review_outcomes(primary):
        match_index = _match_outcome_index(
            primary_outcome, unmatched_secondary, require_business_key=True
        )
        if match_index is None:
            unmatched_primary.append(primary_outcome)
        else:
            unmatched_secondary.pop(match_index)

    diagnostics: list[ReviewDiagnostic] = []
    for primary_outcome in unmatched_primary:
        match_index = _match_outcome_index(
            primary_outcome, unmatched_secondary, require_business_key=False
        )
        secondary_outcome = (
            unmatched_secondary.pop(match_index) if match_index is not None else None
        )
        diagnostics.append(_difference_diagnostic(primary_outcome, secondary_outcome))
    diagnostics.extend(
        ReviewDiagnostic(
            code="MODEL_RESULT_MISMATCH",
            evidence_text=outcome.evidence_text,
            secondary_result=_outcome_text(outcome),
            detail="主模型未确认复核模型识别的观点",
            action=_MODEL_MISMATCH_ACTION,
        )
        for outcome in unmatched_secondary
    )
    if diagnostics:
        return diagnostics
    return [
        ReviewDiagnostic(
            code="MODEL_RESULT_MISMATCH",
            detail="两次模型的结构化语义结果不一致",
            action=_MODEL_MISMATCH_ACTION,
        )
    ]


def _match_outcome_index(
    primary_outcome: _ReviewOutcome,
    unmatched_secondary: list[_ReviewOutcome],
    *,
    require_business_key: bool,
) -> int | None:
    return next(
        (
            index
            for index, secondary_outcome in enumerate(unmatched_secondary)
            if (
                not require_business_key
                or primary_outcome.business_key == secondary_outcome.business_key
            )
            and _evidence_matches(
                primary_outcome.evidence,
                secondary_outcome.evidence,
            )
        ),
        None,
    )


def _difference_diagnostic(
    primary_outcome: _ReviewOutcome,
    secondary_outcome: _ReviewOutcome | None,
) -> ReviewDiagnostic:
    return ReviewDiagnostic(
        code="MODEL_RESULT_MISMATCH",
        evidence_text=primary_outcome.evidence_text,
        primary_result=_outcome_text(primary_outcome),
        secondary_result=(
            _outcome_text(secondary_outcome) if secondary_outcome else ""
        ),
        detail=(
            "两次模型对同一证据给出了不同标签、处置或业务作用域"
            if secondary_outcome
            else "复核模型未确认主模型识别的观点"
        ),
        action=_MODEL_MISMATCH_ACTION,
    )
