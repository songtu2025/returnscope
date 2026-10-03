from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from test_config_service import _create_version, _database, _secret_box
from test_validation_run_service import (
    ACTOR_ID,
    CONFIG_VERSION_ID,
    CONNECTION_ID,
    _build_harness,
    _create_run,
)

from web_backend.config_service import ConfigService
from web_backend.model_services.validation_records import _ValidationTarget


@pytest.mark.parametrize("kind", ("model", "config"))
def test_creation_preserves_target_config_and_queued_event(
    tmp_path: Path, kind: str
) -> None:
    harness = _build_harness(tmp_path)
    run = _create_run(harness, kind, 2)

    assert run["kind"] == kind
    assert run["target_id"] == (
        CONFIG_VERSION_ID if kind == "config" else harness.models[0]["id"]
    )
    assert run["connection_id"] == CONNECTION_ID
    assert run["config_version_id"] == CONFIG_VERSION_ID
    assert run["created_by"] == ACTOR_ID
    assert run["endpoint"] == "https://example.test/v1/responses"
    assert run["timeout_seconds"] == 30
    assert run["status"] == run["stage"] == "queued"
    assert run["total_count"] == 2
    assert run["completed_count"] == 0
    assert [item["model_key"] for item in run["items"]] == ["model-a", "model-b"]
    assert [item["effort"] for item in run["items"]] == ["low", "medium"]
    assert all(item["status"] == "pending" for item in run["items"])
    events = harness.service.validation_events(str(run["id"]))
    assert len(events) == 1
    assert events[0]["event_type"] == events[0]["stage"] == "queued"
    assert events[0]["message"] == "验证已进入队列"
    assert events[0]["data"] == {"kind": kind, "total_count": 2}
    assert events[0]["created_at"] == run["created_at"]


@pytest.mark.parametrize("status", ("queued", "running"))
def test_active_target_reuses_run_without_overwriting_snapshot(
    tmp_path: Path, status: str
) -> None:
    harness = _build_harness(tmp_path)
    run_id = str(_create_run(harness, "config", 1)["id"])
    if status == "running":
        assert harness.service._start_validation_run(run_id)
    before = harness.service.get_validation_run(run_id)
    events_before = harness.service.validation_events(run_id)
    harness.config["base_url"] = "https://changed.example.test/v2"
    harness.config["timeout_seconds"] = 90

    reused = _create_run(harness, "config", 3)

    assert reused == before
    assert harness.service.validation_events(run_id) == events_before
    with harness.database.connect() as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM api_validation_runs").fetchone()[0]
            == 1
        )


@pytest.mark.parametrize("changed_field", ("kind", "target_id"))
def test_distinct_kind_or_target_creates_an_independent_run(
    tmp_path: Path, changed_field: str
) -> None:
    harness = _build_harness(tmp_path)
    original = _create_run(harness, "config", 2)
    original_events = harness.service.validation_events(str(original["id"]))
    kind = "model" if changed_field == "kind" else "config"
    target_id = "other-target" if changed_field == "target_id" else CONFIG_VERSION_ID

    created = harness.service._create_validation_run(
        target=_ValidationTarget(
            kind=kind,
            target_id=target_id,
            connection_id=CONNECTION_ID,
            config_version_id=CONFIG_VERSION_ID,
        ),
        actor_id=ACTOR_ID,
        config=harness.config,
        items=original["items"],
    )

    assert created["id"] != original["id"]
    assert created["kind"] == kind
    assert created["target_id"] == target_id
    assert created["items"] == original["items"]
    assert harness.service.get_validation_run(str(original["id"])) == original
    assert harness.service.validation_events(str(original["id"])) == original_events
    assert len(harness.service.validation_events(str(created["id"]))) == 1


@pytest.mark.parametrize("status", ("passed", "failed"))
def test_finished_target_can_create_a_new_validation_run(
    tmp_path: Path, status: str
) -> None:
    harness = _build_harness(
        tmp_path, failure=RuntimeError("合成模型失败") if status == "failed" else None
    )
    run_id = str(_create_run(harness, "model", 1)["id"])
    harness.service.run_validation(run_id)
    finished = harness.service.get_validation_run(run_id)
    assert finished is not None
    assert finished["status"] == status
    finished_events = harness.service.validation_events(run_id)

    created = _create_run(harness, "model", 1)

    assert created["id"] != run_id
    assert created["status"] == created["stage"] == "queued"
    assert created["target_id"] == finished["target_id"]
    assert harness.service.get_validation_run(run_id) == finished
    assert harness.service.validation_events(run_id) == finished_events
    assert len(harness.service.validation_events(str(created["id"]))) == 1


@pytest.mark.parametrize(
    "trigger_sql",
    (
        """
        CREATE TRIGGER fail_run_insert BEFORE INSERT ON api_validation_runs
        BEGIN SELECT RAISE(ABORT, 'synthetic run failure'); END
        """,
        """
        CREATE TRIGGER fail_queue_event BEFORE INSERT ON api_validation_events
        BEGIN SELECT RAISE(ABORT, 'synthetic event failure'); END
        """,
    ),
)
def test_run_and_queue_event_creation_roll_back_together(
    tmp_path: Path, trigger_sql: str
) -> None:
    harness = _build_harness(tmp_path)
    original = _create_run(harness, "model", 1)
    original_events = harness.service.validation_events(str(original["id"]))
    with harness.database.transaction() as connection:
        connection.execute(trigger_sql)

    with pytest.raises(sqlite3.IntegrityError, match="synthetic .* failure"):
        _create_run(harness, "config", 2)

    assert harness.service.get_validation_run(str(original["id"])) == original
    assert harness.service.validation_events(str(original["id"])) == original_events
    with harness.database.connect() as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM api_validation_runs").fetchone()[0]
            == 1
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM api_validation_events").fetchone()[
                0
            ]
            == 1
        )


@pytest.mark.parametrize("kind", ("model", "config"))
def test_public_entry_maps_target_and_configuration_version(
    tmp_path: Path, kind: str
) -> None:
    service = ConfigService(_database(tmp_path), _secret_box())
    first = _create_version(
        service,
        cheap_model="primary-model",
        cheap_effort="medium",
        secondary_model="primary-model",
        secondary_effort="medium",
    )
    latest = _create_version(
        service,
        connection_id=first["connection_id"],
        api_key=" ",
        models=None,
        cheap_model="primary-model",
        cheap_effort="medium",
        secondary_model="primary-model",
        secondary_effort="medium",
    )
    model = service.model_catalog.get_by_key(
        str(first["connection_id"]), "primary-model"
    )
    assert model is not None

    if kind == "model":
        run = service.start_model_validation(str(model["id"]), ACTOR_ID)
        expected_version = latest["id"]
        expected_target = model["id"]
        expected_role = "单模型验证"
    else:
        run = service.start_config_validation(str(first["id"]), ACTOR_ID)
        expected_version = first["id"]
        expected_target = first["id"]
        expected_role = "低成本初筛 / 主分析 / 风险二次复核"

    assert run["kind"] == kind
    assert run["target_id"] == expected_target
    assert run["connection_id"] == first["connection_id"]
    assert run["config_version_id"] == expected_version
    assert run["created_by"] == ACTOR_ID
    assert run["total_count"] == 1
    assert run["items"][0]["model_id"] == model["id"]
    assert run["items"][0]["model_key"] == "primary-model"
    assert run["items"][0]["effort"] == "medium"
    assert run["items"][0]["role"] == expected_role
