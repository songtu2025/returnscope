from __future__ import annotations

from typing import Any

import pandas as pd

from return_semantics.exporter import REVIEW_STATUSES
from return_semantics.schemas import (
    ProcessingStatus,
    TaxonomyConfig,
    ValidatedClassification,
)
from return_semantics.semantic_review import (
    build_semantic_review_view,
    requires_system_rerun,
)
from web_backend.classification_results.payload_facts import (
    _fact_id_by_label as _fact_id_by_label,
)
from web_backend.classification_results.payload_facts import (
    _normalize_semantic_facts,
    add_api_fact_fields,
)
from web_backend.classification_results.payload_summaries import (
    CONFIRMED_STATEMENT_TYPES as CONFIRMED_STATEMENT_TYPES,
)
from web_backend.classification_results.payload_summaries import (
    _comment_summary_status,
    _topic_summaries,
    build_comment_summary,
)
from web_backend.classification_results.payload_summaries import (
    _is_confirmed_fact as _is_confirmed_fact,
)
from web_backend.classification_results.payload_summaries import (
    _scope_key as _scope_key,
)
from web_backend.classification_results.payload_summaries import (
    _topic_identity as _topic_identity,
)
from web_backend.classification_results.payload_summaries import (
    _unit_fact_ids as _unit_fact_ids,
)

QUALITY_STATUSES = {"ready", "review_required", "unusable", "excluded"}

SEMANTIC_DISPOSITIONS = {
    "MAPPED",
    "EXPECTED_ABSTENTION",
    "EVIDENCE_ONLY",
    "TAXONOMY_GAP",
    "MAPPING_UNCERTAIN",
    "OUT_OF_SCOPE",
}

REVIEW_DISPOSITIONS = {"TAXONOMY_GAP", "MAPPING_UNCERTAIN"}

PAGE_SIZE_DEFAULT = 50

PAGE_SIZE_MAX = 200


def _nullable_text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _classification_quality(
    result: ValidatedClassification,
    semantic_disposition: str | None = None,
    *,
    source_text: str = "",
    taxonomy: TaxonomyConfig | None = None,
) -> str:
    if requires_system_rerun(
        result,
        source_text,
        taxonomy,
        processing_status=result.status,
    ):
        return "unusable"
    if semantic_disposition in REVIEW_DISPOSITIONS:
        return "review_required"
    if semantic_disposition in {
        "EXPECTED_ABSTENTION",
        "EVIDENCE_ONLY",
        "OUT_OF_SCOPE",
    }:
        return "ready"
    if result.status.value in REVIEW_STATUSES:
        return "review_required"
    return "ready"


def _unknown_disposition(value: dict[str, Any]) -> str:
    disposition = str(value.get("disposition") or "").strip().upper()
    return disposition if disposition in SEMANTIC_DISPOSITIONS else "MAPPING_UNCERTAIN"


def _classification_disposition(
    payload: dict[str, Any],
    processing_status: str,
) -> str:
    dispositions = {
        _unknown_disposition(value)
        for value in payload.get("unknown_semantics", [])
        if isinstance(value, dict)
    }
    if "TAXONOMY_GAP" in dispositions:
        return "TAXONOMY_GAP"
    if "MAPPING_UNCERTAIN" in dispositions:
        return "MAPPING_UNCERTAIN"
    if payload.get("semantic_units"):
        return "MAPPED"
    if "EXPECTED_ABSTENTION" in dispositions:
        return "EXPECTED_ABSTENTION"
    if "EVIDENCE_ONLY" in dispositions:
        return "EVIDENCE_ONLY"
    if "OUT_OF_SCOPE" in dispositions:
        return "OUT_OF_SCOPE"
    if processing_status == ProcessingStatus.NO_TEXT_EVIDENCE.value:
        return "EXPECTED_ABSTENTION"
    return "MAPPED"


def classification_comment_status(
    payload: dict[str, Any], taxonomy: TaxonomyConfig | None
) -> str:
    """按记录详情相同的事实和主题规则计算评论状态。"""
    facts = _normalize_semantic_facts(payload, taxonomy)
    summaries = _topic_summaries(facts, taxonomy, payload.get("semantic_relations", []))
    return _comment_summary_status(payload, summaries)


def _prepare_classification_payload(
    payload: dict[str, Any],
    taxonomy: TaxonomyConfig | None,
    processing_status: str,
    *,
    include_api_fields: bool = True,
    source_text: str = "",
) -> dict[str, Any]:
    normalized = dict(payload)
    unknown_semantics = []
    for source in normalized.get("unknown_semantics", []):
        if not isinstance(source, dict):
            continue
        unknown = dict(source)
        unknown["disposition"] = _unknown_disposition(unknown)
        unknown_semantics.append(unknown)
    normalized["unknown_semantics"] = unknown_semantics
    facts = _normalize_semantic_facts(normalized, taxonomy)
    if include_api_fields:
        add_api_fact_fields(facts)
    normalized["semantic_units"] = facts
    normalized["semantic_disposition"] = _classification_disposition(
        normalized, processing_status
    )
    summaries = _topic_summaries(
        facts,
        taxonomy,
        normalized.get("semantic_relations", []),
    )
    comment_status = _comment_summary_status(normalized, summaries)
    normalized["comment_summary"] = build_comment_summary(
        normalized, facts, comment_status
    )
    if include_api_fields:
        normalized["atomic_facts"] = facts
        normalized["comment_conclusions"] = summaries
        normalized["comment_summary_status"] = comment_status
        normalized["semantic_review"] = build_semantic_review_view(
            normalized,
            source_text,
            taxonomy,
            processing_status=processing_status,
        )
    return normalized


def prepare_semantic_record(
    record: dict[str, Any],
    taxonomy: TaxonomyConfig | None,
) -> dict[str, Any]:
    """统一读取入口的语义状态，不改写持久化结果。"""
    classification = _prepare_classification_payload(
        record.get("classification", {}),
        taxonomy,
        str(record.get("processing_status") or ""),
        source_text=str(record.get("comment") or ""),
    )
    for field in (
        "semantic_disposition",
        "comment_summary_status",
        "atomic_facts",
        "comment_conclusions",
    ):
        record[field] = classification.pop(field)
    record["classification"] = classification
    return record


def _version_quality(qualities: list[str]) -> str:
    if "unusable" in qualities:
        return "unusable"
    if any(value != "ready" for value in qualities):
        return "review_required"
    return "ready"
