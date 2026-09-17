import json
from collections import Counter
from pathlib import Path

import pytest

from web_backend.classification_validation_quality import (
    ERROR_METRICS,
    FACT_QUALITY_POLICY,
    METRIC_LABELS,
    quality_gate,
)

FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "winter_gloves_review_holdout20_r14_v24.json"
)
FIXTURE = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
CASES = FIXTURE["cases"]
HOLDOUT_IDS = frozenset(case["review_id"] for case in CASES)
REQUIRED_FIELDS = {
    "sequence",
    "review_id",
    "source_row",
    "model_status",
    "human_verdict",
    "label_resolution",
    "review_note",
    "diagnostics",
}


def _quality_summary(metric: str) -> dict:
    values = dict.fromkeys(ERROR_METRICS, 0)
    values.update(
        {
            metric: 1,
            "expected_instances": 20,
            "actual_instances": 20,
            "matched_instances": 20,
            "duplicate_samples": 0,
        }
    )
    return {
        "sample_size": 20,
        "reference_evaluation": {
            "sample_count": 20,
            "total_sample_count": 20,
            "fact_state_sample_count": 20,
            "scope_sample_counts": {
                dimension: 20
                for dimension in FACT_QUALITY_POLICY["warn_incomplete_scope_dimensions"]
            },
            "sides": {"draft": values},
        },
    }


def test_holdout_fixture_contains_20_unique_complete_results() -> None:
    assert len(CASES) == 20
    assert [case["sequence"] for case in CASES] == list(range(1, 21))
    assert len(HOLDOUT_IDS) == 20
    assert len({case["source_row"] for case in CASES}) == 20
    assert all(REQUIRED_FIELDS == case.keys() for case in CASES)
    assert all(case["review_id"] for case in CASES)
    assert all(case["model_status"] for case in CASES)
    assert all(case["human_verdict"] for case in CASES)


def test_blind_input_contract_preserves_verified_population_counts() -> None:
    contract = FIXTURE["blind_input_contract"]
    assert contract["exclusion_key"] == "review_id"
    assert contract["source_review_count"] == 344
    assert contract["verified_holdout_overlap_count"] == 20
    assert contract["verified_holdout_overlap_count"] == len(HOLDOUT_IDS)
    assert contract["expected_blind_review_count"] == 324
    assert (
        contract["source_review_count"] - contract["verified_holdout_overlap_count"]
        == contract["expected_blind_review_count"]
    )


def test_blind_sample_contains_50_unique_non_holdout_reviews() -> None:
    contract = FIXTURE["blind_sample_contract"]
    blind_sample_ids = contract["review_ids"]

    assert contract["source_file"] == "winter_gloves_input_blind50_v1.json"
    assert contract["count"] == 50
    assert (
        contract["sha256"]
        == "35547BDFFD14A2D9AF9C41D087C1234B9067374241ED49C271BCA4C39894802F"
    )
    assert len(blind_sample_ids) == contract["count"]
    assert len(set(blind_sample_ids)) == contract["count"]
    assert set(blind_sample_ids).isdisjoint(HOLDOUT_IDS)


def test_holdout_fixture_preserves_human_verdict_distribution() -> None:
    expected = Counter({"正确": 12, "部分正确": 7, "错误": 1})

    assert Counter(FIXTURE["expected_verdict_counts"]) == expected
    assert Counter(case["human_verdict"] for case in CASES) == expected


def test_correct_results_can_record_supplemental_labels() -> None:
    supplemental = [
        case
        for case in CASES
        if case["human_verdict"] == "正确"
        and "missing_secondary_label" in case["diagnostics"]
    ]

    assert len(supplemental) == 3
    assert all("补充" in case["label_resolution"] for case in supplemental)


def test_review_diagnostics_do_not_override_human_verdicts() -> None:
    diagnostic_cases = [
        case
        for case in CASES
        if {"primary_reason_difference", "missing_secondary_label"}
        & set(case["diagnostics"])
    ]

    assert diagnostic_cases
    assert all(case["human_verdict"] != "错误" for case in diagnostic_cases)


@pytest.mark.parametrize("metric", ["primary_errors", "missing_labels"])
def test_review_only_quality_differences_do_not_block_publication(metric: str) -> None:
    result = quality_gate(_quality_summary(metric), FACT_QUALITY_POLICY)

    assert result["passed"] is True
    assert result["blocking"] == []
    assert any(METRIC_LABELS[metric] in warning for warning in result["warnings"])
