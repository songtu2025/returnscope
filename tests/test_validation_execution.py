from types import SimpleNamespace

import pytest
from test_validation_run_service import _build_harness, _create_run

from web_backend.model_probe import ModelValidationError


@pytest.mark.parametrize("model_missing", (False, True))
@pytest.mark.parametrize("structured", (False, True))
def test_failed_probe_keeps_error_identity_timing_and_catalog_before_event(
    tmp_path, monkeypatch, model_missing, structured
) -> None:
    failure = (
        ModelValidationError("长" * 620, "synthetic", "合成建议", 503)
        if structured
        else RuntimeError("长" * 620)
    )
    harness = _build_harness(tmp_path, failure=failure)
    run_id = str(_create_run(harness, "config", 1)["id"])
    if model_missing:
        harness.catalog.models.clear()
    times = iter([10.0, 10.125])
    monkeypatch.setattr(
        "web_backend.model_services.validation_execution.time",
        SimpleNamespace(monotonic=lambda: next(times)),
    )
    catalog_at_event = []
    original = harness.service._update_validation_item

    def record(*args):
        if args[-1].event_type == "model_failed":
            catalog_at_event.append(list(harness.catalog.validation_updates))
        return original(*args)

    monkeypatch.setattr(harness.service, "_update_validation_item", record)
    context = harness.service._prepare_validation_context(run_id)
    result = harness.service._run_validation_item(context, 0, context.run["items"][0])
    assert isinstance(result, ModelValidationError)
    if structured:
        assert result is failure
    item = harness.service.get_validation_run(run_id)["items"][0]
    assert item["duration_ms"] == 125
    assert item["message"] == ("长" * (620 if structured else 500))
    assert item["error_category"] == ("synthetic" if structured else "unknown")
    assert len(catalog_at_event) == 1
    assert bool(catalog_at_event[0]) is not model_missing
    if not model_missing:
        assert catalog_at_event[0][0][2] == "长" * 500


@pytest.mark.parametrize("model_missing", (False, True))
def test_successful_probe_preserves_report_event_and_catalog_order(
    tmp_path, monkeypatch, model_missing
) -> None:
    harness = _build_harness(tmp_path)
    run_id = str(_create_run(harness, "model", 1)["id"])
    if model_missing:
        harness.catalog.models.clear()
    catalog_at_event = []
    original = harness.service._update_validation_item

    def record(*args):
        if args[-1].event_type == "model_passed":
            catalog_at_event.append(list(harness.catalog.validation_updates))
        return original(*args)

    monkeypatch.setattr(harness.service, "_update_validation_item", record)
    harness.service.run_validation(run_id)
    result = harness.service.get_validation_run(run_id)
    assert result["status"] == "passed"
    event = next(
        event
        for event in harness.service.validation_events(run_id)
        if event["event_type"] == "model_passed"
    )
    assert event["data"] == {
        "duration_ms": 25,
        "http_status": 200,
        "response_model": "model-a-response",
    }
    assert len(catalog_at_event) == 1
    assert bool(catalog_at_event[0]) is not model_missing
