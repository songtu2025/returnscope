from types import SimpleNamespace

import pandas as pd
import pytest

from return_semantics.model_client import JsonlCache, ModelCallResult
from return_semantics.output_correction import correct_invalid_output
from return_semantics.pipeline import classify_comments
from return_semantics.schemas import (
    AssertionCode,
    ModelClassification,
    ProcessingStatus,
)


def classification(code="FIT_TOO_SMALL", evidence="Too small", sentiment="NEGATIVE"):
    return ModelClassification.model_validate(
        {
            "semantic_units": [
                {
                    "subject": "PRODUCT",
                    "label_code": code,
                    "opinion": "尺码偏小",
                    "sentiment": sentiment,
                    "assertion": "AFFIRMED",
                    "part": "WHOLE_SHOE",
                    "evidence": evidence,
                    "implicit": False,
                }
            ],
            "primary_label_codes": [code],
        }
    )


class CorrectionClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.messages = []
        self.settings = SimpleNamespace(
            model="test-model",
            cheap_model=None,
            max_workers=1,
            cache_namespace="test-correction",
        )

    def classify(self, messages, model=None, thinking=False):
        self.messages.append(messages)
        value = next(self.responses)
        if isinstance(value, Exception):
            raise value
        return ModelCallResult(value, model, {"input_tokens": 10}, {"attempts": 1})


def run(client, cache, taxonomy, claims, comment="Too small", **options):
    return classify_comments(
        pd.DataFrame(
            [
                {
                    "classification_key": "sample",
                    "comment_normalized": comment,
                    "reason": "",
                    "category_a": "水鞋",
                    "category_b": "水鞋",
                }
            ]
        ),
        taxonomy,
        claims,
        client,
        cache,
        **options,
    )


def test_repairs_invalid_code_once_and_caches_final_result(tmp_path, taxonomy, claims):
    client = CorrectionClient([classification("TYPO"), classification()])
    cache = JsonlCache(tmp_path / "cache.jsonl")
    first = run(client, cache, taxonomy, claims)
    assert first.classifications["sample"].status == ProcessingStatus.AUTO_APPROVED
    assert first.model_calls == 2
    assert first.usage["input_tokens"] == 20
    assert first.request_metrics["output_correction_successes"] == 1
    assert "未知标签" in client.messages[1][-1]["content"]
    assert "Too small" in client.messages[1][-2]["content"]
    second = run(client, cache, taxonomy, claims)
    assert len(client.messages) == 2
    assert second.cache_hits == 1
    assert second.model_calls == 0


@pytest.mark.parametrize(
    "retry",
    [classification("STILL_INVALID"), RuntimeError("failed"), ModelClassification()],
)
def test_failed_or_empty_correction_preserves_review(tmp_path, taxonomy, claims, retry):
    client = CorrectionClient([classification("TYPO"), retry])
    result = run(client, JsonlCache(tmp_path / "cache.jsonl"), taxonomy, claims)
    assert len(client.messages) == 2
    assert result.classifications["sample"].status != ProcessingStatus.AUTO_APPROVED
    assert any(
        "TYPO" in reason for reason in result.classifications["sample"].review_reasons
    )
    assert result.request_metrics["output_correction_failures"] == 1


def test_soft_uncertainty_does_not_trigger_correction(tmp_path, taxonomy, claims):
    payload = classification()
    payload.semantic_units[0].assertion = AssertionCode.UNCERTAIN
    payload.primary_label_codes = []
    client = CorrectionClient([payload])
    run(client, JsonlCache(tmp_path / "cache.jsonl"), taxonomy, claims)
    assert len(client.messages) == 1


def test_correction_cannot_drop_a_valid_opinion_with_shared_evidence(taxonomy, claims):
    original = classification("TYPO", "Too small but comfortable")
    comfort = classification(
        "EXPERIENCE_COMFORT", "Too small but comfortable", "POSITIVE"
    )
    original.semantic_units.extend(comfort.semantic_units)
    client = CorrectionClient([classification()])
    result = correct_invalid_output(
        ModelCallResult(original, "test", {}),
        comment="Too small but comfortable",
        messages=[],
        taxonomy=taxonomy,
        claims=claims,
        client=client,
        model_name="test",
        thinking=False,
    )
    assert result.metrics["output_correction_failures"] == 1
    assert result.classification.semantic_units == original.semantic_units


def test_cancellation_skips_correction_and_preserves_completed_usage(taxonomy, claims):
    original = ModelCallResult(classification("TYPO"), "test", {"input_tokens": 10})
    client = CorrectionClient([])
    result = correct_invalid_output(
        original,
        comment="Too small",
        messages=[],
        taxonomy=taxonomy,
        claims=claims,
        client=client,
        model_name="test",
        thinking=False,
        should_cancel=lambda: True,
    )
    assert result is original
    assert client.messages == []


@pytest.fixture
def footwear_taxonomy(taxonomy):
    return taxonomy.model_copy(
        update={
            "agent_family": "鞋履智能体",
            "recognition_profile": "semantic_v1",
            "version": "footwear-taxonomy-v6",
        }
    )


def test_footwear_restores_unique_evidence_without_extra_call(
    tmp_path, footwear_taxonomy, claims
):
    client = CorrectionClient([classification(evidence="too small")])
    result = run(client, JsonlCache(tmp_path / "shoe.jsonl"), footwear_taxonomy, claims)
    assert len(client.messages) == result.model_calls == 1
    assert result.classifications["sample"].semantic_units[0].evidence == "Too small"
    assert result.classifications["sample"].status == ProcessingStatus.AUTO_APPROVED


def test_footwear_deduplication_preserves_distinct_events(
    tmp_path, footwear_taxonomy, claims
):
    payload = classification()
    first = payload.semantic_units[0]
    payload.semantic_units += [
        first.model_copy(update={"opinion": "偏小"}),
        first.model_copy(
            update={"event_ref": "other", "condition": "with thick socks"}
        ),
    ]
    client = CorrectionClient([payload])
    result = run(client, JsonlCache(tmp_path / "shoe.jsonl"), footwear_taxonomy, claims)
    normalized = result.classifications["sample"]
    assert [unit.opinion for unit in normalized.semantic_units] == [
        "尺码偏小",
        "尺码偏小",
    ]
    assert normalized.semantic_units[-1].condition == "with thick socks"


@pytest.mark.parametrize("qualifies", [False, True])
def test_footwear_keeps_existing_review_without_targeting_omitted_fragments(
    tmp_path, footwear_taxonomy, claims, qualifies
):
    original = classification()
    original.needs_review = qualifies
    corrected = classification()
    corrected.semantic_units.extend(
        classification(
            "EXPERIENCE_COMFORT", "They felt comfortable", "POSITIVE"
        ).semantic_units
    )
    client = CorrectionClient([original, corrected])
    result = run(
        client,
        JsonlCache(tmp_path / "shoe.jsonl"),
        footwear_taxonomy,
        claims,
        "Too small. They felt comfortable.",
        secondary_model="risk-model",
    )
    assert len(client.messages) == result.model_calls == 1 + qualifies
    if qualifies:
        assert "鞋履首轮判定补充" in client.messages[0][0]["content"]
        assert client.messages[0][1:] == client.messages[1][1:]


def test_footwear_invalid_cheap_result_and_secondary_share_one_call(
    tmp_path, footwear_taxonomy, claims
):
    corrected = classification()
    corrected.needs_review = True
    client = CorrectionClient([classification("TYPO"), corrected])
    client.settings.cheap_model = "cheap"
    result = run(
        client,
        JsonlCache(tmp_path / "shoe.jsonl"),
        footwear_taxonomy,
        claims,
        secondary_model="risk-model",
    )
    assert len(client.messages) == result.model_calls == 2
    assert result.classifications["sample"].semantic_units == corrected.semantic_units


def test_footwear_output_repair_cannot_add_independent_opinions(
    tmp_path, footwear_taxonomy, claims
):
    original = classification("TYPO")
    corrected = classification()
    corrected.semantic_units.extend(
        classification(
            "EXPERIENCE_COMFORT", "They felt comfortable", "POSITIVE"
        ).semantic_units
    )
    client = CorrectionClient([original, corrected])
    result = run(
        client,
        JsonlCache(tmp_path / "shoe.jsonl"),
        footwear_taxonomy,
        claims,
        "Too small. They felt comfortable.",
    )
    validated = result.classifications["sample"]
    assert len(client.messages) == result.model_calls == 2
    assert "只修复错误单元" in client.messages[1][-1]["content"]
    assert validated.status == ProcessingStatus.MANUAL_REVIEW
    assert not validated.semantic_units


def test_footwear_cheap_failure_leaves_no_further_call(
    tmp_path, footwear_taxonomy, claims
):
    client = CorrectionClient([RuntimeError("failed"), classification("TYPO")])
    client.settings.cheap_model = "cheap"
    result = run(
        client,
        JsonlCache(tmp_path / "shoe.jsonl"),
        footwear_taxonomy,
        claims,
        secondary_model="risk-model",
    )
    assert len(client.messages) == 2
    assert result.classifications["sample"].status == ProcessingStatus.MANUAL_REVIEW


def test_footwear_existing_secondary_timeout_routes_to_rerun(
    tmp_path, footwear_taxonomy, claims
):
    original = classification()
    original.needs_review = True
    client = CorrectionClient([original, TimeoutError()])
    result = run(
        client,
        JsonlCache(tmp_path / "shoe.jsonl"),
        footwear_taxonomy,
        claims,
        "Too small. They felt comfortable.",
        secondary_model="risk-model",
    )
    validated = result.classifications["sample"]
    assert len(client.messages) == 2
    assert validated.semantic_units == original.semantic_units
    assert validated.review_diagnostics[-1].action == "SYSTEM_RERUN"
