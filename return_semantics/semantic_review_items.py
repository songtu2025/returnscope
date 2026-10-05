from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from return_semantics.schemas import TaxonomyConfig
from return_semantics.taxonomy_hierarchy import label_path

MAPPED = "MAPPED"

NO_TAG_NEEDED = "NO_TAG_NEEDED"

TAXONOMY_GAP = "TAXONOMY_GAP"

TRUE_AMBIGUITY = "TRUE_AMBIGUITY"

ANALYSIS_FAILURE = "ANALYSIS_FAILURE"

_NO_TAG_DISPOSITIONS = {
    "EXPECTED_ABSTENTION",
    "EVIDENCE_ONLY",
    "OUT_OF_SCOPE",
}

_UNRESOLVED_DISPOSITIONS = {
    "MAPPING_UNCERTAIN": TRUE_AMBIGUITY,
    "TAXONOMY_GAP": TAXONOMY_GAP,
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


@dataclass(frozen=True, kw_only=True)
class _ReviewEvidence:
    prefix: str
    fact_id: str
    texts: list[str]
    sources: list[str]
    opinion: str


def _item(
    *,
    review_evidence: _ReviewEvidence,
    label_code: str,
    disposition: str,
    reason: str,
    taxonomy: TaxonomyConfig | None,
) -> dict[str, object]:
    prefix = review_evidence.prefix
    fact_id = review_evidence.fact_id
    evidence = review_evidence.texts
    sources = review_evidence.sources
    opinion = review_evidence.opinion
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


def _fact_review_evidence(
    fact: object,
    unit: object | None,
    unknown: object | None,
    *,
    fact_id: str,
) -> _ReviewEvidence:
    """保留事实证据优先于旧语义单元的装配规则。"""
    evidence, sources = _fact_evidence(fact)
    if not evidence:
        evidence, sources = _fallback_evidence(unit, unknown)
    opinion = _text(_get(fact, "opinion")) or _text(_get(unit, "opinion"))
    return _ReviewEvidence(
        prefix="fact",
        fact_id=fact_id,
        texts=evidence,
        sources=sources,
        opinion=opinion,
    )
