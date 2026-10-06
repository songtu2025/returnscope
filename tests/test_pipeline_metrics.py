import pytest
from test_pipeline_routing import _classification

from return_semantics.model_client import ModelCallResult, ModelHTTPError
from return_semantics.pipeline_metrics import _RunTracker
from return_semantics.pipeline_models import ModelServiceUnavailable


@pytest.mark.parametrize("count", [2, 3, 4, 5, 6])
def test_service_failure_notifications_and_pause_boundaries(count):
    notifications = []
    tracker = _RunTracker(
        lambda run, failures, _error: notifications.append(
            (run.model_failures, failures)
        )
    )
    error = ModelHTTPError("synthetic", 503, "合成服务错误")
    for _ in range(count):
        failures = tracker.record_failure(error)
    assert failures == tracker.snapshot().model_failures == count
    assert notifications == [(value, value) for value in range(3, count + 1)]
    if count >= 5:
        with pytest.raises(ModelServiceUnavailable) as caught:
            tracker.pause_after_failure(failures, error)
        assert caught.value.consecutive_failures == count
        assert caught.value.__cause__ is error
        with pytest.raises(ModelServiceUnavailable):
            tracker.raise_if_service_paused()
    else:
        tracker.pause_after_failure(failures, error)
        tracker.raise_if_service_paused()


@pytest.mark.parametrize("cache_hit", [False, True])
def test_cached_calls_keep_failure_streak_and_real_success_resets_it(cache_hit):
    tracker = _RunTracker(None)
    error = ModelHTTPError("synthetic", 503, "合成服务错误")
    tracker.record_failure(error)
    tracker.record_failure(error)
    call = ModelCallResult(
        _classification(),
        "synthetic",
        {"input_tokens": 7},
        metrics={"fact_model_calls": 2, "output_correction_calls": 1},
    )
    tracker.record_call("synthetic", call, cache_hit)
    assert tracker.consecutive_service_failures == (2 if cache_hit else 0)
    snapshot = tracker.snapshot()
    assert snapshot.model_failures == 2
    assert (snapshot.cache_hits, snapshot.model_calls) == (
        (1, 0) if cache_hit else (0, 3)
    )
    assert snapshot.usage == ({} if cache_hit else {"input_tokens": 7})


@pytest.mark.parametrize("status", [400, 503])
def test_wrapped_http_failure_keeps_cause_classification_and_nonservice_reset(status):
    tracker = _RunTracker(None)
    tracker.record_failure(ModelHTTPError("synthetic", 503, "此前失败"))
    wrapped = RuntimeError("合成外层错误")
    wrapped.__cause__ = ModelHTTPError("synthetic", status, "合成内层错误")
    assert tracker.record_failure(wrapped) == (2 if status == 503 else 0)
    assert tracker.snapshot().model_failures == 2
