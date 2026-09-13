from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from web_backend.database import Database
from web_backend.model_probe import ModelValidationError
from web_backend.validation_run_service import ValidationRunService

ACTOR_ID = "user-1"
CONNECTION_ID = "connection-1"
CONFIG_VERSION_ID = "config-1"
CREATED_AT = "2026-09-10T00:00:00+00:00"


class FakeModelCatalog:
    def __init__(self, models: list[dict[str, Any]]) -> None:
        self.models = {str(model["id"]): model for model in models}
        self.validation_updates: list[tuple[str, str, str, str]] = []

    def get(self, model_id: str) -> dict[str, Any] | None:
        return self.models.get(model_id)

    def set_validation(
        self,
        model: dict[str, Any],
        status: str,
        message: str,
        actor_id: str,
    ) -> None:
        self.validation_updates.append((str(model["id"]), status, message, actor_id))


class FakeModelProbe:
    def __init__(self, failure: Exception | None = None) -> None:
        self.failure = failure
        self.calls: list[tuple[str, str]] = []

    def test(
        self,
        config: dict[str, Any],
        model_key: str,
        effort: str,
        on_stage: Callable[[str, str, dict[str, Any]], None],
    ) -> dict[str, Any]:
        assert config["api_key"] == "test-api-key"
        self.calls.append((model_key, effort))
        on_stage(
            "requesting",
            "正在请求模型响应",
            {"request_sent": True},
        )
        if self.failure is not None:
            raise self.failure
        return {
            "duration_ms": 25,
            "http_status": 200,
            "response_model": f"{model_key}-response",
        }


class FakeGetVersion:
    def __init__(self, config: dict[str, Any] | None) -> None:
        self.config = config
        self.calls: list[tuple[str, bool]] = []

    def __call__(
        self,
        version_id: str,
        include_secret: bool = False,
    ) -> dict[str, Any] | None:
        self.calls.append((version_id, include_secret))
        return self.config


@dataclass
class ValidationHarness:
    database: Database
    service: ValidationRunService
    catalog: FakeModelCatalog
    probe: FakeModelProbe
    get_version: FakeGetVersion
    config: dict[str, Any]
    models: list[dict[str, Any]]


def _build_harness(
    tmp_path: Path,
    failure: Exception | None = None,
    config_available: bool = True,
) -> ValidationHarness:
    database = Database(tmp_path / "app.db")
    database.initialize()
    config = {
        "id": CONFIG_VERSION_ID,
        "connection_id": CONNECTION_ID,
        "base_url": "https://example.test/v1",
        "api_key": "test-api-key",
        "timeout_seconds": 30,
    }
    models = [
        {
            "id": f"model-{index}",
            "model_key": f"model-{key}",
            "display_name": f"测试模型 {index}",
            "effort": effort,
        }
        for index, (key, effort) in enumerate(
            [("a", "low"), ("b", "medium"), ("c", "high")],
            start=1,
        )
    ]
    with database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO users(
                id, email, display_name, password_hash, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (ACTOR_ID, "tester@example.test", "测试用户", "hash", CREATED_AT),
        )
        connection.execute(
            """
            INSERT INTO api_connections(
                id, name, provider, created_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                CONNECTION_ID,
                "测试连接",
                "openai-compatible",
                ACTOR_ID,
                CREATED_AT,
                CREATED_AT,
            ),
        )
        connection.execute(
            """
            INSERT INTO api_config_versions(
                id, connection_id, version, base_url, api_key_ciphertext,
                primary_model, primary_effort, created_by, created_at
            ) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?)
            """,
            (
                CONFIG_VERSION_ID,
                CONNECTION_ID,
                config["base_url"],
                "ciphertext",
                models[0]["model_key"],
                models[0]["effort"],
                ACTOR_ID,
                CREATED_AT,
            ),
        )
    catalog = FakeModelCatalog(models)
    probe = FakeModelProbe(failure)
    get_version = FakeGetVersion(config if config_available else None)
    service = ValidationRunService(database, catalog, probe, get_version)
    return ValidationHarness(
        database,
        service,
        catalog,
        probe,
        get_version,
        config,
        models,
    )


def _create_run(
    harness: ValidationHarness,
    kind: str,
    item_count: int,
) -> dict[str, Any]:
    items = [
        harness.service._validation_item(
            model,
            str(model["effort"]),
            f"模型 {index}",
        )
        for index, model in enumerate(harness.models[:item_count], start=1)
    ]
    target_id = CONFIG_VERSION_ID if kind == "config" else str(items[0]["model_id"])
    return harness.service._create_validation_run(
        kind=kind,
        target_id=target_id,
        connection_id=CONNECTION_ID,
        config_version_id=CONFIG_VERSION_ID,
        actor_id=ACTOR_ID,
        config=harness.config,
        items=items,
    )


def test_config_validation_all_models_pass(tmp_path: Path) -> None:
    harness = _build_harness(tmp_path)
    run = _create_run(harness, "config", 2)

    harness.service.run_validation(str(run["id"]))

    result = harness.service.get_validation_run(str(run["id"]))
    assert result is not None
    assert result["status"] == "passed"
    assert result["stage"] == "passed"
    assert result["completed_count"] == 2
    assert result["error_category"] is None
    assert result["error_message"] is None
    assert result["suggestion"] is None
    assert result["started_at"]
    assert result["completed_at"]
    assert [item["status"] for item in result["items"]] == ["passed", "passed"]
    assert [item["stage"] for item in result["items"]] == ["passed", "passed"]
    assert [item["duration_ms"] for item in result["items"]] == [25, 25]
    assert [item["http_status"] for item in result["items"]] == [200, 200]
    assert [item["response_model"] for item in result["items"]] == [
        "model-a-response",
        "model-b-response",
    ]
    assert all(item["started_at"] for item in result["items"])
    assert all(item["completed_at"] for item in result["items"])
    assert all(item["request_sent"] is True for item in result["items"])
    assert all(item["message"] == "模型响应与结构检查通过" for item in result["items"])

    events = harness.service.validation_events(str(run["id"]))
    assert [event["event_type"] for event in events] == [
        "queued",
        "started",
        "model_started",
        "stage",
        "model_passed",
        "model_started",
        "stage",
        "model_passed",
        "completed",
    ]
    assert [event["message"] for event in events] == [
        "验证已进入队列",
        "开始执行真实模型验证",
        "正在检查模型与连接配置",
        "正在请求模型响应",
        "模型响应与结构检查通过",
        "正在检查模型与连接配置",
        "正在请求模型响应",
        "模型响应与结构检查通过",
        "全部模型验证通过",
    ]
    assert [event["model_key"] for event in events[2:8]] == [
        "model-a",
        "model-a",
        "model-a",
        "model-b",
        "model-b",
        "model-b",
    ]
    assert events[3]["data"] == {"request_sent": True}
    assert events[4]["data"] == {
        "duration_ms": 25,
        "http_status": 200,
        "response_model": "model-a-response",
    }
    assert harness.probe.calls == [("model-a", "low"), ("model-b", "medium")]
    assert harness.get_version.calls == [(CONFIG_VERSION_ID, True)]
    assert harness.catalog.validation_updates == [
        (
            "model-1",
            "validated",
            "HTTP 200 · 25 ms · 使用 low 推理强度测试通过",
            ACTOR_ID,
        ),
        (
            "model-2",
            "validated",
            "HTTP 200 · 25 ms · 使用 medium 推理强度测试通过",
            ACTOR_ID,
        ),
    ]
    with harness.database.connect() as connection:
        config_state = connection.execute(
            """
            SELECT validation_status, validation_message, validated_at
            FROM api_config_versions WHERE id = ?
            """,
            (CONFIG_VERSION_ID,),
        ).fetchone()
        audit = connection.execute(
            """
            SELECT entity_type, entity_id, action, after_json, actor_id
            FROM audit_logs
            """
        ).fetchone()
    assert dict(config_state) == {
        "validation_status": "validated",
        "validation_message": "连接与 2 个模型均测试通过",
        "validated_at": config_state["validated_at"],
    }
    assert config_state["validated_at"]
    assert audit["entity_type"] == "api_config_version"
    assert audit["entity_id"] == CONFIG_VERSION_ID
    assert audit["action"] == "validate"
    assert audit["actor_id"] == ACTOR_ID
    assert json.loads(audit["after_json"]) == {
        "status": "validated",
        "message": "连接与 2 个模型均测试通过",
    }


@pytest.mark.parametrize(
    "failure_case",
    [
        (
            ModelValidationError(
                "API Key 无效",
                "authentication",
                "请检查 API Key",
                401,
            ),
            "authentication",
            "请检查 API Key",
            401,
        ),
        (
            RuntimeError("底层调用失败"),
            "unknown",
            "请检查模型配置后重新验证",
            None,
        ),
    ],
)
def test_first_failure_skips_remaining_models(
    tmp_path: Path,
    failure_case: tuple[Exception, str, str, int | None],
) -> None:
    failure, category, suggestion, http_status = failure_case
    harness = _build_harness(tmp_path, failure=failure)
    run = _create_run(harness, "config", 3)

    harness.service.run_validation(str(run["id"]))

    result = harness.service.get_validation_run(str(run["id"]))
    assert result is not None
    assert result["status"] == "failed"
    assert result["stage"] == "failed"
    assert result["completed_count"] == 1
    assert result["error_category"] == category
    assert result["error_message"] == str(failure)
    assert result["suggestion"] == suggestion
    assert result["started_at"]
    assert result["completed_at"]
    failed_item, *skipped_items = result["items"]
    assert failed_item["status"] == "failed"
    assert failed_item["stage"] == "failed"
    assert failed_item["message"] == str(failure)
    assert failed_item["http_status"] == http_status
    assert failed_item["error_category"] == category
    assert failed_item["suggestion"] == suggestion
    assert failed_item["duration_ms"] >= 0
    assert failed_item["started_at"]
    assert failed_item["completed_at"]
    assert failed_item["request_sent"] is True
    assert [item["status"] for item in skipped_items] == ["skipped", "skipped"]
    assert [item["stage"] for item in skipped_items] == ["skipped", "skipped"]
    assert all(
        item["message"] == "前序模型验证失败，已停止后续验证" for item in skipped_items
    )
    assert all(item["started_at"] is None for item in skipped_items)
    assert all(item["completed_at"] is None for item in skipped_items)

    events = harness.service.validation_events(str(run["id"]))
    assert [event["event_type"] for event in events] == [
        "queued",
        "started",
        "model_started",
        "stage",
        "model_failed",
        "model_skipped",
        "model_skipped",
        "failed",
    ]
    assert events[4]["message"] == str(failure)
    assert events[4]["data"]["duration_ms"] == failed_item["duration_ms"]
    assert events[4]["data"]["http_status"] == http_status
    assert events[4]["data"]["error_category"] == category
    assert events[4]["data"]["suggestion"] == suggestion
    assert [event["model_key"] for event in events[5:7]] == [
        "model-b",
        "model-c",
    ]
    assert events[-1]["message"] == str(failure)
    assert events[-1]["data"] == {
        "error_category": category,
        "suggestion": suggestion,
    }
    assert harness.probe.calls == [("model-a", "low")]
    assert harness.catalog.validation_updates == [
        ("model-1", "failed", str(failure), ACTOR_ID)
    ]
    with harness.database.connect() as connection:
        config_state = connection.execute(
            """
            SELECT validation_status, validation_message, validated_at
            FROM api_config_versions WHERE id = ?
            """,
            (CONFIG_VERSION_ID,),
        ).fetchone()
        audit = connection.execute("SELECT after_json FROM audit_logs").fetchone()
    assert config_state["validation_status"] == "failed"
    assert config_state["validation_message"] == str(failure)
    assert config_state["validated_at"]
    assert json.loads(audit["after_json"]) == {
        "status": "failed",
        "message": str(failure),
    }


def test_missing_config_finishes_run_without_starting_items(tmp_path: Path) -> None:
    harness = _build_harness(tmp_path, config_available=False)
    run = _create_run(harness, "config", 2)

    harness.service.run_validation(str(run["id"]))

    result = harness.service.get_validation_run(str(run["id"]))
    assert result is not None
    assert result["status"] == "failed"
    assert result["stage"] == "failed"
    assert result["error_category"] == "config_missing"
    assert result["error_message"] == "API 配置不存在"
    assert result["suggestion"] == "请重新保存 API 接入配置"
    assert result["completed_count"] == 0
    assert [item["status"] for item in result["items"]] == ["pending", "pending"]
    assert [
        event["event_type"]
        for event in harness.service.validation_events(str(run["id"]))
    ] == ["queued", "started", "failed"]
    assert harness.get_version.calls == [(CONFIG_VERSION_ID, True)]
    assert harness.probe.calls == []
    assert harness.catalog.validation_updates == []
    with harness.database.connect() as connection:
        config_state = connection.execute(
            """
            SELECT validation_status, validation_message, validated_at
            FROM api_config_versions WHERE id = ?
            """,
            (CONFIG_VERSION_ID,),
        ).fetchone()
        audit_count = connection.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[
            0
        ]
    assert dict(config_state) == {
        "validation_status": "draft",
        "validation_message": "",
        "validated_at": None,
    }
    assert audit_count == 0


def test_completed_model_validation_is_not_processed_twice(tmp_path: Path) -> None:
    harness = _build_harness(tmp_path)
    run = _create_run(harness, "model", 1)

    harness.service.run_validation(str(run["id"]))
    first_result = harness.service.get_validation_run(str(run["id"]))
    first_events = harness.service.validation_events(str(run["id"]))
    first_calls = list(harness.probe.calls)
    first_updates = list(harness.catalog.validation_updates)

    harness.service.run_validation(str(run["id"]))

    assert harness.service.get_validation_run(str(run["id"])) == first_result
    assert harness.service.validation_events(str(run["id"])) == first_events
    assert harness.probe.calls == first_calls == [("model-a", "low")]
    assert (
        harness.catalog.validation_updates
        == first_updates
        == [
            (
                "model-1",
                "validated",
                "HTTP 200 · 25 ms · 使用 low 推理强度测试通过",
                ACTOR_ID,
            )
        ]
    )
    assert harness.get_version.calls == [(CONFIG_VERSION_ID, True)]
    with harness.database.connect() as connection:
        config_state = connection.execute(
            """
            SELECT validation_status, validation_message, validated_at
            FROM api_config_versions WHERE id = ?
            """,
            (CONFIG_VERSION_ID,),
        ).fetchone()
        audit_count = connection.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[
            0
        ]
    assert dict(config_state) == {
        "validation_status": "draft",
        "validation_message": "",
        "validated_at": None,
    }
    assert audit_count == 0


def test_claim_failure_returns_without_loading_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _build_harness(tmp_path)
    run = _create_run(harness, "model", 1)
    monkeypatch.setattr(
        harness.service,
        "_start_validation_run",
        lambda _run_id: False,
    )

    harness.service.run_validation(str(run["id"]))

    result = harness.service.get_validation_run(str(run["id"]))
    assert result is not None
    assert result["status"] == "queued"
    assert [
        event["event_type"]
        for event in harness.service.validation_events(str(run["id"]))
    ] == ["queued"]
    assert harness.get_version.calls == []
    assert harness.probe.calls == []
    assert harness.catalog.validation_updates == []
