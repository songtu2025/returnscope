from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from test_validation_run_service import _build_harness, _create_run

from web_backend.model_services.validation_events import _ValidationItemEvent


@pytest.mark.parametrize("index", (0, 1))
@pytest.mark.parametrize(
    "case",
    (
        ("running", "preparing", "model_started", False),
        ("running", "requesting", "stage", False),
        ("passed", "passed", "model_passed", True),
        ("failed", "failed", "model_failed", True),
    ),
)
def test_item_update_keeps_state_and_event_fields_aligned(
    tmp_path: Path,
    index: int,
    case: tuple[str, str, str, bool],
) -> None:
    status, stage, event_type, completed = case
    harness = _build_harness(tmp_path)
    run_id = str(_create_run(harness, "config", 2)["id"])
    service = harness.service
    service._update_validation_item(
        run_id,
        1 - index,
        {"status": "passed", "stage": "passed"},
        _ValidationItemEvent(event_type="model_passed", message="另一模型已经通过"),
    )
    before = service.get_validation_run(run_id)
    assert before is not None
    message = f"模型 {index} 的 {stage} 事件"
    data = {"duration_ms": 13, "http_status": 401, "suggestion": "合成建议"}
    changes = {"status": status, "stage": stage, "message": message, **data}

    service._update_validation_item(
        run_id,
        index,
        changes,
        _ValidationItemEvent(event_type=event_type, message=message, data=data),
    )
    service._update_validation_item(
        run_id,
        index,
        changes,
        _ValidationItemEvent(event_type=event_type, message=message, data=data),
    )

    result = service.get_validation_run(run_id)
    assert result is not None
    assert result["stage"] == stage
    assert result["completed_count"] == 1 + int(completed)
    assert result["items"][index] == {**before["items"][index], **changes}
    assert result["items"][1 - index] == before["items"][1 - index]
    events = service.validation_events(run_id)
    assert len(events) == 4
    for event in events[-2:]:
        assert event["event_type"] == event_type
        assert event["stage"] == stage
        assert event["message"] == message
        assert event["model_key"] == before["items"][index]["model_key"]
        assert event["data"] == data
        assert event["created_at"]
    assert changes == {"status": status, "stage": stage, "message": message, **data}
    assert data == {"duration_ms": 13, "http_status": 401, "suggestion": "合成建议"}


@pytest.mark.parametrize("data", (None, {}, {"说明": "合成事件数据"}))
def test_event_message_and_data_are_independent_from_item_changes(
    tmp_path: Path, data: dict[str, Any] | None
) -> None:
    harness = _build_harness(tmp_path)
    run_id = str(_create_run(harness, "config", 1)["id"])

    harness.service._update_validation_item(
        run_id,
        0,
        {"stage": "checking", "message": "项目状态消息"},
        _ValidationItemEvent(event_type="stage", message="独立的事件消息", data=data),
    )

    result = harness.service.get_validation_run(run_id)
    assert result is not None
    assert result["items"][0]["message"] == "项目状态消息"
    event = harness.service.validation_events(run_id)[-1]
    assert event["message"] == "独立的事件消息"
    assert event["data"] == (data or {})


def test_saved_stage_callbacks_keep_each_model_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = _build_harness(tmp_path)
    run_id = str(_create_run(harness, "config", 2)["id"])
    callbacks: list[Callable[[str, str, dict[str, Any]], None]] = []
    original_test = harness.probe.test

    def capture_stage(
        config: dict[str, Any],
        model_key: str,
        effort: str,
        on_stage: Callable[[str, str, dict[str, Any]], None],
    ) -> dict[str, Any]:
        callbacks.append(on_stage)
        return original_test(config, model_key, effort, on_stage)

    monkeypatch.setattr(harness.probe, "test", capture_stage)
    harness.service.run_validation(run_id)
    assert len(callbacks) == 2
    callbacks[0]("checking_a", "模型 A 回调", {"probe_marker": "a"})
    callbacks[1]("checking_b", "模型 B 回调", {"probe_marker": "b"})

    result = harness.service.get_validation_run(run_id)
    assert result is not None
    assert result["completed_count"] == 2
    assert [item["probe_marker"] for item in result["items"]] == ["a", "b"]
    assert [item["stage"] for item in result["items"]] == ["checking_a", "checking_b"]
    events = harness.service.validation_events(run_id)[-2:]
    assert [(event["model_key"], event["data"]) for event in events] == [
        ("model-a", {"probe_marker": "a"}),
        ("model-b", {"probe_marker": "b"}),
    ]
    assert [event["message"] for event in events] == ["模型 A 回调", "模型 B 回调"]


@pytest.mark.parametrize(
    "trigger_sql",
    (
        """
        CREATE TRIGGER fail_item_update BEFORE UPDATE ON api_validation_runs
        BEGIN SELECT RAISE(ABORT, 'synthetic update failure'); END
        """,
        """
        CREATE TRIGGER fail_event_insert BEFORE INSERT ON api_validation_events
        BEGIN SELECT RAISE(ABORT, 'synthetic event failure'); END
        """,
    ),
)
def test_item_and_event_writes_roll_back_together(
    tmp_path: Path, trigger_sql: str
) -> None:
    harness = _build_harness(tmp_path)
    run_id = str(_create_run(harness, "config", 2)["id"])
    before = harness.service.get_validation_run(run_id)
    events_before = harness.service.validation_events(run_id)
    with harness.database.transaction() as connection:
        connection.execute(trigger_sql)

    with pytest.raises(sqlite3.IntegrityError, match="synthetic .* failure"):
        harness.service._update_validation_item(
            run_id,
            1,
            {"status": "passed", "stage": "passed", "message": "通过"},
            _ValidationItemEvent(
                event_type="model_passed", message="通过事件", data={"http_status": 200}
            ),
        )

    assert harness.service.get_validation_run(run_id) == before
    assert harness.service.validation_events(run_id) == events_before


def test_missing_run_does_not_write_an_event(tmp_path: Path) -> None:
    harness = _build_harness(tmp_path)

    harness.service._update_validation_item(
        "missing-run",
        0,
        {"stage": "checking"},
        _ValidationItemEvent(event_type="stage", message="合成事件"),
    )

    assert harness.service.get_validation_run("missing-run") is None
    assert harness.service.validation_events("missing-run") == []
