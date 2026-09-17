from types import SimpleNamespace

import pandas as pd
import pytest

from return_semantics.model_client import JsonlCache, ModelCallResult, ModelHTTPError
from return_semantics.pipeline import (
    ModelServiceUnavailable,
    PipelineCancelled,
    can_accept_cheap_result,
    classify_comments,
    has_input_semantic_risk,
)
from return_semantics.schemas import ModelClassification, ValidatedClassification


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
        update={"label_code": "EXPERIENCE_COMFORT"}
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
        responses: dict[str, ModelClassification | Exception],
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
        response = self.responses[model_name]
        if isinstance(response, Exception):
            raise response
        return ModelCallResult(
            classification=response,
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


def test_cheap_result_acceptance_does_not_depend_on_primary_label() -> None:
    model_result = _classification().model_dump(mode="json")
    model_result.pop("needs_review")
    result = ValidatedClassification.model_validate(
        {
            **model_result,
            "classification_key": "key",
            "problem_label_codes": ["FIT_TOO_SMALL"],
            "positive_label_codes": [],
            "primary_label_codes": [],
            "status": "AUTO_APPROVED",
            "model_name": "cheap-model",
            "prompt_version": "test-prompt",
            "taxonomy_version": "test-taxonomy",
        }
    )

    assert can_accept_cheap_result(result) is True


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


def test_cheap_error_falls_back_to_primary(
    tmp_path,
    taxonomy,
    claims,
) -> None:
    client = FakeClient(
        {
            "gpt-5.4-mini": RuntimeError("低成本模型临时失败"),
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

    assert client.calls == ["gpt-5.4-mini", "gpt-5.5"]
    assert run.model_failures == 1
    assert run.model_calls_by_model == {"gpt-5.5": 1}
    assert run.routing == {
        "cheap_first_pass": 1,
        "cheap_error_fallback": 1,
    }


def test_multiple_cheap_semantic_units_fall_back_to_primary(
    tmp_path,
    taxonomy,
    claims,
) -> None:
    client = FakeClient(
        {
            "gpt-5.4-mini": _multi_issue_classification(),
            "gpt-5.5": _classification(
                "EXPERIENCE_COMFORT",
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
    assert result.problem_label_codes == ["EXPERIENCE_COMFORT"]
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
    assert result.review_diagnostics == []


@pytest.mark.parametrize(
    "secondary_error,expected_code",
    [
        (RuntimeError("复核模型临时失败"), "SECONDARY_MODEL_CALL_FAILED"),
        (TimeoutError("The read operation timed out"), "SECONDARY_MODEL_TIMEOUT"),
    ],
)
def test_secondary_error_becomes_manual_review(
    tmp_path,
    taxonomy,
    claims,
    secondary_error,
    expected_code,
) -> None:
    client = FakeClient(
        {
            "gpt-5.5": _classification(needs_review=True),
            "gpt-5.6-sol": secondary_error,
        }
    )

    run = classify_comments(
        unique_comments=_comments("Too small but uncomfortable"),
        taxonomy=taxonomy,
        claims=claims,
        client=client,
        cache=JsonlCache(tmp_path / "cache.jsonl"),
        secondary_model="gpt-5.6-sol",
    )

    result = next(iter(run.classifications.values()))
    assert client.calls == ["gpt-5.5", "gpt-5.6-sol"]
    assert run.model_failures == 1
    assert result.status.value == "MANUAL_REVIEW"
    assert result.review_reasons[-1].startswith("二次模型调用失败:")
    assert result.review_diagnostics[0].code == expected_code
    assert result.review_diagnostics[0].action == "SYSTEM_RERUN"


def test_secondary_accepts_same_terminal_result_with_evidence_span_variation(
    tmp_path,
    taxonomy,
    claims,
) -> None:
    client = FakeClient(
        {
            "gpt-5.5": _classification(
                evidence="Too small",
                needs_review=True,
            ),
            "gpt-5.6-sol": _classification(
                evidence="They are Too small",
            ),
        }
    )

    run = classify_comments(
        unique_comments=_comments("They are Too small but still usable"),
        taxonomy=taxonomy,
        claims=claims,
        client=client,
        cache=JsonlCache(tmp_path / "cache.jsonl"),
        secondary_model="gpt-5.6-sol",
    )

    result = next(iter(run.classifications.values()))
    assert client.calls == ["gpt-5.5", "gpt-5.6-sol"]
    assert result.status.value == "AUTO_APPROVED"
    assert result.review_reasons == ["二次模型结果一致"]


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


def test_parallel_run_aggregates_metrics_and_callbacks_in_input_order(
    tmp_path,
    taxonomy,
    claims,
) -> None:
    client = FakeClient(
        {"gpt-5.4-mini": _classification()},
        max_workers=3,
    )
    comments = pd.concat(
        [_comments(f"Too small {index}") for index in range(6)],
        ignore_index=True,
    )
    progress_events: list[tuple[int, int]] = []
    checkpoint_sizes: list[int] = []

    run = classify_comments(
        unique_comments=comments,
        taxonomy=taxonomy,
        claims=claims,
        client=client,
        cache=JsonlCache(tmp_path / "cache.jsonl"),
        progress=lambda current, total: progress_events.append((current, total)),
        checkpoint=lambda snapshot: checkpoint_sizes.append(
            len(snapshot.classifications)
        ),
    )

    assert run.model_calls == 6
    assert run.model_calls_by_model == {"gpt-5.4-mini": 6}
    assert run.usage == {"input_tokens": 60, "output_tokens": 12}
    assert run.usage_by_model == {
        "gpt-5.4-mini": {"input_tokens": 60, "output_tokens": 12}
    }
    assert run.request_metrics == {"attempts": 6, "retries": 0, "latency_ms": 30}
    assert run.routing == {
        "cheap_first_pass": 6,
        "cheap_result_accepted": 6,
    }
    assert progress_events == [(index, 6) for index in range(1, 7)]
    assert checkpoint_sizes == [1, 5, 6]


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

    with pytest.raises(PipelineCancelled, match="^分析任务已取消$"):
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
    assert str(error.value) == (
        "模型服务连续失败 5 次，已自动暂停："
        "Sub2API 调用失败: Sub2API HTTP 503: Service unavailable"
    )
    assert client.calls == 5
    assert degraded == [(3, 3), (4, 4), (5, 5)]
