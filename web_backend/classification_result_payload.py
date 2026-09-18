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
from return_semantics.taxonomy_hierarchy import label_path, label_path_codes

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

CONFIRMED_STATEMENT_TYPES = {"EXPERIENCE", "EVALUATION", "REPORTED"}

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


def _fact_id_by_label(payload: dict[str, Any]) -> dict[str, str]:
    candidates: dict[str, set[str]] = {}
    for mapping in payload.get("fact_mappings", []):
        if not isinstance(mapping, dict):
            continue
        fact_id = str(mapping.get("fact_id") or "").strip()
        if not fact_id:
            continue
        for label_code in mapping.get("label_codes", []):
            candidates.setdefault(str(label_code), set()).add(fact_id)
    return {
        label_code: next(iter(fact_ids))
        for label_code, fact_ids in candidates.items()
        if len(fact_ids) == 1
    }


def _normalize_semantic_facts(
    payload: dict[str, Any],
    taxonomy: TaxonomyConfig | None,
) -> list[dict[str, Any]]:
    facts = {
        str(value.get("fact_id")): value
        for value in payload.get("extracted_facts", [])
        if isinstance(value, dict) and value.get("fact_id")
    }
    fact_ids_by_label = _fact_id_by_label(payload)
    normalized: list[dict[str, Any]] = []
    for source in payload.get("semantic_units", []):
        if not isinstance(source, dict):
            continue
        unit = dict(source)
        label_code = str(unit.get("label_code") or "")
        fact_id = str(
            unit.get("fact_id") or fact_ids_by_label.get(label_code) or ""
        ).strip()
        fact = facts.get(fact_id, {})
        unit["fact_id"] = fact_id or None
        for field in (
            "actor_ref",
            "source_ref",
            "experiencer_ref",
            "product_ref",
            "variant_ref",
            "event_ref",
            "reference_basis",
            "statement_type",
            "fact_role",
            "operation",
            "condition",
            "causal_attribution",
            "causal_attribution_reason",
            "decision_reason",
            "context_fact_ids",
        ):
            fact_value = fact.get(field)
            if unit.get(field) in (None, "", "UNSPECIFIED") and fact_value not in (
                None,
                "",
            ):
                unit[field] = fact_value
        unit["condition"] = unit.get("condition") or ""
        unit["evidence_source"] = str(
            unit.get("evidence_source") or fact.get("evidence_source") or "UNKNOWN"
        )
        unit.setdefault("fact_role", "CONCLUSION")
        unit.setdefault("causal_attribution", "UNKNOWN")
        unit.setdefault("causal_attribution_reason", "")
        unit.setdefault("decision_reason", "")
        unit.setdefault("context_fact_ids", [])
        if taxonomy:
            unit["label_code_path"] = label_path_codes(taxonomy, label_code)
            unit["label_path"] = label_path(taxonomy, label_code)
        else:
            unit.setdefault("label_code_path", [])
            unit.setdefault("label_path", [])
        normalized.append(unit)
    return normalized


def _topic_identity(
    taxonomy: TaxonomyConfig | None,
    label_code: str,
) -> tuple[str, str, list[str], list[str]]:
    if taxonomy is None:
        return label_code, label_code, [], []
    label = next((value for value in taxonomy.labels if value.code == label_code), None)
    if label is None:
        return label_code, label_code, [], []
    code_path = label_path_codes(taxonomy, label_code)
    name_path = label_path(taxonomy, label_code)
    if taxonomy.structure_version == 2 and len(code_path) > 1:
        return code_path[-2], name_path[-2], code_path[:-1], name_path[:-1]
    topic_code = label.group or label.code
    topic_name = label.group or label.name
    return topic_code, topic_name, [topic_code], [topic_name]


def _is_confirmed_fact(unit: dict[str, Any]) -> bool:
    if str(unit.get("assertion") or "AFFIRMED") != "AFFIRMED":
        return False
    statement_type = str(unit.get("statement_type") or "")
    return not statement_type or statement_type in CONFIRMED_STATEMENT_TYPES


def _scope_key(unit: dict[str, Any]) -> tuple[str, ...] | None:
    values = tuple(
        str(unit.get(field) or "").strip()
        for field in (
            "actor_ref",
            "product_ref",
            "event_ref",
            "operation",
            "part",
            "condition",
        )
    )
    return values if all(values) and "UNSPECIFIED" not in values else None


def _unit_fact_ids(unit: dict[str, Any]) -> list[str]:
    values = [
        str(value).strip() for value in unit.get("fact_ids", []) if str(value).strip()
    ]
    fact_id = str(unit.get("fact_id") or "").strip()
    if fact_id:
        values.insert(0, fact_id)
    return list(dict.fromkeys(values))


def _topic_summaries(
    facts: list[dict[str, Any]],
    taxonomy: TaxonomyConfig | None,
    relations: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    topics: dict[str, dict[str, Any]] = {}
    for fact in facts:
        label_code = str(fact.get("label_code") or "")
        topic_code, topic_name, code_path, name_path = _topic_identity(
            taxonomy, label_code
        )
        topic = topics.setdefault(
            topic_code,
            {
                "topic_code": topic_code,
                "topic_name": topic_name,
                "topic_code_path": code_path,
                "topic_path": name_path,
                "facts": [],
            },
        )
        topic["facts"].append(fact)

    summaries: list[dict[str, Any]] = []
    for topic_code in sorted(topics):
        topic = topics[topic_code]
        facts_for_topic = topic.pop("facts")
        confirmed = [value for value in facts_for_topic if _is_confirmed_fact(value)]
        sentiments = {
            str(value.get("sentiment") or "")
            for value in confirmed
            if value.get("sentiment")
        }
        label_codes = {
            str(value["label_code"])
            for value in facts_for_topic
            if value.get("label_code")
        }
        related_types = {
            str(relation.get("relation_type") or "")
            for relation in relations or []
            if isinstance(relation, dict)
            and label_codes.intersection(
                str(value) for value in relation.get("label_codes", [])
            )
        }
        if "CONFLICT" in related_types:
            status = "CONFLICT"
        elif "MIXED" in related_types:
            status = "MIXED"
        elif not confirmed or not sentiments.intersection({"POSITIVE", "NEGATIVE"}):
            status = "NO_CONFIRMED"
        elif {"POSITIVE", "NEGATIVE"}.issubset(sentiments):
            positive_scopes = {
                scope
                for value in confirmed
                if value.get("sentiment") == "POSITIVE"
                if (scope := _scope_key(value)) is not None
            }
            negative_scopes = {
                scope
                for value in confirmed
                if value.get("sentiment") == "NEGATIVE"
                if (scope := _scope_key(value)) is not None
            }
            status = "CONFLICT" if positive_scopes & negative_scopes else "MIXED"
        elif "NEGATIVE" in sentiments:
            status = "NEGATIVE"
        else:
            status = "POSITIVE"
        fact_ids = [
            fact_id for value in facts_for_topic for fact_id in _unit_fact_ids(value)
        ]
        event_ids = {
            str(value["event_ref"])
            for value in facts_for_topic
            if value.get("event_ref") not in (None, "", "UNSPECIFIED")
        }
        summaries.append(
            {
                **topic,
                "status": status,
                "supporting_fact_ids": list(dict.fromkeys(fact_ids)),
                "label_codes": sorted(label_codes),
                "fact_count": len(facts_for_topic),
                "event_count": len(event_ids),
            }
        )
    return summaries


def _comment_summary_status(
    payload: dict[str, Any],
    summaries: list[dict[str, Any]],
) -> str:
    summary = payload.get("comment_summary")
    if isinstance(summary, dict):
        status = str(summary.get("status") or "")
        is_explicit = status != "NO_CONFIRMED" or any(
            summary.get(field)
            for field in ("fact_ids", "positive_label_codes", "negative_label_codes")
        )
        if is_explicit and status in {
            "POSITIVE",
            "NEGATIVE",
            "MIXED",
            "CONFLICT",
            "NO_CONFIRMED",
        }:
            return status
    statuses = {str(value["status"]) for value in summaries}
    if "CONFLICT" in statuses:
        return "CONFLICT"
    if "MIXED" in statuses or {"POSITIVE", "NEGATIVE"}.issubset(statuses):
        return "MIXED"
    if "NEGATIVE" in statuses:
        return "NEGATIVE"
    if "POSITIVE" in statuses:
        return "POSITIVE"
    return "NO_CONFIRMED"


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
        for fact in facts:
            fact["fact_text_zh"] = str(fact.get("opinion") or "")
            fact["original_evidence"] = str(fact.get("evidence") or "")
            fact["object_ref"] = str(fact.get("product_ref") or "CURRENT")
            fact["usage_task"] = str(fact.get("operation") or "")
            fact["scenario"] = str(fact.get("condition") or "")
            fact["certainty"] = str(fact.get("assertion") or "AFFIRMED")
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
    current_summary = normalized.get("comment_summary")
    summary_is_default = isinstance(current_summary, dict) and (
        str(current_summary.get("status") or "") == "NO_CONFIRMED"
        and not any(
            current_summary.get(field)
            for field in ("fact_ids", "positive_label_codes", "negative_label_codes")
        )
    )
    if not isinstance(current_summary, dict) or summary_is_default:
        normalized["comment_summary"] = {
            "status": comment_status,
            "fact_ids": list(
                dict.fromkeys(
                    fact_id for fact in facts for fact_id in _unit_fact_ids(fact)
                )
            ),
            "positive_label_codes": sorted(
                {
                    str(fact["label_code"])
                    for fact in facts
                    if fact.get("sentiment") == "POSITIVE" and fact.get("label_code")
                }
            ),
            "negative_label_codes": sorted(
                {
                    str(fact["label_code"])
                    for fact in facts
                    if fact.get("sentiment") == "NEGATIVE" and fact.get("label_code")
                }
            ),
        }
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


def _version_quality(qualities: list[str]) -> str:
    if "unusable" in qualities:
        return "unusable"
    if any(value != "ready" for value in qualities):
        return "review_required"
    return "ready"
