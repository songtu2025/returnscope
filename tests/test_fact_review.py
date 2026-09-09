import json

import pytest

from return_semantics import prompt
from return_semantics.review import (
    classifications_match,
    reconcile_secondary,
    should_run_secondary,
)
from return_semantics.schemas import ExtractedFact, FactMapping, ValidatedClassification


def result_with_fact(**updates):
    fact = ExtractedFact.model_validate(
        {
            "fact_id": "a",
            "actor_ref": "REVIEWER",
            "product_ref": "CURRENT",
            "event_ref": "event",
            "subject": "PRODUCT",
            "statement_type": "EXPERIENCE",
            "opinion": "实际评价",
            "sentiment": "POSITIVE",
            "part": "UNSPECIFIED",
            "condition": "",
            "evidence_spans": [{"text": "This worked well."}],
            **updates,
        }
    )
    return ValidatedClassification.model_validate(
        {
            "classification_key": "test",
            "semantic_units": [],
            "unknown_semantics": [],
            "problem_label_codes": [],
            "positive_label_codes": [],
            "primary_label_codes": [],
            "status": "SECONDARY_REVIEW",
            "review_reasons": [],
            "model_name": "fake",
            "prompt_version": "fact-test",
            "taxonomy_version": "test",
            "extracted_facts": [fact.model_dump(mode="json")],
            "fact_mappings": [{"fact_id": fact.fact_id, "label_codes": []}],
        }
    )


@pytest.mark.parametrize(
    "change",
    [
        {"actor_ref": "OTHER:1"},
        {"product_ref": "CURRENT:1"},
        {"statement_type": "PREDICTION"},
        {"condition": "仅首次"},
        {"is_primary_reason": True},
    ],
)
def test_same_labels_do_not_hide_fact_disagreement(change):
    first = result_with_fact()
    second = result_with_fact(**change)
    assert not classifications_match(first, second)
    assert reconcile_secondary(first, second).status == "MANUAL_REVIEW"


def test_model_generated_identifiers_do_not_create_false_disagreement():
    assert classifications_match(
        result_with_fact(), result_with_fact(fact_id="another", event_ref="renamed")
    )


def test_event_partition_difference_requires_review():
    first = result_with_fact()
    another = first.extracted_facts[0].model_copy(update={"fact_id": "b"})
    first.extracted_facts.append(another)
    first.fact_mappings.append(FactMapping(fact_id="b"))
    second = first.model_copy(deep=True)
    second.extracted_facts[1].event_ref = "different_event"
    assert not classifications_match(first, second)


@pytest.mark.parametrize(
    "reason",
    [
        "待确认事实 a: PREDICTION",
        "fact_v2尚未完成Listing承诺关系核验，需人工确认；未推断承诺关系",
    ],
)
def test_model_agreement_cannot_remove_unresolved_fact_review(reason):
    first = result_with_fact()
    first.review_reasons = [reason]
    second = first.model_copy(deep=True)
    assert not should_run_secondary(first)
    result = reconcile_secondary(first, second)
    assert result.status == "MANUAL_REVIEW"
    assert reason in result.review_reasons


def test_legacy_without_fact_trace_keeps_existing_agreement_behavior():
    first = result_with_fact()
    first.extracted_facts = []
    first.fact_mappings = []
    assert reconcile_secondary(first, first).status == "AUTO_APPROVED"


@pytest.mark.parametrize(
    "profile,version",
    [
        ("legacy_v3", "evidence-validator-v1"),
        ("semantic_v1", "evidence-validator-v2"),
        ("fact_v2", "evidence-fact-validator-v3"),
    ],
)
def test_review_contract_version_isolated_to_fact_profile(
    taxonomy, monkeypatch, profile, version
):
    candidate = taxonomy.model_copy(update={"recognition_profile": profile})
    captured = []
    sha256 = prompt.hashlib.sha256

    def capture(payload):
        captured.append(json.loads(payload))
        return sha256(payload)

    monkeypatch.setattr(prompt.hashlib, "sha256", capture)
    prompt.recognition_fingerprint(candidate)
    assert captured[0]["validator_version"] == version
