from __future__ import annotations

import hashlib
import re
from collections import Counter
from collections.abc import Mapping
from typing import Any, cast

from return_semantics.schemas import ProcessingStatus, TaxonomyConfig
from return_semantics.taxonomy_hierarchy import label_path

MAPPED = "MAPPED"
NO_TAG_NEEDED = "NO_TAG_NEEDED"
TAXONOMY_GAP = "TAXONOMY_GAP"
TRUE_AMBIGUITY = "TRUE_AMBIGUITY"
ANALYSIS_FAILURE = "ANALYSIS_FAILURE"

READY = "READY"
BUSINESS_REVIEW_REQUIRED = "BUSINESS_REVIEW_REQUIRED"
SYSTEM_RERUN_REQUIRED = "SYSTEM_RERUN_REQUIRED"

_NON_BLOCKING_DIAGNOSTIC_CODES = {"SECONDARY_MODEL_MISSING"}

_BUSINESS_REVIEW_STATUSES = {
    ProcessingStatus.SECONDARY_REVIEW.value,
    ProcessingStatus.MANUAL_REVIEW.value,
    ProcessingStatus.UNKNOWN_SEMANTIC.value,
}

_NO_TAG_DISPOSITIONS = {
    "EXPECTED_ABSTENTION",
    "EVIDENCE_ONLY",
    "OUT_OF_SCOPE",
}
_UNRESOLVED_DISPOSITIONS = {
    "MAPPING_UNCERTAIN": TRUE_AMBIGUITY,
    "TAXONOMY_GAP": TAXONOMY_GAP,
}
_SYSTEM_REVIEW_REASON_PREFIXES = (
    "覆盖审计失败",
    "二次模型调用失败:",
    "二次模型结果未通过程序校验",
    "两次模型的语义结果不一致",
    "低成本模型与主模型结果不一致",
    "风险复核模型缺失",
)

_DETAILS_NOT_RETAINED = "NOT_RETAINED"
_DETAILS_NOT_APPLICABLE = "NOT_APPLICABLE"

_DIAGNOSTIC_METADATA = {
    "COVERAGE_AUDIT_FAILED": (
        "SEMANTIC_ANALYSIS_QUALITY",
        "可能存在用户反馈漏抽",
        "请核对疑似漏抽片段；没有片段时请系统重跑。",
    ),
    "MODEL_RESULT_MISMATCH": (
        "SEMANTIC_ANALYSIS_QUALITY",
        "两次模型结果不一致",
        "请核对两次模型的逐项差异；没有差异明细时请系统重跑。",
    ),
    "LABEL_RULE_REVIEW_REQUIRED": (
        "SEMANTIC_ANALYSIS_QUALITY",
        "标签规则要求人工判断",
        "请业务员核对原文证据是否足以支持该标签，并确认保留或修改标签。",
    ),
    "SECONDARY_MODEL_MISSING": (
        "TECHNICAL_CONFIGURATION",
        "风险复核模型未配置",
        "已使用主模型完成复核；无需业务员核验，请管理员补充风险复核模型配置。",
    ),
    "SECONDARY_MODEL_TIMEOUT": (
        "TECHNICAL_RUNTIME",
        "风险复核调用超时",
        "无需业务员核验；请系统重试风险复核。",
    ),
    "SECONDARY_MODEL_CALL_FAILED": (
        "TECHNICAL_RUNTIME",
        "风险复核调用失败",
        "无需业务员核验；请系统重试风险复核。",
    ),
    "SECONDARY_RESULT_INVALID": (
        "TECHNICAL_RUNTIME",
        "风险复核结果校验失败",
        "无需业务员核验；请系统重新执行风险复核。",
    ),
    "MODEL_RUN_TIMEOUT": (
        "TECHNICAL_RUNTIME",
        "模型分析超时",
        "无需业务员核验；请系统重跑本条分析。",
    ),
    "MODEL_RUN_FAILED": (
        "TECHNICAL_RUNTIME",
        "模型分析未完成",
        "无需业务员核验；请系统重跑本条分析。",
    ),
}


def _get(value: object, field: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(field, default)
    return getattr(value, field, default)


def _list(value: object, field: str) -> list[Any]:
    items = _get(value, field, [])
    return list(items or [])


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value) or "")


def _text(value: object) -> str:
    return str(value or "").strip()


def _fact_id(value: object) -> str:
    direct = _text(_get(value, "fact_id"))
    if direct:
        return direct
    fact_ids = _list(value, "fact_ids")
    return _text(fact_ids[0]) if fact_ids else ""


def _stable_item_id(prefix: str, *parts: str) -> str:
    fact_id = parts[0] if parts and parts[0] else ""
    if fact_id:
        return f"fact:{fact_id}"
    payload = "\x1f".join(parts[1:] if parts else [])
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}"


def _review_disposition(raw_disposition: object, label_code: str) -> str:
    if label_code:
        return MAPPED
    disposition = _enum_value(raw_disposition)
    if disposition in _NO_TAG_DISPOSITIONS:
        return NO_TAG_NEEDED
    return _UNRESOLVED_DISPOSITIONS.get(disposition, TRUE_AMBIGUITY)


def _label_path(taxonomy: TaxonomyConfig | None, label_code: str) -> list[str]:
    if taxonomy is None or not label_code:
        return []
    known_codes = {label.code for label in taxonomy.labels}
    if label_code not in known_codes:
        return []
    return label_path(taxonomy, label_code)


def _fact_evidence(fact: object) -> tuple[list[str], list[str]]:
    texts: list[str] = []
    sources: list[str] = []
    for span in _list(fact, "evidence_spans"):
        text = _text(_get(span, "text"))
        if text:
            texts.append(text)
            sources.append(_enum_value(_get(span, "source", "COMMENT")))
    return texts, sources


def _fallback_evidence(*values: object) -> tuple[list[str], list[str]]:
    for value in values:
        if value is None:
            continue
        evidence = _text(_get(value, "evidence"))
        if evidence:
            source = _enum_value(_get(value, "evidence_source", "COMMENT"))
            return [evidence], [source]
    return [], []


def _evidence_source(sources: list[str]) -> str:
    unique = list(dict.fromkeys(source or "COMMENT" for source in sources))
    if not unique:
        return "COMMENT"
    if len(unique) == 1:
        return unique[0]
    return "TITLE_AND_BODY"


def _item(
    *,
    prefix: str,
    fact_id: str,
    evidence: list[str],
    sources: list[str],
    opinion: str,
    label_code: str,
    disposition: str,
    reason: str,
    taxonomy: TaxonomyConfig | None,
) -> dict[str, object]:
    evidence_text = " | ".join(dict.fromkeys(evidence))
    item: dict[str, object] = {
        "item_id": _stable_item_id(
            prefix,
            fact_id,
            evidence_text,
            opinion,
            label_code,
            disposition,
        ),
        "fact_id": fact_id,
        "evidence_text": evidence_text,
        "evidence_source": _evidence_source(sources),
        "opinion": opinion,
        "label_code": label_code,
        "label_path": _label_path(taxonomy, label_code),
        "disposition": disposition,
        "reason": reason,
        "_coverage_evidence": evidence,
    }
    return item


def _index_by_fact_id(values: list[object]) -> dict[str, object]:
    return {fact_id: value for value in values if (fact_id := _fact_id(value))}


def _mapped_label(mapping: object | None, unit: object | None) -> str:
    if mapping is not None:
        label_codes = _list(mapping, "label_codes")
        if label_codes:
            return _text(label_codes[0])
    return _text(_get(unit, "label_code")) if unit is not None else ""


def _unexplained_fragments(source_text: str, evidence: list[str]) -> list[str]:
    if not source_text.strip():
        return []
    covered = [False] * len(source_text)
    for span in dict.fromkeys(item.strip() for item in evidence if item.strip()):
        words = re.split(r"\s+", span)
        pattern = r"\s+".join(re.escape(word) for word in words)
        for match in re.finditer(pattern, source_text, flags=re.IGNORECASE):
            covered[match.start() : match.end()] = [True] * (
                match.end() - match.start()
            )

    remainder = "".join(
        " " if is_covered else char
        for char, is_covered in zip(source_text, covered, strict=True)
    )
    fragments = []
    for fragment in re.split(r"[\r\n.!?;,:。！？；，：]+", remainder):
        normalized = " ".join(fragment.split()).strip("-_/|()[]{}'“”‘’")
        if normalized and any(character.isalnum() for character in normalized):
            fragments.append(normalized)
    return fragments


def _system_review_reasons(result: object) -> list[str]:
    reasons = [_text(reason) for reason in _list(result, "review_reasons")]
    return list(
        dict.fromkeys(
            reason
            for reason in reasons
            if reason.startswith(_SYSTEM_REVIEW_REASON_PREFIXES)
        )
    )


def _failure_diagnostic(reason: str, *, model_error: bool = False) -> dict[str, object]:
    normalized = reason.casefold()
    is_timeout = (
        "超时" in reason or "timeout" in normalized or "timed out" in normalized
    )
    if model_error:
        code = "MODEL_RUN_TIMEOUT" if is_timeout else "MODEL_RUN_FAILED"
    elif reason.startswith("覆盖审计失败"):
        code = "COVERAGE_AUDIT_FAILED"
    elif reason.startswith(
        ("两次模型的语义结果不一致", "低成本模型与主模型结果不一致")
    ):
        code = "MODEL_RESULT_MISMATCH"
    elif reason.startswith("风险复核模型缺失"):
        code = "SECONDARY_MODEL_MISSING"
    elif reason.startswith("二次模型调用失败:"):
        code = (
            "SECONDARY_MODEL_TIMEOUT" if is_timeout else "SECONDARY_MODEL_CALL_FAILED"
        )
    else:
        code = "SECONDARY_RESULT_INVALID"

    domain, title, action = _DIAGNOSTIC_METADATA[code]
    if code == "COVERAGE_AUDIT_FAILED":
        action = (
            "当前结果未保留疑似漏抽的原文片段，业务员无法据此判断；"
            "请系统重跑并保留疑似漏抽片段。"
        )
    elif code == "MODEL_RESULT_MISMATCH":
        action = (
            "当前结果未保留两次模型的差异明细，业务员无法据此判断；"
            "请系统重跑并保留逐项差异。"
        )
    return {
        "diagnostic_domain": domain,
        "diagnostic_code": code,
        "diagnostic_title": title,
        "detail_status": (
            _DETAILS_NOT_RETAINED
            if code in {"COVERAGE_AUDIT_FAILED", "MODEL_RESULT_MISMATCH"}
            else _DETAILS_NOT_APPLICABLE
        ),
        "action": action,
        "business_review_required": False,
    }


def _structured_failure_diagnostic(value: object) -> dict[str, object]:
    code = _text(_get(value, "code")) or "ANALYSIS_DIAGNOSTIC"
    evidence_text = _text(_get(value, "evidence_text"))
    primary_result = _text(_get(value, "primary_result"))
    secondary_result = _text(_get(value, "secondary_result"))
    detail = _text(_get(value, "detail"))
    action = _text(_get(value, "action"))

    domain, title, default_action = _DIAGNOSTIC_METADATA.get(
        code,
        _DIAGNOSTIC_METADATA["MODEL_RUN_FAILED"],
    )

    if code == "COVERAGE_AUDIT_FAILED":
        has_details = bool(evidence_text)
    elif code in {"MODEL_RESULT_MISMATCH", "LABEL_RULE_REVIEW_REQUIRED"}:
        has_details = bool(evidence_text or primary_result or secondary_result)
    else:
        has_details = False
    is_system_action = action in {"SYSTEM_RERUN", "SYSTEM_RETRY", "ADMIN_CONFIG"}
    if is_system_action and code == "COVERAGE_AUDIT_FAILED":
        action_text = "无需业务员判断本次运行异常；请系统重跑，疑似片段仅用于定位。"
    elif is_system_action and code == "MODEL_RESULT_MISMATCH":
        action_text = "无需业务员判断本次运行异常；请系统重跑，差异明细仅用于定位。"
    else:
        action_text = default_action if not action or is_system_action else action
    return {
        "diagnostic_domain": domain,
        "diagnostic_code": code,
        "diagnostic_title": title,
        "detail_status": (
            "AVAILABLE"
            if has_details
            else _DETAILS_NOT_APPLICABLE
            if domain != "SEMANTIC_ANALYSIS_QUALITY"
            else _DETAILS_NOT_RETAINED
        ),
        "evidence_text": evidence_text,
        "primary_result": primary_result,
        "secondary_result": secondary_result,
        "detail": detail,
        "action": action_text,
        "business_review_required": domain == "SEMANTIC_ANALYSIS_QUALITY"
        and has_details
        and not is_system_action,
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
        prefix=(
            f"analysis-failure:{diagnostic['diagnostic_code']}:{diagnostic_digest}"
        ),
        fact_id="",
        evidence=[evidence_text or "系统运行记录"],
        sources=["SYSTEM"],
        opinion=str(diagnostic["diagnostic_title"]),
        label_code="",
        disposition=ANALYSIS_FAILURE,
        reason=reason,
        taxonomy=taxonomy,
    )
    item.update(diagnostic)
    return item


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
        evidence, sources = _fact_evidence(fact)
        if not evidence:
            evidence, sources = _fallback_evidence(unit, unknown)
        opinion = _text(_get(fact, "opinion")) or _text(_get(unit, "opinion"))
        reason = (
            _text(_get(mapping, "reason"))
            or _text(_get(unknown, "reason"))
            or _text(_get(unit, "decision_reason"))
        )
        items.append(
            _item(
                prefix="fact",
                fact_id=fact_id,
                evidence=evidence,
                sources=sources,
                opinion=opinion,
                label_code=label_code,
                disposition=_review_disposition(raw_disposition, label_code),
                reason=reason,
                taxonomy=taxonomy,
            )
        )

    for unit in units:
        if id(unit) in handled_units:
            continue
        fact_id = _fact_id(unit)
        evidence, sources = _fallback_evidence(unit)
        label_code = _text(_get(unit, "label_code"))
        items.append(
            _item(
                prefix="semantic",
                fact_id=fact_id,
                evidence=evidence,
                sources=sources,
                opinion=_text(_get(unit, "opinion")),
                label_code=label_code,
                disposition=MAPPED,
                reason=_text(_get(unit, "decision_reason")),
                taxonomy=taxonomy,
            )
        )

    for unknown in unknowns:
        if id(unknown) in handled_unknowns:
            continue
        fact_id = _fact_id(unknown)
        evidence, sources = _fallback_evidence(unknown)
        items.append(
            _item(
                prefix="unknown",
                fact_id=fact_id,
                evidence=evidence,
                sources=sources,
                opinion=_text(_get(unknown, "opinion")),
                label_code="",
                disposition=_review_disposition(_get(unknown, "disposition"), ""),
                reason=_text(_get(unknown, "reason")),
                taxonomy=taxonomy,
            )
        )

    status = _enum_value(
        processing_status or _get(result, "processing_status") or _get(result, "status")
    )
    structured_diagnostics = _list(result, "review_diagnostics")
    structured_codes = {
        _text(_get(diagnostic, "code")) for diagnostic in structured_diagnostics
    }
    items.extend(
        _analysis_failure_item(
            _text(_get(diagnostic, "detail"))
            or _text(_get(diagnostic, "code"))
            or "分析诊断",
            taxonomy,
            structured_diagnostic=diagnostic,
        )
        for diagnostic in structured_diagnostics
    )
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
    elif system_reasons := _system_review_reasons(result):
        items.extend(
            _analysis_failure_item(reason, taxonomy)
            for reason in system_reasons
            if _text(_failure_diagnostic(reason)["diagnostic_code"])
            not in structured_codes
        )

    coverage_evidence: list[str] = []
    for item in items:
        raw_evidence = item.pop("_coverage_evidence", [])
        if isinstance(raw_evidence, list):
            coverage_evidence.extend(
                str(evidence) for evidence in raw_evidence if str(evidence)
            )
    unexplained = (
        [] if facts else _unexplained_fragments(source_text, coverage_evidence)
    )
    counts = Counter(_text(item["disposition"]) for item in items)
    coverage_summary = {
        "total": len(items),
        "mapped": counts[MAPPED],
        "no_tag_needed": counts[NO_TAG_NEEDED],
        "taxonomy_gap": counts[TAXONOMY_GAP],
        "true_ambiguity": counts[TRUE_AMBIGUITY],
        "analysis_failure": counts[ANALYSIS_FAILURE],
        "unexplained_fragment_count": len(unexplained),
        "complete": not unexplained
        and not any(
            counts[disposition]
            for disposition in (TAXONOMY_GAP, TRUE_AMBIGUITY, ANALYSIS_FAILURE)
        ),
    }
    return {
        "semantic_items": items,
        "coverage_summary": coverage_summary,
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
