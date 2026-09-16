import json
from collections import Counter
from pathlib import Path

import pytest

from return_semantics.schemas import ExtractedFact

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "fact_v2_model_risk_cases.json"
TAXONOMY_PATH = Path(__file__).parents[1] / "config" / "taxonomy_gloves.json"

CONTRACT = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
TAXONOMY = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
CASES = CONTRACT["cases"]
LABEL_CODES = {label["code"] for label in TAXONOMY["labels"]}
LABELS_BY_CODE = {label["code"]: label for label in TAXONOMY["labels"]}

TOP_LEVEL_FIELDS = {
    "schema_version",
    "data_origin",
    "target_profile",
    "taxonomy_version",
    "cases",
}
CASE_FIELDS = {
    "case_id",
    "risk_type",
    "comment",
    "expected_facts",
    "required_labels",
    "forbidden_labels",
    "expected_needs_review",
    "damage_level",
}
FACT_FIELDS = {
    "fact_id",
    "opinion",
    "sentiment",
    "statement_type",
    "fact_role",
    "evidence",
    "product_ref",
    "condition",
    "reference_basis",
    "required_label_code",
    "expected_disposition",
}
RISK_TYPES = {
    "MULTI_FACT_PRESERVATION",
    "CAPABILITY_WITH_LIMITATION",
    "NON_EVALUATIVE_CONTEXT",
    "LISTING_EXPECTATION_MISMATCH",
}
ALLOWED_DISPOSITIONS = {
    "EXPECTED_ABSTENTION",
    "EVIDENCE_ONLY",
    "OUT_OF_SCOPE",
    "TAXONOMY_GAP",
    "MAPPING_UNCERTAIN",
    None,
}
FORBIDDEN_IDENTIFIER_FIELDS = {
    "address",
    "asin",
    "customer_id",
    "customer_name",
    "email",
    "order_id",
    "order_number",
    "phone",
    "reviewer_id",
    "reviewer_name",
    "sku",
    "tracking_number",
}


def _field_names(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            field for child in value.values() for field in _field_names(child)
        }
    if isinstance(value, list):
        return {field for child in value for field in _field_names(child)}
    return set()


def _label_codes(case: dict) -> set[str]:
    return {
        fact["required_label_code"]
        for fact in case["expected_facts"]
        if fact["required_label_code"]
    }


def _validate_expected_fact(fact: dict) -> ExtractedFact:
    fact_payload = {
        key: value
        for key, value in fact.items()
        if key not in {"evidence", "required_label_code", "expected_disposition"}
    }
    return ExtractedFact.model_validate(
        {
            **fact_payload,
            "actor_ref": "REVIEWER",
            "source_ref": "REVIEWER",
            "experiencer_ref": "REVIEWER",
            "variant_ref": "UNSPECIFIED",
            "event_ref": "EVENT:1",
            "subject": "PRODUCT",
            "part": "UNSPECIFIED",
            "evidence_spans": [{"text": fact["evidence"]}],
        }
    )


def test_fixture_declares_expected_schema_and_synthetic_origin() -> None:
    assert set(CONTRACT) == TOP_LEVEL_FIELDS
    assert CONTRACT["schema_version"] == 1
    assert CONTRACT["data_origin"] == "synthetic"
    assert CONTRACT["target_profile"] == "fact_v2"
    assert CONTRACT["taxonomy_version"] == TAXONOMY["version"]
    assert not (_field_names(CONTRACT) & FORBIDDEN_IDENTIFIER_FIELDS)


def test_fixture_has_balanced_unique_ascii_cases() -> None:
    assert len(CASES) == 20
    assert Counter(case["risk_type"] for case in CASES) == Counter(
        {risk_type: 5 for risk_type in RISK_TYPES}
    )
    assert len({case["case_id"] for case in CASES}) == len(CASES)
    assert len({case["comment"] for case in CASES}) == len(CASES)
    assert all(case["comment"].isascii() for case in CASES)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["case_id"])
def test_case_schema_and_fact_contract(case: dict) -> None:
    assert set(case) == CASE_FIELDS
    assert case["risk_type"] in RISK_TYPES
    assert case["damage_level"] in {"HIGH", "MEDIUM"}
    assert isinstance(case["expected_needs_review"], bool)
    assert case["expected_facts"]
    assert len({fact["fact_id"] for fact in case["expected_facts"]}) == len(
        case["expected_facts"]
    )

    required_labels = set(case["required_labels"])
    forbidden_labels = set(case["forbidden_labels"])
    assert required_labels.isdisjoint(forbidden_labels)
    assert required_labels == _label_codes(case)
    assert required_labels | forbidden_labels <= LABEL_CODES

    for fact in case["expected_facts"]:
        assert set(fact) == FACT_FIELDS
        assert fact["evidence"]
        assert fact["evidence"] in case["comment"]
        assert fact["expected_disposition"] in ALLOWED_DISPOSITIONS
        _validate_expected_fact(fact)
        label_code = fact["required_label_code"]
        assert not label_code or label_code in LABEL_CODES
        if label_code:
            assert fact["expected_disposition"] is None
            assert fact["sentiment"] in LABELS_BY_CODE[label_code]["allowed_sentiments"]


@pytest.mark.parametrize(
    "case",
    [case for case in CASES if case["risk_type"] == "MULTI_FACT_PRESERVATION"],
    ids=lambda case: case["case_id"],
)
def test_multi_fact_cases_preserve_two_independent_dimensions(case: dict) -> None:
    labeled_facts = [
        fact for fact in case["expected_facts"] if fact["required_label_code"]
    ]
    assert len(labeled_facts) >= 2
    label_codes = _label_codes(case)
    assert "GLOVE_WARMTH_U1" in label_codes
    assert label_codes & {"GLOVE_BULK_WEIGHT_U1", "GLOVE_PORTABILITY_U1"}


@pytest.mark.parametrize(
    "case",
    [case for case in CASES if case["risk_type"] == "CAPABILITY_WITH_LIMITATION"],
    ids=lambda case: case["case_id"],
)
def test_capability_limit_cases_preserve_negative_touchscreen_fact(case: dict) -> None:
    assert "GLOVE_HAND_DEXTERITY_U1" in case["forbidden_labels"]
    assert any(
        fact["sentiment"] == "NEGATIVE"
        and fact["required_label_code"] == "GLOVE_TOUCHSCREEN_U1"
        for fact in case["expected_facts"]
    )


@pytest.mark.parametrize(
    "case",
    [case for case in CASES if case["risk_type"] == "NON_EVALUATIVE_CONTEXT"],
    ids=lambda case: case["case_id"],
)
def test_non_evaluative_cases_are_normal_abstentions(case: dict) -> None:
    assert case["required_labels"] == []
    assert case["expected_needs_review"] is False
    assert all(
        fact["expected_disposition"] in {"EXPECTED_ABSTENTION", "EVIDENCE_ONLY"}
        for fact in case["expected_facts"]
    )


@pytest.mark.parametrize(
    "case",
    [case for case in CASES if case["risk_type"] == "LISTING_EXPECTATION_MISMATCH"],
    ids=lambda case: case["case_id"],
)
def test_listing_mismatch_cases_use_the_most_specific_supported_label(
    case: dict,
) -> None:
    required = set(case["required_labels"])
    forbidden = set(case["forbidden_labels"])

    assert required in (
        {"GLOVE_EXPECTATION_MISMATCH_U1"},
        {"GLOVE_APPEARANCE_U1"},
    )
    assert {"GLOVE_COLOR_U1", "GLOVE_ORDER_WRONG_ITEM_U1"} <= forbidden
    if "GLOVE_EXPECTATION_MISMATCH_U1" in required:
        assert "GLOVE_APPEARANCE_U1" in forbidden
    else:
        assert "GLOVE_EXPECTATION_MISMATCH_U1" in forbidden
