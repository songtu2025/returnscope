from copy import deepcopy

import pytest

from web_backend.classification_reference_scope import (
    append_reference_scope,
    compare_reference_scope,
)
from web_backend.classification_validation_quality import (
    FACT_QUALITY_POLICY,
    quality_gate,
)


def _item():
    return {
        "reference": {
            "scope_complete": dict.fromkeys(
                ("event", "condition", "subject", "primary"), True
            ),
            "primary_label_codes": ["COLD"],
            "facts": [
                {
                    "label_codes": ["COLD"],
                    "expected_event_ref": "E1",
                    "expected_subject": "PRODUCT",
                    "expected_condition": ["45 F", "bike"],
                },
                {
                    "label_codes": ["COLD"],
                    "expected_event_ref": "E1",
                    "expected_subject": "PRODUCT",
                    "expected_condition": [],
                },
                {
                    "label_codes": ["SERVICE"],
                    "expected_event_ref": "E2",
                    "expected_subject": "SERVICE",
                    "expected_condition": [],
                },
            ],
        },
        "draft": {
            "primary_label_codes": ["COLD"],
            "extracted_facts": [
                {
                    "fact_id": "f1",
                    "is_primary_reason": True,
                    "event_ref": "ride",
                    "subject": "PRODUCT",
                    "condition": "BIKE ride at 45   F",
                },
                {"event_ref": "ride", "subject": "PRODUCT", "condition": ""},
                {"event_ref": "support", "subject": "SERVICE", "condition": ""},
            ],
            "fact_mappings": [{"fact_id": "f1", "label_codes": ["COLD"]}],
        },
    }


def test_scope_compares_relations_not_event_names_and_normalizes_conditions():
    counts = compare_reference_scope(_item(), "draft", {0: 0, 1: 1, 2: 2})
    assert counts == dict.fromkeys(
        ("event_errors", "condition_errors", "subject_errors", "primary_errors"), 0
    )


def test_no_required_condition_allows_other_retained_conditions():
    item = _item()
    parsed = append_reference_scope({}, {"条件": "无"}, "one", "COLD")
    item["reference"]["facts"][1].update(parsed)
    item["draft"]["extracted_facts"][1]["condition"] = "during the ride"
    assert (
        compare_reference_scope(item, "draft", {0: 0, 1: 1, 2: 2})["condition_errors"]
        == 0
    )
    item["draft"]["extracted_facts"][1]["condition"] = " \t\n "
    assert (
        compare_reference_scope(item, "draft", {0: 0, 1: 1, 2: 2})["condition_errors"]
        == 0
    )


@pytest.mark.parametrize("field", ["condition", "opinion", "evidence_spans"])
def test_required_conditions_may_be_retained_in_any_fact_text(field):
    item = _item()
    fact = item["draft"]["extracted_facts"][0]
    fact["condition"] = ""
    text = "A BIKE ride at 45   F"
    fact[field] = [{"text": text}] if field == "evidence_spans" else text
    assert compare_reference_scope(item, "draft", {0: 0})["condition_errors"] == 0


def test_required_phrases_can_be_retained_in_separate_fields():
    item = _item()
    fact = item["draft"]["extracted_facts"][0]
    fact.update(condition="bike", evidence_spans=[{"text": "at 45 F"}])
    assert compare_reference_scope(item, "draft", {0: 0})["condition_errors"] == 0
    fact["evidence_spans"] = [{"text": "at 50 F"}]
    assert compare_reference_scope(item, "draft", {0: 0})["condition_errors"] == 1


@pytest.mark.parametrize(
    "field,value,metric,count",
    [
        ("event_ref", "new_event", "event_errors", 2),
        ("condition", "bike", "condition_errors", 1),
        ("subject", "CUSTOMER", "subject_errors", 1),
    ],
)
def test_scope_detects_missing_condition_wrong_subject_and_split_event(
    field, value, metric, count
):
    item = _item()
    item["draft"]["extracted_facts"][0][field] = value
    assert compare_reference_scope(item, "draft", {0: 0, 1: 1, 2: 2})[metric] == count


def test_scope_detects_merged_independent_events_and_missing_primary():
    item = _item()
    item["draft"]["extracted_facts"][2]["event_ref"] = "ride"
    item["draft"]["primary_label_codes"] = []
    counts = compare_reference_scope(item, "draft", {0: 0, 1: 1, 2: 2})
    assert counts["event_errors"] == 3
    assert counts["primary_errors"] == 1


def test_primary_fact_and_final_labels_must_both_match_reference():
    item = _item()
    item["draft"]["extracted_facts"][0]["is_primary_reason"] = False
    assert compare_reference_scope(item, "draft", {0: 0})["primary_errors"] == 1
    item["draft"]["extracted_facts"][0]["is_primary_reason"] = True
    item["draft"]["fact_mappings"][0]["label_codes"] = ["OTHER"]
    assert compare_reference_scope(item, "draft", {0: 0})["primary_errors"] == 1


def test_event_errors_count_affected_facts_not_all_pair_combinations():
    item = _item()
    item["reference"]["facts"] = [
        {"expected_event_ref": "same", "label_codes": ["COLD"]} for _ in range(10)
    ]
    item["draft"]["extracted_facts"] = [{"event_ref": str(i)} for i in range(10)]
    counts = compare_reference_scope(item, "draft", dict(enumerate(range(10))))
    assert counts["event_errors"] == 10


def test_unmatched_fact_does_not_multiply_scope_errors():
    item = _item()
    counts = compare_reference_scope(item, "draft", {1: 1, 2: 2})
    assert (
        counts["subject_errors"]
        == counts["condition_errors"]
        == counts["event_errors"]
        == 0
    )


def test_parser_tracks_missing_columns_instead_of_claiming_evaluated():
    reference = {}
    assert append_reference_scope(reference, {}, "one", "COLD") == {}
    assert not any(reference["scope_complete"].values())
    parsed = append_reference_scope(
        {},
        {"事件": "E1", "条件": "45 F || bike", "责任主体": "PRODUCT", "是否主因": "是"},
        "one",
        "COLD",
    )
    assert parsed["expected_condition"] == ["45 F", "bike"]
    assert parsed["expected_event_ref"] == "E1"


@pytest.mark.parametrize(
    "row,code",
    [
        ({"责任主体": "seller"}, "COLD"),
        ({"是否主因": "unknown"}, "COLD"),
        ({"是否主因": "是"}, "无标签"),
    ],
)
def test_invalid_scope_fails_during_upload(row, code):
    with pytest.raises(ValueError):
        append_reference_scope({}, row, "one", code)


def test_v2_requires_scope_coverage_while_frozen_v1_stays_compatible():
    evaluation = {
        "sample_count": 20,
        "total_sample_count": 20,
        "fact_state_sample_count": 20,
        "sides": {"draft": dict.fromkeys(FACT_QUALITY_POLICY["thresholds"], 0)},
    }
    summary = {"reference_evaluation": evaluation}
    gate = quality_gate(summary, FACT_QUALITY_POLICY)
    assert not gate["passed"]
    assert len(gate["blocking"]) == 4
    legacy = deepcopy(FACT_QUALITY_POLICY)
    legacy.pop("require_scope_dimensions")
    legacy["version"] = "fact-reference-v1"
    assert quality_gate(summary, legacy)["passed"]
    evaluation["scope_sample_counts"] = dict.fromkeys(
        ("event", "condition", "subject", "primary"), 20
    )
    assert quality_gate(summary, FACT_QUALITY_POLICY)["passed"]


def test_background_event_cannot_create_business_relation_error():
    item = _item()
    item["reference"]["facts"][1]["label_codes"] = []
    item["draft"]["extracted_facts"][1].update(
        event_ref="background", subject="UNKNOWN"
    )
    counts = compare_reference_scope(item, "draft", {0: 0, 1: 1, 2: 2})
    assert counts["event_errors"] == counts["subject_errors"] == 0
