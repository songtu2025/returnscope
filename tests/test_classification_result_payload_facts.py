from __future__ import annotations

from copy import deepcopy

import pytest

from return_semantics.schemas import TaxonomyConfig
from web_backend import classification_result_payload as payloads
from web_backend import classification_result_service as services
from web_backend.classification_results.payload_facts import (
    _fact_id_by_label,
    _normalize_semantic_facts,
    add_api_fact_fields,
)


def test_fact_association_keeps_unique_mapping_and_explicit_identity() -> None:
    payload = {
        "extracted_facts": [
            {"fact_id": "F1", "actor_ref": "SOURCE", "product_ref": "CURRENT"},
            {"fact_id": "F2", "actor_ref": "OTHER"},
        ],
        "fact_mappings": [
            {"fact_id": " F1 ", "label_codes": ["A"]},
            {"fact_id": "F1", "label_codes": ["A", "B"]},
            {"fact_id": "F2", "label_codes": ["B"]},
            {"fact_id": "", "label_codes": ["C"]},
            "旧格式占位",
        ],
        "semantic_units": [
            {"label_code": "A", "actor_ref": "KEEP", "product_ref": "UNSPECIFIED"},
            {"label_code": "B"},
            {"label_code": "A", "fact_id": "F2"},
            "旧格式占位",
        ],
    }
    before = deepcopy(payload)
    assert _fact_id_by_label(payload) == {"A": "F1"}
    units = _normalize_semantic_facts(payload, None)
    assert [unit["fact_id"] for unit in units] == ["F1", None, "F2"]
    assert [unit["label_code"] for unit in units] == ["A", "B", "A"]
    assert units[0]["actor_ref"] == "KEEP"
    assert units[0]["product_ref"] == "CURRENT"
    assert units[2]["actor_ref"] == "OTHER"
    assert payload == before


@pytest.mark.parametrize("value", [None, "", "UNSPECIFIED"])
def test_fact_context_fills_missing_fields_without_replacing_existing_values(
    value: str | None,
) -> None:
    payload = {
        "extracted_facts": [
            {
                "fact_id": "F1",
                "event_ref": "E1",
                "condition": {"source": "合成场景"},
                "evidence_source": "BODY",
            }
        ],
        "semantic_units": [
            {
                "fact_id": "F1",
                "event_ref": value,
                "condition": value,
                "decision_reason": "保留明确说明",
            }
        ],
    }
    before = deepcopy(payload)
    unit = _normalize_semantic_facts(payload, None)[0]
    assert unit["event_ref"] == "E1"
    assert unit["condition"] == {"source": "合成场景"}
    assert unit["evidence_source"] == "BODY"
    assert unit["decision_reason"] == "保留明确说明"
    assert unit["context_fact_ids"] == []
    assert unit["fact_role"] == "CONCLUSION"
    assert payload == before


def test_fact_paths_use_taxonomy_and_preserve_legacy_paths(
    taxonomy: TaxonomyConfig,
) -> None:
    label = taxonomy.labels[0]
    payload = {
        "semantic_units": [
            {"label_code": label.code, "label_path": ["旧路径"]},
        ]
    }
    assert _normalize_semantic_facts(payload, None)[0]["label_path"] == ["旧路径"]
    unit = _normalize_semantic_facts(payload, taxonomy)[0]
    assert unit["label_code_path"] == [label.code]
    assert unit["label_path"] == [label.group, label.name]
    assert payload["semantic_units"][0]["label_path"] == ["旧路径"]


def test_api_fact_aliases_keep_defaults_and_string_conversion() -> None:
    facts = [{"opinion": "合成观点", "condition": {"phase": "合成场景"}}, {}]
    add_api_fact_fields(facts)
    assert facts[0]["fact_text_zh"] == "合成观点"
    assert facts[0]["scenario"] == "{'phase': '合成场景'}"
    assert {
        key: facts[1][key]
        for key in (
            "fact_text_zh",
            "original_evidence",
            "object_ref",
            "usage_task",
            "scenario",
            "certainty",
        )
    } == {
        "fact_text_zh": "",
        "original_evidence": "",
        "object_ref": "CURRENT",
        "usage_task": "",
        "scenario": "",
        "certainty": "AFFIRMED",
    }


@pytest.mark.parametrize("include_api_fields", [False, True])
def test_persisted_payload_excludes_api_aliases_and_keeps_source(
    include_api_fields: bool,
) -> None:
    source = {"semantic_units": [{"label_code": "A", "opinion": "合成观点"}]}
    before = deepcopy(source)
    value = payloads._prepare_classification_payload(
        source, None, "AUTO_APPROVED", include_api_fields=include_api_fields
    )
    assert ("atomic_facts" in value) is include_api_fields
    assert ("fact_text_zh" in value["semantic_units"][0]) is include_api_fields
    assert source == before


def test_existing_payload_and_service_entry_points_use_shared_implementation() -> None:
    assert payloads._fact_id_by_label is _fact_id_by_label
    assert payloads._normalize_semantic_facts is _normalize_semantic_facts
    assert services._fact_id_by_label is _fact_id_by_label
    assert services._normalize_semantic_facts is _normalize_semantic_facts
