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


def run(client, cache, taxonomy, claims):
    return classify_comments(
        pd.DataFrame(
            [
                {
                    "classification_key": "sample",
                    "comment_normalized": "Too small",
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
