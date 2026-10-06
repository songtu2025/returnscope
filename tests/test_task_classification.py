from unittest.mock import Mock, call

import pandas as pd
import pytest
from test_agent_runner_segment_outcomes import _latest_run
from test_agent_runner_segment_outcomes import runtime as runtime
from test_task_model_runtime import _policy
from test_task_model_runtime import _runtime as model_runtime

from return_semantics.category_pipeline import CategorySegmentRuntime
from return_semantics.claims import NO_CLAIMS_VERSION
from web_backend.common import json_text
from web_backend.task_execution import classification


def _segment_runtime(fallback):
    policy = _policy()
    if fallback:
        policy["actual"]["review"]["fallback_from"] = "secondary"
    return CategorySegmentRuntime(Mock(), Mock(), "review-model", policy)


@pytest.mark.parametrize("failures", [2, 3, 4, 5])
@pytest.mark.parametrize("fallback", [False, True])
def test_segment_callbacks_keep_checkpoint_alert_and_progress_boundaries(
    runtime, monkeypatch, failures, fallback
):
    runner, context = runtime.runner, runtime.context
    segment_runtime = _segment_runtime(fallback)
    context.task["snapshot_json"] = json_text({"analysis_context": "review"})
    run = _latest_run(runtime.seed.results)
    pipeline = Mock(return_value=run)
    monkeypatch.setattr(classification, "classify_comments", pipeline)
    runner._get_cache = Mock()
    runner._segment_should_stop = Mock(return_value=True)
    runner._update_segment_progress = Mock()
    operations = Mock()
    runner._save_segment_checkpoint = operations.save
    runner._record_model_degraded = operations.alert
    result = runner._classify_segment(
        context,
        runtime.seed.dataset.unique_comments,
        runtime.seed.taxonomy,
        segment_runtime,
        7,
    )
    kwargs = pipeline.call_args.kwargs
    assert result is run and kwargs["analysis_context"] == "review"
    assert kwargs["model_policy_version"] == "policy-v1"
    assert kwargs["secondary_is_fallback"] is fallback
    runner._get_cache.assert_called_once_with(
        f"{context.task_id}-{context.task['config_version_id']}"
    )
    for current in [0, 1, 4, 6]:
        kwargs["progress"](current, 6)
    assert runner._update_segment_progress.call_args_list == [
        call(context.task_id, context.segment_id, count, 7) for count in [1, 5, 7]
    ]
    kwargs["checkpoint"](run)
    kwargs["on_model_degraded"](run, failures, "合成错误")
    expected = [call.save(context, run), call.save(context, run)]
    if failures == 3:
        expected.append(call.alert(context.task_id, context.segment_id, "合成错误", 3))
    assert operations.mock_calls == expected
    assert kwargs["should_cancel"]()
    runner._segment_should_stop.assert_called_once_with(
        context.task_id, context.segment_id
    )


def test_empty_segment_never_calls_model_or_cache(runtime, monkeypatch):
    pipeline = Mock()
    monkeypatch.setattr(classification, "classify_comments", pipeline)
    runtime.runner._get_cache = Mock()
    result = runtime.runner._classify_segment(
        runtime.context,
        pd.DataFrame(),
        runtime.seed.taxonomy,
        _segment_runtime(False),
        0,
    )
    assert result.classifications == {} and result.model_calls == 0
    pipeline.assert_not_called()
    runtime.runner._get_cache.assert_not_called()


@pytest.mark.parametrize("kind", ["raw_dataset", "review_file"])
@pytest.mark.parametrize("policy_kind", ["none", "review", "fallback"])
@pytest.mark.parametrize("explicit_context", [False, True])
def test_source_sample_preserves_settings_claims_and_source_context(
    runtime, monkeypatch, kind, policy_kind, explicit_context
):
    runner = runtime.runner
    _, settings, _, _ = model_runtime(monkeypatch, "cheap", "secondary", False)
    runner.config_service.build_model_settings.return_value = settings
    runner.claims_resolver = Mock()
    runner._get_cache = Mock()
    runner._get_rate_limiter = Mock()
    source = _sample_source(kind, policy_kind, explicit_context)
    pipeline = Mock(return_value=_latest_run({}))
    client = Mock()
    monkeypatch.setattr(classification, "classify_comments", pipeline)
    monkeypatch.setattr(classification, "Sub2APIClient", client)
    progress = Mock()
    result = runner.classify_taxonomy_sample(
        taxonomy=runtime.seed.taxonomy,
        samples=[{"classification_key": 42, "comment": None, "category_a": "水鞋"}],
        source=source,
        progress=progress,
    )
    assert result is pipeline.return_value
    kwargs = pipeline.call_args.kwargs
    _assert_sample_inputs(kwargs)
    assert kwargs["analysis_context"] == ("review" if explicit_context else "returns")
    assert kwargs["model_policy_version"] == "source-policy"
    assert kwargs["secondary_model"] == (
        "secondary" if policy_kind == "none" else "frozen-review"
    )
    assert kwargs["secondary_is_fallback"] is (policy_kind == "fallback")
    assert kwargs["progress"] is progress
    runner.config_service.build_model_settings.assert_called_once_with("42")
    runner.claims_resolver.resolve.assert_called_once_with(
        "", None, "footwear", expected_version=NO_CLAIMS_VERSION
    )
    runner._get_rate_limiter.assert_called_once_with("42", settings.requests_per_minute)
    client.assert_called_once()
    assert kwargs["client"] is client.return_value
    assert kwargs["claims"] is runner.claims_resolver.resolve.return_value
    runner._get_cache.assert_called_once_with("classification-standard-validation")


def _sample_source(kind, policy_kind, explicit_context):
    source = {
        "kind": kind,
        "config_version_id": 42,
        "standard_key": "footwear",
        "model_policy_version": "source-policy",
    }
    if policy_kind != "none":
        source["model_policy"] = _segment_runtime(
            policy_kind == "fallback"
        ).model_policy
    if explicit_context:
        source["analysis_context"] = "review"
    return source


def _assert_sample_inputs(kwargs):
    assert kwargs["unique_comments"].to_dict("records") == [
        {
            "classification_key": "42",
            "comment_normalized": "None",
            "reason": None,
            "category_a": "水鞋",
            "category_b": "",
        }
    ]


@pytest.mark.parametrize("fallback", [False, True])
def test_task_sample_uses_frozen_task_context_and_segment_runtime(
    runtime, monkeypatch, fallback
):
    runner, context = runtime.runner, runtime.context
    task = context.task | {"snapshot_json": json_text({"analysis_context": "review"})}
    segment_runtime = _segment_runtime(fallback)
    runner._snapshot_model_settings = Mock()
    runner._build_segment_runtime = Mock(return_value=segment_runtime)
    runner._get_cache = Mock()
    pipeline = Mock(return_value=_latest_run({}))
    monkeypatch.setattr(classification, "classify_comments", pipeline)
    progress = Mock()
    result = runner.classify_taxonomy_sample(
        taxonomy=runtime.seed.taxonomy,
        samples=[{"classification_key": 42, "comment": None, "category_a": "水鞋"}],
        source={"kind": "task", "task": task, "segment": context.segment},
        progress=progress,
    )
    assert result is pipeline.return_value
    kwargs = pipeline.call_args.kwargs
    _assert_sample_inputs(kwargs)
    assert kwargs["analysis_context"] == "review"
    assert (
        kwargs["claims"] is segment_runtime.claims
        and kwargs["client"] is segment_runtime.client
    )
    assert kwargs["secondary_is_fallback"] is fallback
    assert kwargs["model_policy_version"] == "policy-v1"
    assert (
        kwargs["progress"] is progress and kwargs["secondary_model"] == "review-model"
    )
    runner._snapshot_model_settings.assert_called_once_with(
        task, {"analysis_context": "review"}
    )
    runner._build_segment_runtime.assert_called_once_with(
        context.segment,
        runner._snapshot_model_settings.return_value,
        str(task["config_version_id"]),
        str(task["store"]),
        task.get("listing"),
    )
    runner._get_cache.assert_called_once_with("classification-standard-validation")
