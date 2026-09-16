import copy
import json
from pathlib import Path

import pytest

from return_semantics.fact_pipeline import classify_facts
from return_semantics.model_client import JsonModelCallResult
from return_semantics.schemas import ListingClaimsConfig, TaxonomyConfig
from return_semantics.validator import validate_classification

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "fact_v2_stage_replay.json"
CONTRACT = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
CASES = CONTRACT["cases"]
ALL_STAGES = {
    "extraction",
    "coverage_audit",
    "mapping",
    "evidence_adjudication",
    "dimension_decision",
}
REQUIRED_RISKS = {
    "warmth_and_lightweight_preserved",
    "touchscreen_precision_limit_preserved",
    "non_evaluative_context_does_not_become_business_unknown",
    "expectation_mismatch_not_rewritten_as_preference",
}


def _taxonomy() -> TaxonomyConfig:
    return TaxonomyConfig.model_validate(
        {
            "version": "fact-v2-stage-replay-v1",
            "structure_version": 2,
            "recognition_profile": "fact_v2",
            "agent_family": "synthetic-stage-replay",
            "product_context": "synthetic gloves",
            "categories": [
                {"code": "THERMAL", "name": "Thermal performance"},
                {"code": "WEIGHT", "name": "Weight"},
                {"code": "TOUCHSCREEN", "name": "Touchscreen performance"},
                {"code": "EXPECTATION", "name": "Listing expectation"},
            ],
            "validation_rules": {
                "dimension_contracts": [
                    {
                        "parent_code": "THERMAL",
                        "verdict_label_codes": ["WARM_POSITIVE"],
                        "scope_fields": ["product_ref", "condition"],
                    },
                    {
                        "parent_code": "WEIGHT",
                        "verdict_label_codes": ["LIGHTWEIGHT_POSITIVE"],
                        "scope_fields": ["product_ref", "condition"],
                    },
                    {
                        "parent_code": "TOUCHSCREEN",
                        "verdict_label_codes": [
                            "TOUCH_USABLE_POSITIVE",
                            "TOUCH_IMPRECISE_NEGATIVE",
                        ],
                        "scope_fields": ["product_ref"],
                    },
                    {
                        "parent_code": "EXPECTATION",
                        "verdict_label_codes": [
                            "EXPECTATION_MISMATCH_NEGATIVE",
                            "COLOR_DISLIKE_NEGATIVE",
                        ],
                        "scope_fields": ["product_ref", "reference_basis"],
                    },
                ]
            },
            "labels": [
                {
                    "code": "WARM_POSITIVE",
                    "name": "Warm",
                    "parent_code": "THERMAL",
                    "allowed_sentiments": ["POSITIVE"],
                },
                {
                    "code": "LIGHTWEIGHT_POSITIVE",
                    "name": "Lightweight",
                    "parent_code": "WEIGHT",
                    "allowed_sentiments": ["POSITIVE"],
                },
                {
                    "code": "TOUCH_USABLE_POSITIVE",
                    "name": "Touch input usable",
                    "parent_code": "TOUCHSCREEN",
                    "allowed_sentiments": ["POSITIVE"],
                },
                {
                    "code": "TOUCH_IMPRECISE_NEGATIVE",
                    "name": "Touch input imprecise",
                    "parent_code": "TOUCHSCREEN",
                    "allowed_sentiments": ["NEGATIVE"],
                },
                {
                    "code": "EXPECTATION_MISMATCH_NEGATIVE",
                    "name": "Item differs from listing image",
                    "parent_code": "EXPECTATION",
                    "allowed_sentiments": ["NEGATIVE"],
                },
                {
                    "code": "COLOR_DISLIKE_NEGATIVE",
                    "name": "Subjective color dislike",
                    "parent_code": "EXPECTATION",
                    "allowed_sentiments": ["NEGATIVE"],
                },
            ],
        }
    )


def _stage_name(payload: dict) -> str:
    if "existing_facts" in payload:
        return "coverage_audit"
    if "current_mappings" in payload:
        return "evidence_adjudication"
    if "contracts" in payload and "mappings" in payload:
        return "dimension_decision"
    if "allowed_labels_by_fact" in payload:
        return "mapping"
    return "extraction"


class ScriptedJsonClient:
    """按 fixture 顺序回放模型阶段，并保留每阶段的真实输入。"""

    def __init__(self, case: dict) -> None:
        self.case = case
        self.calls: list[str] = []
        self.payloads: dict[str, dict] = {}

    def generate_json(self, messages, **_kwargs) -> JsonModelCallResult:
        payload = json.loads(messages[1]["content"])
        stage = _stage_name(payload)
        expected_stage = self.case["expected"]["call_stages"][len(self.calls)]
        assert stage == expected_stage
        response = self.case["stages"][stage]
        assert response is not None
        self.calls.append(stage)
        self.payloads[stage] = payload
        return JsonModelCallResult(
            payload=copy.deepcopy(response),
            model_name="offline-stage-replay",
            usage={"total_tokens": 1},
            metrics={"attempts": 1},
        )


def _ids(items: list[dict]) -> list[str]:
    return [item["fact_id"] for item in items]


def _assert_stage_inputs(client: ScriptedJsonClient, case: dict) -> None:
    expected = case["expected"]
    extraction_payload = client.payloads["extraction"]
    assert extraction_payload["comment"] == case["comment"]
    assert "labels" not in extraction_payload

    primary_ids = _ids(case["stages"]["extraction"]["facts"])
    coverage_payload = client.payloads["coverage_audit"]
    assert _ids(coverage_payload["existing_facts"]) == primary_ids

    mapping_payload = client.payloads["mapping"]
    assert _ids(mapping_payload["facts"]) == expected["fact_ids"]
    assert set(mapping_payload["allowed_labels_by_fact"]) == set(expected["fact_ids"])

    if "evidence_adjudication" in client.payloads:
        adjudication_payload = client.payloads["evidence_adjudication"]
        assert _ids(adjudication_payload["facts"]) == expected["adjudication_fact_ids"]
    else:
        assert expected["adjudication_fact_ids"] == []

    decision_payload = client.payloads["dimension_decision"]
    assert _ids(decision_payload["facts"]) == expected["fact_ids"]
    assert _ids(decision_payload["mappings"]) == expected["fact_ids"]


def test_fixture_declares_complete_synthetic_stage_contract() -> None:
    assert CONTRACT["data_origin"] == "synthetic"
    assert set(CONTRACT["stages"]) == ALL_STAGES
    assert {case["risk"] for case in CASES} == REQUIRED_RISKS
    assert all(case["comment"].isascii() for case in CASES)
    assert all(set(case["stages"]) == ALL_STAGES for case in CASES)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_fact_v2_stage_replay_preserves_structured_semantics(case: dict) -> None:
    taxonomy = _taxonomy()
    client = ScriptedJsonClient(case)

    result = classify_facts(
        comment=case["comment"],
        taxonomy=taxonomy,
        client=client,
        model_name="offline-stage-replay",
        reasoning_effort="low",
    )
    classification = result.classification
    expected = case["expected"]

    assert client.calls == expected["call_stages"]
    assert result.metrics["fact_model_calls"] == len(expected["call_stages"])
    assert result.usage["total_tokens"] == len(expected["call_stages"])
    _assert_stage_inputs(client, case)

    facts_by_id = {fact.fact_id: fact for fact in classification.extracted_facts}
    assert list(facts_by_id) == expected["fact_ids"]
    assert {
        fact_id: fact.extraction_source.value for fact_id, fact in facts_by_id.items()
    } == expected["extraction_sources"]

    expected_opinions = {
        fact["fact_id"]: fact["opinion"]
        for stage in ("extraction", "coverage_audit")
        for fact in (case["stages"][stage] or {"facts": []})["facts"]
    }
    assert {
        fact_id: fact.opinion for fact_id, fact in facts_by_id.items()
    } == expected_opinions

    actual_units = [
        {
            "label_code": unit.label_code,
            "fact_ids": unit.fact_ids,
            "opinion": unit.opinion,
            "evidence": unit.evidence,
        }
        for unit in classification.semantic_units
    ]
    assert actual_units == expected["final_units"]
    assert {
        item.fact_id: item.disposition.value
        for item in classification.unknown_semantics
        if item.fact_id is not None
    } == expected["dispositions"]

    validated = validate_classification(
        classification_key=case["id"],
        comment=case["comment"],
        reason="",
        model_result=classification,
        taxonomy=taxonomy,
        claims=ListingClaimsConfig(version="none", claims=[]),
        model_name="offline-stage-replay",
        prompt_version="fact-v2-stage-replay-v1",
        analysis_context="review",
    )
    assert validated.status.value == expected["status"]


def test_listing_mismatch_never_becomes_subjective_color_dislike() -> None:
    case = next(
        item
        for item in CASES
        if item["risk"] == "expectation_mismatch_not_rewritten_as_preference"
    )
    result = classify_facts(
        comment=case["comment"],
        taxonomy=_taxonomy(),
        client=ScriptedJsonClient(case),
        model_name="offline-stage-replay",
        reasoning_effort="low",
    ).classification

    assert [unit.label_code for unit in result.semantic_units] == [
        "EXPECTATION_MISMATCH_NEGATIVE"
    ]
    assert "listing image" in result.semantic_units[0].opinion
    assert "color dislike" not in result.semantic_units[0].opinion.lower()
