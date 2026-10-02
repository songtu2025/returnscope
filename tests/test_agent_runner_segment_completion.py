from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest
from test_agent_runner_segment_outcomes import _latest_run
from test_agent_runner_segment_outcomes import runtime as runtime

from return_semantics.schemas import ProcessingStatus
from web_backend.common import json_value


def _complete(runtime: SimpleNamespace) -> None:
    runtime.runner._complete_segment_run(
        runtime.context,
        runtime.seed.dataset,
        set(runtime.seed.results),
        runtime.seed.taxonomy,
        runtime.context.latest_run,
    )


@pytest.mark.parametrize("previous_version", [0, 4])
@pytest.mark.parametrize("phase", ["cached", "latest", "overlap"])
@pytest.mark.parametrize(
    ("status", "expected_status"),
    [
        (ProcessingStatus.AUTO_APPROVED, "completed"),
        (ProcessingStatus.MANUAL_REVIEW, "completed"),
        (ProcessingStatus.MODEL_ERROR, "completed_with_errors"),
    ],
)
def test_completion_preserves_publication_and_runtime(
    runtime, previous_version, phase, status, expected_status
) -> None:
    seed = runtime.seed
    result = seed.results[seed.key].model_copy(
        update={
            "status": status,
            "review_reasons": ["需要人工确认"]
            if status is ProcessingStatus.MANUAL_REVIEW
            else [],
        }
    )
    runtime.context.existing_results = {
        seed.key: result.model_copy(update={"model_name": "历史结果"})
    }
    run = _latest_run({seed.key: result.model_copy(update={"model_name": "最新结果"})})
    if phase == "cached":
        run = replace(
            run, classifications={}, model_calls=0, cache_hits=1, model_failures=0
        )
    elif phase == "latest":
        runtime.context.existing_results = {}
    runtime.context.latest_run = run
    runtime.context.segment["result_version"] = previous_version
    with seed.database.transaction() as connection:
        connection.execute(
            "UPDATE task_segments SET result_version = ? WHERE id = ?",
            (previous_version, seed.segment_id),
        )

    _complete(runtime)

    segment = runtime.runner._load_segment(seed.segment_id)
    assert segment["status"] == expected_status
    assert segment["progress_current"] == segment["progress_total"] == 1
    assert (
        segment["model_calls"],
        segment["cache_hits"],
        segment["model_failures"],
    ) == ((3, 6, 7) if phase == "cached" else (14, 18, 24))
    assert segment["result_version"] == previous_version + 1
    assert segment["result_publish_status"] == "published"
    assert segment["result_publish_error"] is None
    assert segment["result_json_path"] == str(runtime.context.checkpoint_path)
    expected_path = (
        runtime.runner.settings.data_dir
        / "results"
        / seed.task_id
        / "segments"
        / f"{seed.segment_id}-analysis-v{previous_version + 1}.xlsx"
    )
    assert segment["result_file_path"] == str(expected_path)
    assert expected_path.is_file()
    checkpoint = runtime.runner._load_checkpoint(runtime.context.checkpoint_path)
    expected_result = (
        runtime.context.existing_results[seed.key]
        if phase == "cached"
        else run.classifications[seed.key]
    )
    assert checkpoint == {seed.key: expected_result}
    version = runtime.runner.result_service.get(segment["result_version_id"])
    assert version["record_count"] == 3
    assert version["version"] == 1
    with seed.database.connect() as connection:
        event = connection.execute(
            "SELECT data_json FROM task_events WHERE event_type = 'segment_completed'"
        ).fetchone()
    event_data = json_value(event["data_json"], {})
    assert event_data["status"] == expected_status
    assert event_data["segment_id"] == seed.segment_id
    assert event_data["result_version_id"] == segment["result_version_id"]
    runtime.refresh_parent.assert_called_once_with(seed.task_id, seed.dataset)


def test_completion_keeps_checkpoint_publication_export_refresh_order(
    runtime, monkeypatch
) -> None:
    runtime.context.latest_run = _latest_run(runtime.seed.results)
    extra_key = "另一个片段的分类键"
    dataset = runtime.seed.dataset
    records = pd.concat(
        [
            dataset.records,
            dataset.records.iloc[:1].assign(classification_key=extra_key),
        ],
        ignore_index=True,
    )
    unique_comments = pd.concat(
        [
            dataset.unique_comments,
            dataset.unique_comments.assign(classification_key=extra_key),
        ],
        ignore_index=True,
    )
    dataset = replace(dataset, records=records, unique_comments=unique_comments)
    runtime.seed.dataset = dataset
    calls = Mock()
    for name, owner, attribute in (
        ("checkpoint", runtime.runner, "_write_checkpoint"),
        ("publish", runtime.runner.result_service, "publish_v1"),
        ("export", runtime.runner, "_export_legacy_segment_result"),
        ("refresh", runtime.runner, "_refresh_parent"),
    ):
        method = Mock(wraps=getattr(owner, attribute))
        calls.attach_mock(method, name)
        monkeypatch.setattr(owner, attribute, method)

    _complete(runtime)

    assert [call[0] for call in calls.mock_calls[:4]] == [
        "checkpoint",
        "publish",
        "export",
        "refresh",
    ]
    published_dataset = calls.publish.call_args.kwargs["dataset"]
    assert len(published_dataset.records) == 3
    assert set(published_dataset.unique_comments["classification_key"]) == set(
        runtime.seed.results
    )
    assert calls.export.call_args.args[2] is published_dataset
    calls.refresh.assert_called_once_with(runtime.seed.task_id, dataset)


@pytest.mark.parametrize("phase", ["missing", "extra"])
def test_incomplete_results_do_not_checkpoint_or_publish(
    runtime, monkeypatch, phase
) -> None:
    runtime.context.existing_results = {}
    results = (
        {}
        if phase == "missing"
        else {
            **runtime.seed.results,
            "额外分类键": next(iter(runtime.seed.results.values())),
        }
    )
    runtime.context.latest_run = _latest_run(results)
    before = runtime.runner._load_segment(runtime.seed.segment_id)
    publish = Mock()
    export = Mock()
    monkeypatch.setattr(runtime.runner.result_service, "publish_v1", publish)
    monkeypatch.setattr(runtime.runner, "_export_legacy_segment_result", export)

    with pytest.raises(ValueError, match="Listing 片段仍缺少"):
        _complete(runtime)

    assert not runtime.context.checkpoint_path.exists()
    assert runtime.runner._load_segment(runtime.seed.segment_id) == before
    publish.assert_not_called()
    export.assert_not_called()
    runtime.refresh_parent.assert_not_called()


def test_checkpoint_failure_stops_publication(runtime, monkeypatch) -> None:
    runtime.context.latest_run = _latest_run(runtime.seed.results)
    before = runtime.runner._load_segment(runtime.seed.segment_id)
    publish = Mock()
    monkeypatch.setattr(runtime.runner.result_service, "publish_v1", publish)
    monkeypatch.setattr(
        runtime.runner, "_write_checkpoint", Mock(side_effect=OSError("模拟写入失败"))
    )

    with pytest.raises(OSError, match="模拟写入失败"):
        _complete(runtime)

    assert runtime.runner._load_segment(runtime.seed.segment_id) == before
    publish.assert_not_called()
    runtime.refresh_parent.assert_not_called()


def test_legacy_export_failure_keeps_published_result(runtime, monkeypatch) -> None:
    runtime.context.latest_run = _latest_run(runtime.seed.results)
    monkeypatch.setattr(
        "web_backend.agent_runner.export_results",
        Mock(side_effect=OSError("模拟导出失败")),
    )
    runtime.refresh_parent = Mock()
    monkeypatch.setattr(runtime.runner, "_refresh_parent", runtime.refresh_parent)

    _complete(runtime)

    segment = runtime.runner._load_segment(runtime.seed.segment_id)
    assert segment["status"] == "completed"
    assert segment["result_publish_status"] == "published"
    assert segment["result_file_path"] is None
    assert (
        runtime.runner.result_service.get(segment["result_version_id"])["record_count"]
        == 3
    )
    assert (
        runtime.runner._load_checkpoint(runtime.context.checkpoint_path)
        == runtime.seed.results
    )
    with runtime.seed.database.connect() as connection:
        event = connection.execute(
            "SELECT data_json FROM task_events WHERE event_type = 'legacy_export_failed'"
        ).fetchone()
    assert json_value(event["data_json"], {}) == {
        "segment_id": runtime.seed.segment_id,
        "error": "模拟导出失败",
    }
    runtime.refresh_parent.assert_called_once_with(
        runtime.seed.task_id, runtime.seed.dataset
    )
