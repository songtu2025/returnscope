from __future__ import annotations

import hashlib
from typing import cast

from return_semantics.schemas import ProcessingStatus, TaxonomyConfig
from return_semantics.semantic_review_coverage import (
    _coverage_evidence as _coverage_evidence,
)
from return_semantics.semantic_review_coverage import (
    _coverage_summary as _coverage_summary,
)
from return_semantics.semantic_review_coverage import (
    _unexplained_fragments as _unexplained_fragments,
)
from return_semantics.semantic_review_diagnostics import (
    _DETAILS_NOT_APPLICABLE as _DETAILS_NOT_APPLICABLE,
)
from return_semantics.semantic_review_diagnostics import (
    _DETAILS_NOT_RETAINED as _DETAILS_NOT_RETAINED,
)
from return_semantics.semantic_review_diagnostics import (
    _DIAGNOSTIC_METADATA as _DIAGNOSTIC_METADATA,
)
from return_semantics.semantic_review_diagnostics import (
    _SYSTEM_REVIEW_REASON_PREFIXES as _SYSTEM_REVIEW_REASON_PREFIXES,
)
from return_semantics.semantic_review_diagnostics import (
    _failure_diagnostic as _failure_diagnostic,
)
from return_semantics.semantic_review_diagnostics import (
    _structured_failure_diagnostic as _structured_failure_diagnostic,
)
from return_semantics.semantic_review_diagnostics import (
    _system_review_reasons as _system_review_reasons,
)
from return_semantics.semantic_review_items import (
    _NO_TAG_DISPOSITIONS as _NO_TAG_DISPOSITIONS,
)
from return_semantics.semantic_review_items import (
    _UNRESOLVED_DISPOSITIONS as _UNRESOLVED_DISPOSITIONS,
)
from return_semantics.semantic_review_items import (
    ANALYSIS_FAILURE as ANALYSIS_FAILURE,
)
from return_semantics.semantic_review_items import (
    MAPPED as MAPPED,
)
from return_semantics.semantic_review_items import (
    NO_TAG_NEEDED as NO_TAG_NEEDED,
)
from return_semantics.semantic_review_items import (
    TAXONOMY_GAP as TAXONOMY_GAP,
)
from return_semantics.semantic_review_items import (
    TRUE_AMBIGUITY as TRUE_AMBIGUITY,
)
from return_semantics.semantic_review_items import (
    _enum_value as _enum_value,
)
from return_semantics.semantic_review_items import (
    _evidence_source as _evidence_source,
)
from return_semantics.semantic_review_items import (
    _fact_evidence as _fact_evidence,
)
from return_semantics.semantic_review_items import (
    _fact_id as _fact_id,
)
from return_semantics.semantic_review_items import (
    _fact_review_evidence,
)
from return_semantics.semantic_review_items import (
    _fallback_evidence as _fallback_evidence,
)
from return_semantics.semantic_review_items import (
    _get as _get,
)
from return_semantics.semantic_review_items import (
    _index_by_fact_id as _index_by_fact_id,
)
from return_semantics.semantic_review_items import (
    _item as _item,
)
from return_semantics.semantic_review_items import (
    _label_path as _label_path,
)
from return_semantics.semantic_review_items import (
    _list as _list,
)
from return_semantics.semantic_review_items import (
    _mapped_label as _mapped_label,
)
from return_semantics.semantic_review_items import (
    _review_disposition as _review_disposition,
)
from return_semantics.semantic_review_items import (
    _ReviewEvidence as _ReviewEvidence,
)
from return_semantics.semantic_review_items import (
    _stable_item_id as _stable_item_id,
)
from return_semantics.semantic_review_items import (
    _text as _text,
)

READY = "READY"
BUSINESS_REVIEW_REQUIRED = "BUSINESS_REVIEW_REQUIRED"
SYSTEM_RERUN_REQUIRED = "SYSTEM_RERUN_REQUIRED"

_NON_BLOCKING_DIAGNOSTIC_CODES = {"SECONDARY_MODEL_MISSING"}

_BUSINESS_REVIEW_STATUSES = {
    ProcessingStatus.SECONDARY_REVIEW.value,
    ProcessingStatus.MANUAL_REVIEW.value,
    ProcessingStatus.UNKNOWN_SEMANTIC.value,
}


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


def build_semantic_review_view(
    result: object,
    source_text: str,
    taxonomy: TaxonomyConfig | None = None,
    *,
    processing_status: str | ProcessingStatus | None = None,
) -> dict[str, object]:
    """将现有分类结果投影为人工可核验的证据清单。

    该函数只整理已有事实和映射，不判断结果是否正确，也不使用主因决定处置。
    """
    facts = _list(result, "extracted_facts") or _list(result, "facts")
    mappings = _list(result, "fact_mappings")
    units = _list(result, "semantic_units")
    unknowns = [
        *_list(result, "unknown_semantics"),
        *_list(result, "ignored_semantics"),
    ]
    items, handled_units, handled_unknowns = _fact_review_items(
        facts, mappings, units, unknowns, taxonomy
    )
    items.extend(_unhandled_unit_items(units, handled_units, taxonomy))
    items.extend(_unhandled_unknown_items(unknowns, handled_unknowns, taxonomy))

    status = _enum_value(
        processing_status or _get(result, "processing_status") or _get(result, "status")
    )
    items.extend(_analysis_failure_items(result, status, taxonomy))
    coverage_evidence = _coverage_evidence(items)
    # 已删除的错误提取仅保留审计证据，不重新作为漏抽片段出现。
    coverage_evidence.extend(
        _text(_get(review, "evidence_text"))
        for review in _list(result, "human_semantic_reviews")
        if _get(review, "applied") and _get(review, "action") == "remove"
    )
    unexplained = (
        [] if facts else _unexplained_fragments(source_text, coverage_evidence)
    )
    return {
        "semantic_items": items,
        "coverage_summary": _coverage_summary(items, unexplained),
        "unexplained_fragments": unexplained,
    }


def review_route(
    result: object,
    source_text: str,
    taxonomy: TaxonomyConfig | None = None,
    *,
    processing_status: str | ProcessingStatus | None = None,
) -> str:
    """按业务复核、系统重跑和直接可用三类责任集中路由。"""
    view = build_semantic_review_view(
        result,
        source_text,
        taxonomy,
        processing_status=processing_status,
    )
    items = cast(list[dict[str, object]], view["semantic_items"])
    if any(
        item.get("disposition") == ANALYSIS_FAILURE
        and item.get("business_review_required") is False
        and item.get("diagnostic_code") not in _NON_BLOCKING_DIAGNOSTIC_CODES
        for item in items
    ):
        return SYSTEM_RERUN_REQUIRED
    if any(item.get("business_review_required") is True for item in items):
        return BUSINESS_REVIEW_REQUIRED
    if any(item.get("disposition") in {TAXONOMY_GAP, TRUE_AMBIGUITY} for item in items):
        return BUSINESS_REVIEW_REQUIRED
    if view["unexplained_fragments"]:
        return BUSINESS_REVIEW_REQUIRED

    diagnostic_codes = {
        _text(item.get("diagnostic_code"))
        for item in items
        if _text(item.get("diagnostic_code"))
    }
    if diagnostic_codes and diagnostic_codes <= _NON_BLOCKING_DIAGNOSTIC_CODES:
        return READY

    status = _enum_value(
        processing_status or _get(result, "processing_status") or _get(result, "status")
    )
    if status in _BUSINESS_REVIEW_STATUSES:
        return BUSINESS_REVIEW_REQUIRED
    return READY


def requires_system_rerun(
    result: object,
    source_text: str,
    taxonomy: TaxonomyConfig | None = None,
    *,
    processing_status: str | ProcessingStatus | None = None,
) -> bool:
    """系统诊断要求重跑时返回真。"""
    return (
        review_route(
            result,
            source_text,
            taxonomy,
            processing_status=processing_status,
        )
        == SYSTEM_RERUN_REQUIRED
    )


def requires_business_review(
    result: object,
    source_text: str,
    taxonomy: TaxonomyConfig | None = None,
    *,
    processing_status: str | ProcessingStatus | None = None,
) -> bool:
    """仅在业务人员能对语义结果采取明确动作时进入人工复核。"""
    return (
        review_route(
            result,
            source_text,
            taxonomy,
            processing_status=processing_status,
        )
        == BUSINESS_REVIEW_REQUIRED
    )


# 既有辅助入口直接复用职责模块，保留导入路径。
for _entry in (
    _system_review_reasons,
    _failure_diagnostic,
    _structured_failure_diagnostic,
    _unexplained_fragments,
    _coverage_evidence,
    _coverage_summary,
):
    _entry.__module__ = __name__
