from __future__ import annotations

from typing import Any

from return_semantics.schemas import TaxonomyConfig
from return_semantics.taxonomy_hierarchy import label_path, label_path_codes

FACT_CONTEXT_FIELDS = (
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
)


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
        for field in FACT_CONTEXT_FIELDS:
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


def add_api_fact_fields(facts: list[dict[str, Any]]) -> None:
    """在已经复制的事实上补充展示字段，持久化载荷不调用此步骤。"""
    for fact in facts:
        fact["fact_text_zh"] = str(fact.get("opinion") or "")
        fact["original_evidence"] = str(fact.get("evidence") or "")
        fact["object_ref"] = str(fact.get("product_ref") or "CURRENT")
        fact["usage_task"] = str(fact.get("operation") or "")
        fact["scenario"] = str(fact.get("condition") or "")
        fact["certainty"] = str(fact.get("assertion") or "AFFIRMED")
