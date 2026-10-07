from __future__ import annotations

import hashlib

from return_semantics.schemas import ProcessingStatus, TaxonomyConfig
from return_semantics.semantic_review_diagnostics import (
    _failure_diagnostic,
    _structured_failure_diagnostic,
    _system_review_reasons,
)
from return_semantics.semantic_review_items import (
    ANALYSIS_FAILURE,
    MAPPED,
    _enum_value,
    _fact_id,
    _fact_review_evidence,
    _fallback_evidence,
    _get,
    _index_by_fact_id,
    _item,
    _list,
    _mapped_label,
    _review_disposition,
    _ReviewEvidence,
    _text,
)


def _analysis_failure_item(
    reason: str,
    taxonomy: TaxonomyConfig | None,
    *,
    model_error: bool = False,
    structured_diagnostic: object | None = None,
) -> dict[str, object]:
    diagnostic = (
        _structured_failure_diagnostic(structured_diagnostic)
        if structured_diagnostic is not None
        else _failure_diagnostic(reason, model_error=model_error)
    )
    evidence_text = _text(diagnostic.get("evidence_text"))
    diagnostic_digest = hashlib.sha256(
        repr((reason, diagnostic)).encode("utf-8")
    ).hexdigest()[:8]
    item = _item(
        review_evidence=_ReviewEvidence(
            prefix=(
                f"analysis-failure:{diagnostic['diagnostic_code']}:{diagnostic_digest}"
            ),
            fact_id="",
            texts=[evidence_text or "系统运行记录"],
            sources=["SYSTEM"],
            opinion=str(diagnostic["diagnostic_title"]),
        ),
        label_code="",
        disposition=ANALYSIS_FAILURE,
        reason=reason,
        taxonomy=taxonomy,
    )
    item.update(diagnostic)
    return item


def _fact_review_items(
    facts: list[object],
    mappings: list[object],
    units: list[object],
    unknowns: list[object],
    taxonomy: TaxonomyConfig | None,
) -> tuple[list[dict[str, object]], set[int], set[int]]:
    mapping_by_fact = _index_by_fact_id(mappings)
    unit_by_fact = _index_by_fact_id(units)
    unknown_by_fact = _index_by_fact_id(unknowns)
    items: list[dict[str, object]] = []
    handled_units: set[int] = set()
    handled_unknowns: set[int] = set()

    for fact in facts:
        fact_id = _fact_id(fact)
        mapping = mapping_by_fact.get(fact_id)
        unit = unit_by_fact.get(fact_id)
        unknown = unknown_by_fact.get(fact_id)
        if unit is not None:
            handled_units.add(id(unit))
        if unknown is not None:
            handled_unknowns.add(id(unknown))

        label_code = _mapped_label(mapping, unit)
        raw_disposition = (
            _get(mapping, "disposition") if mapping is not None else None
        ) or (_get(unknown, "disposition") if unknown is not None else None)
        review_evidence = _fact_review_evidence(fact, unit, unknown, fact_id=fact_id)
        reason = (
            _text(_get(mapping, "reason"))
            or _text(_get(unknown, "reason"))
            or _text(_get(unit, "decision_reason"))
        )
        items.append(
            _item(
                review_evidence=review_evidence,
                label_code=label_code,
                disposition=_review_disposition(raw_disposition, label_code),
                reason=reason,
                taxonomy=taxonomy,
            )
        )
        if _get(fact, "sentiment"):
            items[-1]["sentiment"] = _enum_value(_get(fact, "sentiment"))
    return items, handled_units, handled_unknowns


def _unhandled_unit_items(
    units: list[object],
    handled_units: set[int],
    taxonomy: TaxonomyConfig | None,
) -> list[dict[str, object]]:
    items = []
    for unit in units:
        if id(unit) in handled_units:
            continue
        fact_id = _fact_id(unit)
        evidence, sources = _fallback_evidence(unit)
        label_code = _text(_get(unit, "label_code"))
        items.append(
            _item(
                review_evidence=_ReviewEvidence(
                    prefix="semantic",
                    fact_id=fact_id,
                    texts=evidence,
                    sources=sources,
                    opinion=_text(_get(unit, "opinion")),
                ),
                label_code=label_code,
                disposition=MAPPED,
                reason=_text(_get(unit, "decision_reason")),
                taxonomy=taxonomy,
            )
        )
        if _get(unit, "sentiment"):
            items[-1]["sentiment"] = _enum_value(_get(unit, "sentiment"))
    return items


def _unhandled_unknown_items(
    unknowns: list[object],
    handled_unknowns: set[int],
    taxonomy: TaxonomyConfig | None,
) -> list[dict[str, object]]:
    items = []
    for unknown in unknowns:
        if id(unknown) in handled_unknowns:
            continue
        fact_id = _fact_id(unknown)
        evidence, sources = _fallback_evidence(unknown)
        items.append(
            _item(
                review_evidence=_ReviewEvidence(
                    prefix="unknown",
                    fact_id=fact_id,
                    texts=evidence,
                    sources=sources,
                    opinion=_text(_get(unknown, "opinion")),
                ),
                label_code="",
                disposition=_review_disposition(_get(unknown, "disposition"), ""),
                reason=_text(_get(unknown, "reason")),
                taxonomy=taxonomy,
            )
        )
    return items


def _analysis_failure_items(
    result: object,
    status: str,
    taxonomy: TaxonomyConfig | None,
) -> list[dict[str, object]]:
    structured_diagnostics = _list(result, "review_diagnostics")
    structured_codes = {
        _text(_get(diagnostic, "code")) for diagnostic in structured_diagnostics
    }
    items = [
        _analysis_failure_item(
            _text(_get(diagnostic, "detail"))
            or _text(_get(diagnostic, "code"))
            or "分析诊断",
            taxonomy,
            structured_diagnostic=diagnostic,
        )
        for diagnostic in structured_diagnostics
    ]
    if status == ProcessingStatus.MODEL_ERROR.value:
        reasons = [_text(reason) for reason in _list(result, "review_reasons")]
        if not structured_codes.intersection({"MODEL_RUN_TIMEOUT", "MODEL_RUN_FAILED"}):
            items.append(
                _analysis_failure_item(
                    " | ".join(reason for reason in reasons if reason)
                    or "模型处理失败",
                    taxonomy,
                    model_error=True,
                )
            )
        return items

    items.extend(
        _analysis_failure_item(reason, taxonomy)
        for reason in _system_review_reasons(result)
        if _text(_failure_diagnostic(reason)["diagnostic_code"]) not in structured_codes
    )
    return items
