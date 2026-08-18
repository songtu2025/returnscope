from types import SimpleNamespace

import pandas as pd
import pytest

from return_semantics.model_client import JsonlCache, ModelCallResult, ModelHTTPError
from return_semantics.pipeline import (
    ModelServiceUnavailable,
    PipelineCancelled,
    classify_comments,
    has_input_semantic_risk,
)
from return_semantics.schemas import ModelClassification


def _classification(
    label_code: str = "FIT_TOO_SMALL",
    evidence: str = "Too small",
    needs_review: bool = False,
) -> ModelClassification:
    return ModelClassification.model_validate(
        {
            "semantic_units": [
                {
                    "subject": "PRODUCT",
                    "label_code": label_code,
                    "opinion": "尺码问题",
                    "sentiment": "NEGATIVE",
                    "assertion": "AFFIRMED",
                    "part": "WHOLE_SHOE",
                    "evidence": evidence,
                    "implicit": False,
                    "claim_relation": "NONE",
                    "claim_id": None,
                }
            ],
            "unknown_semantics": [],
            "primary_label_codes": [label_code],
            "needs_review": needs_review,
            "review_reasons": [],
        }
    )


def _multi_issue_classification() -> ModelClassification:
    classification = _classification(evidence="Uncomfortable")
    discomfort = classification.semantic_units[0].model_copy(
        update={"label_code": "EXPERIENCE_DISCOMFORT"}
    )
    return classification.model_copy(
        update={
            "semantic_units": [
                classification.semantic_units[0],
                discomfort,
            ]
        }
    )


class FakeClient:
    def __init__(
        self,
        responses: dict[str, ModelClassification],
        audit_percent: int = 0,
        max_workers: int = 1,
    ) -> None:
        self.settings = SimpleNamespace(
            model="gpt-5.5",
            secondary_model="gpt-5.6-sol",
            cheap_model="gpt-5.4-mini",
            cheap_model_audit_percent=audit_percent,
            max_workers=max_workers,
            provider="sub2api",
            cache_namespace="test-sub2api",
        )
        self.responses = responses
        self.calls: list[str] = []

    def classify(
        self,
        messages,
        model=None,
        thinking=False,
    ) -> ModelCallResult:
        model_name = model or self.settings.model
        self.calls.append(model_name)
        return ModelCallResult(
            classification=self.responses[model_name],
            model_name=model_name,
            usage={"input_tokens": 10, "output_tokens": 2},
            metrics={"attempts": 1, "retries": 0, "latency_ms": 5},
        )


class UnavailableClient:
    def __init__(self) -> None:
        self.settings = SimpleNamespace(
            model="gpt-5.5",
            cheap_model=None,
            cheap_model_audit_percent=0,
            max_workers=1,
            cache_namespace="test-unavailable",
        )
        self.calls = 0

    def classify(self, messages, model=None, thinking=False) -> ModelCallResult:
        self.calls += 1
        http_error = ModelHTTPError("Sub2API", 503, "Service unavailable")
        raise RuntimeError(f"Sub2API 调用失败: {http_error}") from http_error


def _comments(
    comment: str,
    reason: str = "APPAREL_TOO_SMALL",
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "classification_key": f"{reason}\x1f{comment.lower()}",
                "reason": reason,
                "comment_normalized": comment,
            }
        ]
    )


def test_low_risk_comment_uses_cheap_model(
    tmp_path,
    taxonomy,
    claims,
) -> None:
    client = FakeClient(
        {"gpt-5.4-mini": _classification()},
        audit_percent=0,
    )

    run = classify_comments(
        unique_comments=_comments("Too small"),
        taxonomy=taxonomy,
        claims=claims,
        client=client,
        cache=JsonlCache(tmp_path / "cache.jsonl"),
    )

    assert client.calls == ["gpt-5.4-mini"]
    assert run.model_calls_by_model == {"gpt-5.4-mini": 1}
    assert run.routing == {
        "cheap_first_pass": 1,
        "cheap_result_accepted": 1,
    }
    assert run.request_metrics["attempts"] == 1


def test_input_semantic_risk_uses_primary_model(
    tmp_path,
    taxonomy,
    claims,
) -> None:
    client = FakeClient(
        {
            "gpt-5.5": _classification(evidence="Too small"),
        }
    )

    run = classify_comments(
        unique_comments=_comments("Too small but uncomfortable"),
        taxonomy=taxonomy,
        claims=claims,
        client=client,
        cache=JsonlCache(tmp_path / "cache.jsonl"),
    )

    assert client.calls == ["gpt-5.5"]
    assert run.model_calls_by_model == {"gpt-5.5": 1}
    assert run.routing == {"input_risk_primary": 1}


def test_cheap_review_falls_back_to_primary(
    tmp_path,
    taxonomy,
    claims,
) -> None:
    client = FakeClient(
        {
            "gpt-5.4-mini": _classification(needs_review=True),
            "gpt-5.5": _classification(),
        }
    )

    run = classify_comments(
        unique_comments=_comments("Too small"),
        taxonomy=taxonomy,
        claims=claims,
        client=client,
        cache=JsonlCache(tmp_path / "cache.jsonl"),
    )

    result = next(iter(run.classifications.values()))
    assert client.calls == ["gpt-5.4-mini", "gpt-5.5"]
    assert result.status.value == "AUTO_APPROVED"
    assert run.routing["cheap_result_fallback"] == 1


def test_multiple_cheap_semantic_units_fall_back_to_primary(
    tmp_path,
    taxonomy,
    claims,
) -> None:
    client = FakeClient(
        {
            "gpt-5.4-mini": _multi_issue_classification(),
            "gpt-5.5": _classification(
                "EXPERIENCE_DISCOMFORT",
                evidence="Uncomfortable",
            ),
        }
    )

    run = classify_comments(
        unique_comments=_comments("Uncomfortable", reason="OTHER"),
        taxonomy=taxonomy,
        claims=claims,
        client=client,
        cache=JsonlCache(tmp_path / "cache.jsonl"),
    )

    result = next(iter(run.classifications.values()))
    assert client.calls == ["gpt-5.4-mini", "gpt-5.5"]
    assert result.problem_label_codes == ["EXPERIENCE_DISCOMFORT"]
    assert run.routing["cheap_result_fallback"] == 1


def test_audit_disagreement_uses_secondary_model(
    tmp_path,
    taxonomy,
    claims,
) -> None:
    client = FakeClient(
        {
            "gpt-5.4-mini": _classification(),
            "gpt-5.5": _classification("FIT_TOO_LARGE"),
            "gpt-5.6-sol": _classification("FIT_TOO_LARGE"),
        },
        audit_percent=100,
    )

    run = classify_comments(
        unique_comments=_comments("Too small", reason="OTHER"),
        taxonomy=taxonomy,
        claims=claims,
        client=client,
        cache=JsonlCache(tmp_path / "cache.jsonl"),
        secondary_model="gpt-5.6-sol",
    )

    result = next(iter(run.classifications.values()))
    assert client.calls == [
        "gpt-5.4-mini",
        "gpt-5.5",
        "gpt-5.6-sol",
    ]
    assert result.status.value == "AUTO_APPROVED"
    assert run.routing["cheap_audited"] == 1
    assert run.routing["cheap_disagreement"] == 1


def test_input_semantic_risk_router_ignores_text_length() -> None:
    assert not has_input_semantic_risk("Too small")
    assert has_input_semantic_risk("Not too small")
    assert has_input_semantic_risk("Need smaller size")
    assert has_input_semantic_risk("Too small but uncomfortable")
    assert has_input_semantic_risk(
        "Too small. Very uncomfortable.",
    )
    assert has_input_semantic_risk(
        "Too small|Too small overall|No",
    )
    assert not has_input_semantic_risk(
        "The shoes feel very tight across my feet every time I wear them"
    )


def test_cancellation_is_not_converted_to_secondary_review(
    tmp_path,
    taxonomy,
    claims,
) -> None:
    client = FakeClient(
        {
            "gpt-5.5": _classification(needs_review=True),
            "gpt-5.6-sol": _classification(),
        }
    )
    checks = 0

    def should_cancel() -> bool:
        nonlocal checks
        checks += 1
        return checks >= 3

    with pytest.raises(PipelineCancelled):
        classify_comments(
            unique_comments=_comments("Too small but uncomfortable"),
            taxonomy=taxonomy,
            claims=claims,
            client=client,
            cache=JsonlCache(tmp_path / "cache.jsonl"),
            secondary_model="gpt-5.6-sol",
            should_cancel=should_cancel,
        )

    assert client.calls == ["gpt-5.5"]


def test_parallel_rows_share_same_cached_model_call(
    tmp_path,
    taxonomy,
    claims,
) -> None:
    client = FakeClient(
        {"gpt-5.4-mini": _classification()},
        max_workers=2,
    )
    comments = pd.concat(
        [
            _comments("Too small", reason="APPAREL_TOO_SMALL"),
            _comments("Too small", reason="OTHER"),
        ],
        ignore_index=True,
    )

    run = classify_comments(
        unique_comments=comments,
        taxonomy=taxonomy,
        claims=claims,
        client=client,
        cache=JsonlCache(tmp_path / "cache.jsonl"),
    )

    assert client.calls == ["gpt-5.4-mini"]
    assert run.model_calls == 1
    assert run.cache_hits == 1
    assert len(run.classifications) == 2


def test_consecutive_service_failures_alert_then_pause(
    tmp_path,
    taxonomy,
    claims,
) -> None:
    client = UnavailableClient()
    comments = pd.concat(
        [_comments(f"Unavailable {index}") for index in range(8)],
        ignore_index=True,
    )
    degraded: list[tuple[int, int]] = []

    with pytest.raises(ModelServiceUnavailable) as error:
        classify_comments(
            unique_comments=comments,
            taxonomy=taxonomy,
            claims=claims,
            client=client,
            cache=JsonlCache(tmp_path / "cache.jsonl"),
            on_model_degraded=lambda run, count, _error: degraded.append(
                (count, run.model_failures)
            ),
        )

    assert error.value.consecutive_failures == 5
    assert client.calls == 5
    assert degraded == [(3, 3), (4, 4), (5, 5)]
