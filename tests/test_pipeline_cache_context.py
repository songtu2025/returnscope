from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_pipeline_routing import _classification

from return_semantics.analysis_context import RETURNS_CONTEXT
from return_semantics.fact_pipeline import FactPipelineCancelled
from return_semantics.model_client import JsonlCache, ModelCallResult
from return_semantics.pipeline import (
    PipelineCancelled,
    _call_with_cache,
    _PipelineContext,
    _RowContext,
)
from return_semantics.schemas import (
    ListingClaimsConfig,
    ReviewDiagnostic,
    TaxonomyConfig,
)


@pytest.fixture
def cache_call(
    tmp_path: Path, taxonomy: TaxonomyConfig, claims: ListingClaimsConfig
) -> SimpleNamespace:
    client = Mock()
    client.settings = SimpleNamespace(
        model="primary",
        cheap_model="cheap",
        cache_namespace="synthetic-cache",
        reasoning_effort="medium",
        cheap_reasoning_effort="low",
        secondary_reasoning_effort="high",
    )
    client.classify.return_value = ModelCallResult(
        _classification(), "primary", {"input_tokens": 7}, {"attempts": 1}
    )
    return SimpleNamespace(
        row=_RowContext(
            "key",
            "Too small",
            "",
            "listing-a",
            [{"role": "user", "content": "Too small"}],
            False,
            "primary",
        ),
        context=_PipelineContext(
            taxonomy,
            claims,
            client,
            JsonlCache(tmp_path / "cache.jsonl"),
            False,
            "secondary",
            None,
            "policy-a",
            False,
            RETURNS_CONTEXT,
        ),
        model_name="primary",
        thinking=False,
    )


def _invoke(call: SimpleNamespace) -> tuple[ModelCallResult, bool]:
    return _call_with_cache(
        row=call.row,
        context=call.context,
        model_name=call.model_name,
        thinking=call.thinking,
    )


def test_identical_call_reuses_persisted_result(cache_call: SimpleNamespace) -> None:
    result, hit = _invoke(cache_call)
    cached, cached_hit = _invoke(cache_call)

    assert not hit and cached_hit
    assert cached == result
    cache_call.context.client.classify.assert_called_once_with(
        messages=cache_call.row.messages, model="primary", thinking=False
    )
    assert (
        len(cache_call.context.cache.path.read_text(encoding="utf-8").splitlines()) == 1
    )
    cache_call.context = replace(
        cache_call.context, cache=JsonlCache(cache_call.context.cache.path)
    )
    assert _invoke(cache_call) == (result, True)
    assert cache_call.context.client.classify.call_count == 1


@pytest.mark.parametrize(
    "field",
    [
        "comment",
        "scope",
        "policy",
        "taxonomy",
        "claims",
        "provider",
        "model",
        "thinking",
        "profile",
    ],
)
def test_cache_keeps_scope_and_configuration_isolated(
    cache_call: SimpleNamespace, field: str
) -> None:
    client = cache_call.context.client
    assert _invoke(cache_call)[1] is False
    if field == "comment":
        cache_call.row = replace(cache_call.row, comment="Too small!")
    elif field == "scope":
        cache_call.row = replace(cache_call.row, classification_scope="listing-b")
    elif field == "policy":
        cache_call.context = replace(
            cache_call.context, model_policy_version="policy-b"
        )
    elif field == "taxonomy":
        cache_call.context = replace(
            cache_call.context,
            taxonomy=cache_call.context.taxonomy.model_copy(
                update={"version": "taxonomy-b"}
            ),
        )
    elif field == "claims":
        cache_call.context = replace(
            cache_call.context,
            claims=cache_call.context.claims.model_copy(update={"version": "claims-b"}),
        )
    elif field == "provider":
        client.settings.cache_namespace = "synthetic-other-provider"
    elif field == "model":
        cache_call.model_name = "other-model"
    elif field == "thinking":
        cache_call.thinking = True
    else:
        cache_call.context = replace(
            cache_call.context,
            taxonomy=cache_call.context.taxonomy.model_copy(
                update={"recognition_profile": "semantic_v1"}
            ),
        )

    assert _invoke(cache_call)[1] is False
    assert _invoke(cache_call)[1] is True
    assert client.classify.call_count == 2
    assert (
        len(cache_call.context.cache.path.read_text(encoding="utf-8").splitlines()) == 2
    )


@pytest.mark.parametrize(
    "model,thinking,effort",
    [
        ("primary", False, "reasoning_effort"),
        ("cheap", False, "cheap_reasoning_effort"),
        ("secondary", True, "secondary_reasoning_effort"),
    ],
)
def test_cache_uses_effort_for_actual_model_role(
    cache_call: SimpleNamespace, model: str, thinking: bool, effort: str
) -> None:
    cache_call.model_name, cache_call.thinking = model, thinking
    client = cache_call.context.client
    assert _invoke(cache_call)[1] is False
    setattr(client.settings, effort, "other-effort")
    assert _invoke(cache_call)[1] is False
    for field in {
        "reasoning_effort",
        "cheap_reasoning_effort",
        "secondary_reasoning_effort",
    } - {effort}:
        setattr(client.settings, field, "unused-effort")
    assert _invoke(cache_call)[1] is True
    assert client.classify.call_count == 2


def test_force_refresh_replaces_existing_cache(cache_call: SimpleNamespace) -> None:
    original, _ = _invoke(cache_call)
    fresh = replace(original, usage={"input_tokens": 13})
    cache_call.context.client.classify.return_value = fresh
    cache_call.context = replace(cache_call.context, force=True)

    assert _invoke(cache_call) == (fresh, False)
    cache_call.context = replace(cache_call.context, force=False)
    assert _invoke(cache_call) == (fresh, True)
    assert cache_call.context.client.classify.call_count == 2


def _system_error() -> ModelCallResult:
    classification = _classification().model_copy(
        update={
            "needs_review": True,
            "review_diagnostics": [
                ReviewDiagnostic(
                    code="COVERAGE_AUDIT_FAILED",
                    detail="合成异常",
                    action="SYSTEM_RERUN",
                )
            ],
        }
    )
    return ModelCallResult(classification, "primary", {"input_tokens": 5})


def test_system_error_cache_is_replaced(cache_call: SimpleNamespace) -> None:
    error = _system_error()
    cache_call.context.client.classify.return_value = error
    result, hit = _invoke(cache_call)
    assert result == error and not hit
    assert not cache_call.context.cache.path.exists()
    cache_call.context.client.classify.return_value = ModelCallResult(
        _classification(), "primary", {"input_tokens": 7}
    )
    result, _ = _invoke(cache_call)
    line = cache_call.context.cache.path.read_text(encoding="utf-8")

    key = json.loads(line)["cache_key"]
    cache_call.context.cache.put(key, error)

    fresh, hit = _invoke(cache_call)

    assert not hit and fresh == result
    assert _invoke(cache_call) == (fresh, True)
    assert cache_call.context.client.classify.call_count == 3


def test_fact_cancellation_keeps_signal_and_does_not_cache(
    cache_call: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    signal = Mock(return_value=True)
    cache_call.context = replace(
        cache_call.context,
        taxonomy=cache_call.context.taxonomy.model_copy(
            update={"recognition_profile": "fact_v2"}
        ),
        should_cancel=signal,
    )
    error = FactPipelineCancelled("合成取消")
    classify = Mock(side_effect=error)
    monkeypatch.setattr("return_semantics.pipeline.classify_facts", classify)

    with pytest.raises(PipelineCancelled, match="合成取消") as caught:
        _invoke(cache_call)

    assert caught.value.__cause__ is error
    classify.assert_called_once_with(
        comment=cache_call.row.comment,
        taxonomy=cache_call.context.taxonomy,
        client=cache_call.context.client,
        model_name="primary",
        reasoning_effort="medium",
        should_cancel=signal,
        claims=cache_call.context.claims,
    )
    cache_call.context.client.classify.assert_not_called()
    assert not cache_call.context.cache.path.exists()


def test_model_failure_keeps_error_and_does_not_cache(
    cache_call: SimpleNamespace,
) -> None:
    error = RuntimeError("合成模型失败")
    cache_call.context.client.classify.side_effect = error

    with pytest.raises(RuntimeError, match="合成模型失败") as caught:
        _invoke(cache_call)

    assert caught.value is error
    assert not cache_call.context.cache.path.exists()
