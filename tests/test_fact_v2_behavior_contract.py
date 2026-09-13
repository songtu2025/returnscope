import json
from pathlib import Path

import pytest

from return_semantics.fact_pipeline import FactMappings, compile_fact_classification
from return_semantics.schemas import (
    ExtractedFact,
    FactMapping,
    ListingClaimsConfig,
    TaxonomyConfig,
)
from return_semantics.validator import validate_classification

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "fact_v2_behavior_contract.json"
CONTRACT = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
CASES = CONTRACT["cases"]
REQUIRED_CONTRACTS = {
    "fact_preservation",
    "label_direction",
    "applicability_scope",
    "evidence_traceability",
    "unknown_review_routing",
}


def _taxonomy() -> TaxonomyConfig:
    labels = [
        ("WARM_POSITIVE", "Warm", ["POSITIVE"]),
        ("WARM_NEGATIVE", "Not warm", ["NEGATIVE"]),
        ("LIGHTWEIGHT_POSITIVE", "Lightweight", ["POSITIVE"]),
        ("TOUCH_USABLE_POSITIVE", "Touch input usable", ["POSITIVE"]),
        ("TOUCH_IMPRECISE_NEGATIVE", "Touch input imprecise", ["NEGATIVE"]),
        ("FLEXIBLE_POSITIVE", "Flexible", ["POSITIVE"]),
        ("WATER_RESISTANT_POSITIVE", "Water resistant", ["POSITIVE"]),
        ("FIT_AS_EXPECTED", "Fit as expected", ["NEUTRAL"]),
    ]
    return TaxonomyConfig.model_validate(
        {
            "version": "fact-v2-behavior-contract-v1",
            "recognition_profile": "fact_v2",
            "agent_family": "synthetic-test",
            "product_context": "synthetic gloves",
            "labels": [
                {
                    "code": code,
                    "name": name,
                    "group": "contract",
                    "allowed_sentiments": sentiments,
                }
                for code, name, sentiments in labels
            ],
        }
    )


def _fact(payload: dict) -> ExtractedFact:
    defaults = {
        "actor_ref": "REVIEWER",
        "source_ref": "REVIEWER",
        "experiencer_ref": "REVIEWER",
        "product_ref": "CURRENT",
        "variant_ref": "UNSPECIFIED",
        "event_ref": "EVENT:1",
        "reference_basis": "NONE",
        "fact_role": "CONCLUSION",
        "subject": "PRODUCT",
        "assertion": "AFFIRMED",
        "specificity": "SPECIFIC",
        "experiencer_resolution": "EXPLICIT",
        "part": "UNSPECIFIED",
        "operation": "",
        "condition": "",
        "candidate_branch_codes": [],
    }
    fact_fields = {
        key: value
        for key, value in payload.items()
        if key
        not in {
            "allowed_label_codes",
            "mapping",
            "expected",
        }
    }
    fact_fields["evidence_spans"] = [
        {"text": text} for text in fact_fields["evidence_spans"]
    ]
    return ExtractedFact.model_validate({**defaults, **fact_fields})


def _mapping(payload: dict) -> FactMapping:
    return FactMapping.model_validate(
        {
            "fact_id": payload["fact_id"],
            **payload["mapping"],
        }
    )


def _compile(case: dict):
    taxonomy = _taxonomy()
    facts = [_fact(item) for item in case["facts"]]
    mappings = [_mapping(item) for item in case["facts"]]
    compiled = compile_fact_classification(
        facts,
        FactMappings(mappings=mappings),
        comment=case["comment"],
        taxonomy=taxonomy,
        allowed={
            item["fact_id"]: item["allowed_label_codes"] for item in case["facts"]
        },
    )
    validated = validate_classification(
        classification_key=case["id"],
        comment=case["comment"],
        reason="",
        model_result=compiled,
        taxonomy=taxonomy,
        claims=ListingClaimsConfig(version="none", claims=[]),
        model_name="offline-fixture",
        prompt_version="fact-v2-behavior-contract-v1",
        analysis_context="review",
    )
    return facts, compiled, validated


def test_fixture_declares_synthetic_contract_coverage() -> None:
    assert CONTRACT["data_origin"] == "synthetic"
    assert all(case["comment"].isascii() for case in CASES)
    covered = {name for case in CASES for name in case["contracts"]}
    assert REQUIRED_CONTRACTS <= covered


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_fact_v2_behavior_contract(case: dict) -> None:
    facts, compiled, validated = _compile(case)

    assert compiled.extracted_facts == facts
    assert validated.extracted_facts == facts
    terminal_by_fact = {
        fact_id: unit for unit in validated.semantic_units for fact_id in unit.fact_ids
    }
    unknown_by_fact = {
        item.fact_id: item
        for item in validated.unknown_semantics
        if item.fact_id is not None
    }
    assert set(terminal_by_fact).isdisjoint(unknown_by_fact)
    assert set(terminal_by_fact) | set(unknown_by_fact) == {
        fact.fact_id for fact in facts
    }

    labels = {label.code: label for label in _taxonomy().labels}
    for item in case["facts"]:
        expected = item["expected"]
        if expected["outcome"] == "TERMINAL":
            outcome = terminal_by_fact[item["fact_id"]]
            assert outcome.label_code == expected["label_code"]
            assert outcome.sentiment in labels[outcome.label_code].allowed_sentiments
        else:
            outcome = unknown_by_fact[item["fact_id"]]
            assert outcome.disposition.value == expected["disposition"]
        assert outcome.evidence == expected["evidence"]
        assert outcome.evidence in case["comment"]
        for field_name, value in expected.get("scope", {}).items():
            actual = getattr(outcome, field_name)
            assert getattr(actual, "value", actual) == value

    assert compiled.needs_review is case["expected"]["needs_review"]
    assert validated.status.value == case["expected"]["status"]


@pytest.mark.parametrize(
    "case",
    [case for case in CASES if "direction_guard" in case],
    ids=lambda case: case["id"],
)
def test_fact_v2_rejects_direction_incompatible_label(case: dict) -> None:
    taxonomy = _taxonomy()
    guard = case["direction_guard"]
    facts = [_fact(item) for item in case["facts"]]
    mappings = []
    for item in case["facts"]:
        mapping = _mapping(item)
        if item["fact_id"] == guard["fact_id"]:
            mapping = mapping.model_copy(
                update={"label_codes": [guard["rejected_label_code"]]}
            )
        mappings.append(mapping)

    with pytest.raises(ValueError, match=guard["error"]):
        compile_fact_classification(
            facts,
            FactMappings(mappings=mappings),
            comment=case["comment"],
            taxonomy=taxonomy,
            allowed={
                item["fact_id"]: item["allowed_label_codes"] for item in case["facts"]
            },
        )
