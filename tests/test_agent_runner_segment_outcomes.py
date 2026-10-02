import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_classification_result_pool import _seed_result_context

from return_semantics.pipeline import (
    ModelServiceUnavailable,
    PipelineCancelled,
    PipelineRun,
)
from return_semantics.schemas import ProcessingStatus
from web_backend.agent_runner import AgentRunner, _SegmentRunContext
from web_backend.classification_result_service import ResultPublicationError
from web_backend.common import json_text, json_value

NOW = "2026-10-02T01:02:03+00:00"
STARTED_AT = "2026-10-01T01:02:03+00:00"
ERROR = "模拟异常信息" * 500
MODEL_PAUSE_MESSAGE = "模型服务连续失败，任务已自动暂停；请检查连接后继续执行"
OUTCOMES = {
    "interrupted": ("retry_pending", "segment_retry_pending", "语义分析"),
    "model": ("paused", "model_service_paused", "模型服务异常"),
    "failed": ("failed", "segment_failed", "运行失败"),
    "publish": ("completed", "segment_classified_publish_failed", "生成结果"),
}


def _failure(kind: str) -> Exception:
    return {
        "interrupted": PipelineCancelled(ERROR),
        "model": ModelServiceUnavailable(ERROR, 5),
        "failed": RuntimeError(ERROR),
        "publish": ResultPublicationError(ERROR),
    }[kind]


def _latest_run(results) -> PipelineRun:
    return PipelineRun(
        classifications=results,
        usage={},
        usage_by_model={},
        cache_hits=13,
        cache_hits_by_model={},
        model_calls=11,
        model_calls_by_model={},
        request_metrics={},
        routing={},
        model_failures=17,
    )


@pytest.fixture
def runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    seed = _seed_result_context(tmp_path)
    with seed.database.transaction() as connection:
        connection.execute(
            """
            UPDATE task_segments
            SET started_at = ?, model_calls = 3, cache_hits = 5, model_failures = 7
            WHERE id = ?
            """,
            (STARTED_AT, seed.segment_id),
        )
    runner = AgentRunner(seed.database, SimpleNamespace(data_dir=tmp_path), Mock())
    context = _SegmentRunContext(
        task_id=seed.task_id,
        segment_id=seed.segment_id,
        task=runner._load_task(seed.task_id),
        segment=runner._load_segment(seed.segment_id),
        checkpoint_path=tmp_path / "checkpoint.json",
        existing_results={
            key: result.model_copy(update={"model_name": "历史结果"})
            for key, result in seed.results.items()
        },
        base_model_calls=3,
        base_cache_hits=5,
        base_model_failures=7,
    )
    monkeypatch.setattr(runner, "_segment_run_context", Mock(return_value=context))
    refresh_parent = Mock(wraps=runner._refresh_parent)
    monkeypatch.setattr(runner, "_refresh_parent", refresh_parent)
    for module in (
        "web_backend.agent_runner_segment_outcomes",
        "web_backend.agent_runner_parent_result",
        "web_backend.agent_runner",
    ):
        monkeypatch.setattr(f"{module}.utc_now", lambda: NOW)
    return SimpleNamespace(
        seed=seed,
        runner=runner,
        context=context,
        refresh_parent=refresh_parent,
    )


def _prepare_failure(runtime, kind: str, phase: str = "overlap") -> None:
    if phase in {"empty", "latest"}:
        runtime.context.existing_results = {}
    if phase in {"latest", "overlap"}:
        runtime.context.latest_run = _latest_run(
            {
                key: result.model_copy(update={"model_name": "最新结果"})
                for key, result in runtime.seed.results.items()
            }
        )
    runtime.runner._execute_segment = Mock(side_effect=_failure(kind))


def _run(runtime) -> None:
    runtime.runner.run_segment(runtime.seed.task_id, runtime.seed.segment_id)


def _state(runtime) -> dict:
    with runtime.seed.database.connect() as connection:
        task = connection.execute(
            "SELECT * FROM tasks WHERE id = ?", (runtime.seed.task_id,)
        ).fetchone()
        segments = connection.execute(
            "SELECT * FROM task_segments WHERE task_id = ? ORDER BY id",
            (runtime.seed.task_id,),
        ).fetchall()
        events = connection.execute(
            "SELECT * FROM task_events WHERE task_id = ? ORDER BY id",
            (runtime.seed.task_id,),
        ).fetchall()
    return {
        "task": dict(task),
        "segments": {row["id"]: dict(row) for row in segments},
        "events": [dict(row) for row in events],
    }


@pytest.mark.parametrize(
    ("kind", "phase"),
    [
        (kind, phase)
        for kind in ("interrupted", "model", "failed")
        for phase in ("empty", "existing", "latest", "overlap")
    ]
    + [("publish", "latest"), ("publish", "overlap")],
)
def test_failure_persists_checkpoint_totals_and_event(runtime, kind, phase) -> None:
    _prepare_failure(runtime, kind, phase)
    _run(runtime)
    state = _state(runtime)
    segment = state["segments"][runtime.seed.segment_id]
    status, event_type, stage = OUTCOMES[kind]
    assert segment["status"] == status
    expected_totals = (14, 18, 24) if phase in {"latest", "overlap"} else (3, 5, 7)
    assert (
        tuple(segment[name] for name in ("model_calls", "cache_hits", "model_failures"))
        == expected_totals
    )
    assert segment["progress_current"] == (0 if phase == "empty" else 1)
    assert segment["requested_action"] is None
    assert segment["heartbeat_at"] == NOW
    assert segment["revision"] == runtime.context.segment["revision"] + 1
    assert segment["started_at"] == (None if kind == "interrupted" else STARTED_AT)
    assert segment["completed_at"] == (NOW if kind in {"failed", "publish"} else None)
    if phase == "empty":
        assert segment["result_json_path"] is None
        assert not runtime.context.checkpoint_path.exists()
    else:
        assert segment["result_json_path"] == str(runtime.context.checkpoint_path)
        saved = runtime.runner._load_checkpoint(runtime.context.checkpoint_path)
        assert set(saved) == {runtime.seed.key}
        assert saved[runtime.seed.key].model_name == (
            "最新结果" if phase in {"latest", "overlap"} else "历史结果"
        )
    event = state["events"][0]
    assert (event["event_type"], event["stage"], event["created_at"]) == (
        event_type,
        stage,
        NOW,
    )
    data = json_value(event["data_json"], {})
    assert data["segment_id"] == runtime.seed.segment_id
    if kind == "model":
        assert segment["error"] == MODEL_PAUSE_MESSAGE
        assert event["message"] == MODEL_PAUSE_MESSAGE
        assert data == {
            "segment_id": runtime.seed.segment_id,
            "model_failures": expected_totals[2],
            "error": ERROR[:500],
        }
        assert state["task"]["status"] == "paused"
        assert state["task"]["pause_requested"] == 1
    elif kind == "failed":
        assert segment["error"] == ERROR[:2000]
        assert event["message"] == ERROR[:500]
        assert state["task"]["status"] == "blocked"
    elif kind == "publish":
        assert segment["error"] is None
        assert segment["result_publish_status"] == "failed"
        assert segment["result_publish_error"] == ERROR[:500]
        assert data == {"segment_id": runtime.seed.segment_id, "error": ERROR[:500]}
        assert state["task"]["status"] == "completed"
    else:
        assert event["message"] == "Listing 已中断，等待从检查点恢复"
        assert state["task"]["status"] == "queued"
    runtime.refresh_parent.assert_called_once_with(runtime.seed.task_id)
    runtime.runner._execute_segment.assert_called_once_with(runtime.context)


@pytest.mark.parametrize(
    ("requested", "cancel", "pause", "expected"),
    [
        ("cancel", 0, 0, "cancelled"),
        ("pause", 0, 0, "paused"),
        (None, 1, 0, "cancelled"),
        (None, 0, 1, "paused"),
        ("pause", 1, 1, "cancelled"),
        ("cancel", 0, 1, "cancelled"),
    ],
)
def test_interruption_keeps_cancel_and_pause_priority(
    runtime, requested, cancel, pause, expected
) -> None:
    with runtime.seed.database.transaction() as connection:
        connection.execute(
            "UPDATE task_segments SET requested_action = ? WHERE id = ?",
            (requested, runtime.seed.segment_id),
        )
        connection.execute(
            "UPDATE tasks SET cancel_requested = ?, pause_requested = ? WHERE id = ?",
            (cancel, pause, runtime.seed.task_id),
        )
    _prepare_failure(runtime, "interrupted")
    _run(runtime)
    state = _state(runtime)
    segment = state["segments"][runtime.seed.segment_id]
    assert segment["status"] == expected
    assert segment["requested_action"] is None
    assert segment["started_at"] == STARTED_AT
    assert segment["completed_at"] == (NOW if expected == "cancelled" else None)
    expected_parent = "paused" if pause and not cancel else expected
    assert state["task"]["status"] == expected_parent
    assert state["events"][0]["event_type"] == f"segment_{expected}"


def test_model_pause_only_changes_waiting_and_running_siblings(runtime) -> None:
    statuses = (
        "queued",
        "retry_pending",
        "running",
        "completed",
        "completed_with_errors",
        "cancelled",
        "blocked",
        "paused",
    )
    with runtime.seed.database.transaction() as connection:
        for status in statuses:
            connection.execute(
                """
                INSERT INTO task_segments(
                    id, task_id, segment_key, agent_key, agent_family,
                    logic_version, taxonomy_version, model_policy_version,
                    claims_version, scope_json, status, created_at
                ) SELECT ?, task_id, ?, agent_key, agent_family,
                         logic_version, taxonomy_version, model_policy_version,
                         claims_version, scope_json, ?, created_at
                  FROM task_segments WHERE id = ?
                """,
                (status, status, status, runtime.seed.segment_id),
            )
    before = _state(runtime)["segments"]
    _prepare_failure(runtime, "model")
    _run(runtime)
    after = _state(runtime)
    for status in statuses:
        expected = dict(before[status])
        if status in {"queued", "retry_pending", "running"}:
            expected["revision"] += 1
            if status == "running":
                expected["requested_action"] = "pause"
            else:
                expected.update(status="paused", requested_action=None)
        assert after["segments"][status] == expected
    assert after["task"]["pause_requested"] == 1
    assert after["task"]["stage"] == "模型服务异常"


def test_publish_failure_keeps_quality_status_and_previous_error(runtime) -> None:
    _prepare_failure(runtime, "publish")
    result = runtime.context.latest_run.classifications[runtime.seed.key]
    runtime.context.latest_run.classifications[runtime.seed.key] = result.model_copy(
        update={
            "status": ProcessingStatus.MODEL_ERROR,
            "review_reasons": ["模型调用失败"],
        }
    )
    with runtime.seed.database.transaction() as connection:
        connection.execute(
            "UPDATE task_segments SET result_publish_error = '首次发布失败' WHERE id = ?",
            (runtime.seed.segment_id,),
        )
    _run(runtime)
    segment = _state(runtime)["segments"][runtime.seed.segment_id]
    assert segment["status"] == "completed_with_errors"
    assert segment["result_publish_error"] == "首次发布失败"
    assert segment["progress_current"] == segment["progress_total"]
    assert (
        runtime.runner._load_checkpoint(runtime.context.checkpoint_path)[
            runtime.seed.key
        ].status
        is ProcessingStatus.MODEL_ERROR
    )


@pytest.mark.parametrize("kind", list(OUTCOMES))
def test_checkpoint_failure_does_not_update_database(
    runtime, monkeypatch, kind
) -> None:
    _prepare_failure(runtime, kind)
    before = _state(runtime)
    error = OSError("模拟检查点写入失败")
    monkeypatch.setattr(runtime.runner, "_write_checkpoint", Mock(side_effect=error))
    with pytest.raises(OSError) as caught:
        _run(runtime)
    assert caught.value is error
    assert _state(runtime) == before
    runtime.refresh_parent.assert_not_called()


@pytest.mark.parametrize("kind", list(OUTCOMES))
def test_event_failure_rolls_back_status_and_keeps_checkpoint(runtime, kind) -> None:
    _prepare_failure(runtime, kind)
    with runtime.seed.database.transaction() as connection:
        connection.execute(
            """
            CREATE TRIGGER reject_task_event BEFORE INSERT ON task_events
            BEGIN SELECT RAISE(ABORT, '模拟事件写入失败'); END
            """
        )
    before = _state(runtime)
    with pytest.raises(sqlite3.IntegrityError, match="模拟事件写入失败"):
        _run(runtime)
    assert _state(runtime) == before
    assert runtime.context.checkpoint_path.exists()
    runtime.refresh_parent.assert_not_called()


def test_failure_uses_totals_from_the_latest_checkpoint(runtime) -> None:
    def execute(context) -> None:
        context.latest_run = _latest_run(runtime.seed.results)
        raise RuntimeError(ERROR)

    runtime.runner._execute_segment = Mock(side_effect=execute)
    _run(runtime)
    segment = _state(runtime)["segments"][runtime.seed.segment_id]
    assert (
        segment["model_calls"],
        segment["cache_hits"],
        segment["model_failures"],
    ) == (14, 18, 24)
    assert runtime.context.runtime_totals() == (14, 18, 24)
    assert json_value(_state(runtime)["events"][0]["data_json"], {}) == {
        "segment_id": runtime.seed.segment_id
    }


def test_partial_checkpoint_keeps_existing_and_new_results(runtime) -> None:
    second_key = "second-comment"
    result = runtime.seed.results[runtime.seed.key].model_copy(
        update={"classification_key": second_key, "model_name": "最新结果"}
    )
    runtime.context.latest_run = _latest_run({second_key: result})
    with runtime.seed.database.transaction() as connection:
        connection.execute(
            """
            UPDATE task_segments SET progress_total = 2, classification_keys_json = ?
            WHERE id = ?
            """,
            (json_text([runtime.seed.key, second_key]), runtime.seed.segment_id),
        )
    runtime.runner._execute_segment = Mock(side_effect=RuntimeError(ERROR))
    _run(runtime)
    saved = runtime.runner._load_checkpoint(runtime.context.checkpoint_path)
    assert set(saved) == {runtime.seed.key, second_key}
    assert saved[runtime.seed.key].model_name == "历史结果"
    assert saved[second_key].model_name == "最新结果"
    segment = _state(runtime)["segments"][runtime.seed.segment_id]
    assert segment["progress_current"] == 2
