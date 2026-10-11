from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from config_service_helpers import (
    _TEST_API_KEY,
    _create_version,
    _database,
    _secret_box,
)

from web_backend.config_service import ConfigService


@pytest.mark.parametrize("method_name", ["validate_model", "start_model_validation"])
@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("missing_model", "模型不存在"),
        ("inactive", "停用模型不能验证"),
        ("invalid_effort", "模型推理强度 仅支持 low、medium、high"),
        ("unsupported_effort", "所选推理强度不在模型支持范围内"),
        ("missing_version", "请先保存 API 接入配置，再验证模型"),
    ],
)
def test_model_validation_preflight_errors_match_both_paths(
    tmp_path: Path,
    method_name: str,
    case: str,
    message: str,
) -> None:
    database = _database(tmp_path)
    service = ConfigService(database, _secret_box())
    _create_version(service)
    with database.connect() as connection:
        model_id = str(
            connection.execute(
                "SELECT id FROM api_models WHERE model_key = 'primary-model'"
            ).fetchone()["id"]
        )
    effort = None
    if case == "missing_model":
        model_id = "missing-model"
    elif case == "inactive":
        service.update_model(model_id, "user-1", "主模型", ["medium"], False)
    elif case == "invalid_effort":
        effort = "ultra"
    elif case == "unsupported_effort":
        effort = "low"
    elif case == "missing_version":
        with database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO api_connections(
                    id, name, provider, created_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    "unconfigured-connection",
                    "未配置接入",
                    "responses-compatible",
                    "user-1",
                    "2026-09-10T00:00:00+00:00",
                    "2026-09-10T00:00:00+00:00",
                ),
            )
        model_id = str(
            service.add_model(
                "unconfigured-connection", "user-1", "new-model", "新模型", ["low"]
            )["id"]
        )
    with pytest.raises(ValueError, match=message):
        getattr(service, method_name)(model_id, "user-1", effort)


def test_model_validation_paths_use_same_default_effort_and_latest_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = _database(tmp_path)
    service = ConfigService(database, _secret_box())
    first = _create_version(service)
    latest = _create_version(
        service,
        connection_id=first["connection_id"],
        api_key=" ",
        models=None,
    )
    model = service.add_model(
        first["connection_id"], "user-1", "fallback-model", "回退模型", ["low", "high"]
    )
    probe_calls: list[tuple[str, str]] = []

    def fake_probe(config: dict[str, Any], model_key: str, effort: str) -> None:
        assert config["id"] == latest["id"]
        assert config["api_key"] == _TEST_API_KEY
        probe_calls.append((model_key, effort))

    monkeypatch.setattr(service.model_probe, "test", fake_probe)
    validated = service.validate_model(str(model["id"]), "user-1")
    queued = service.start_model_validation(str(model["id"]), "user-1")

    assert validated["validation_status"] == "validated"
    assert probe_calls == [("fallback-model", "low")]
    assert queued["config_version_id"] == latest["id"]
    assert queued["items"][0]["effort"] == "low"
