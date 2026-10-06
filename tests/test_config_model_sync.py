from pathlib import Path
from typing import Any

import pytest
from task_execution_helpers import audit_rows, trace_queries
from test_config_service import _create_version, _database, _secret_box

from web_backend.config_service import ConfigService


@pytest.fixture
def sync_service(tmp_path: Path) -> tuple[ConfigService, dict[str, Any]]:
    service = ConfigService(_database(tmp_path), _secret_box())
    return service, _create_version(service)


@pytest.mark.parametrize(
    "scenario",
    [
        ("same", ["primary-model", "cheap-model"], [], 0, 5),
        ("add", ["primary-model", "cheap-model", "new-model"], [], 1, 8),
        ("reactivate", ["primary-model", "cheap-model"], [], 1, 7),
        ("deactivate", ["primary-model"], ["cheap-model"], 1, 7),
        ("empty", [], ["primary-model", "cheap-model"], 2, 9),
        ("duplicate", ["primary-model", "primary-model", "cheap-model"], [], 0, 5),
    ],
)
def test_sync_applies_catalog_delta_with_original_query_budget(
    sync_service, monkeypatch, scenario
) -> None:
    case, keys, inactive, audit_delta, selects = scenario
    service, version = sync_service
    if case == "reactivate":
        model = service.model_catalog.get_by_key(
            version["connection_id"], "primary-model"
        )
        service.update_model(model["id"], "user-1", "主模型", ["medium"], False)
    calls = []

    def list_models(config):
        calls.append(config["id"])
        return keys

    monkeypatch.setattr(service.model_probe, "list_models", list_models)
    audit_before = len(audit_rows(service.database))
    queries = trace_queries(service.database, monkeypatch)
    result = service.sync_models_from_provider(version["connection_id"], "user-1")
    assert sum(query.lstrip().startswith("SELECT") for query in queries) == selects
    assert result == {"model_keys": keys, "count": len(keys)}
    assert calls == [version["id"]]
    models = service.list()[0]["models"]
    assert sorted(
        model["model_key"] for model in models if not model["active"]
    ) == sorted(inactive)
    assert len(models) == 2 + int(case == "add")
    assert len(audit_rows(service.database)) - audit_before == audit_delta
    if case == "add":
        new = next(model for model in models if model["model_key"] == "new-model")
        assert new["supported_efforts"] == ["low", "medium", "high"]
        assert new["display_name"] == "new-model"


def test_duplicate_new_provider_key_keeps_first_committed_model(
    sync_service, monkeypatch
) -> None:
    service, version = sync_service
    monkeypatch.setattr(
        service.model_probe, "list_models", lambda _config: ["new-model", "new-model"]
    )
    audit_before = len(audit_rows(service.database))
    with pytest.raises(ValueError, match="该模型 ID 已存在"):
        service.sync_models_from_provider(version["connection_id"], "user-1")
    models = service.list()[0]["models"]
    assert {model["model_key"] for model in models} == {
        "new-model",
        "primary-model",
        "cheap-model",
    }
    assert all(model["active"] for model in models)
    assert len(audit_rows(service.database)) == audit_before + 1


@pytest.mark.parametrize(
    ("case", "message", "provider_called"),
    [
        ("missing_version", "请先保存 API 接入配置，再读取模型目录", False),
        ("missing_config", "API 配置不存在", False),
        ("missing_connection", "API 接入不存在", True),
        ("provider_failure", "合成提供方失败", True),
    ],
)
def test_sync_error_priority_keeps_provider_calls_and_existing_rows(
    sync_service, monkeypatch, case, message, provider_called
) -> None:
    service, version = sync_service
    before = service.list()
    audit_before = audit_rows(service.database)
    calls = []

    def list_models(_config):
        calls.append("provider")
        if case == "provider_failure":
            raise RuntimeError(message)
        return []

    monkeypatch.setattr(service.model_probe, "list_models", list_models)
    connection_id = version["connection_id"]
    if case == "missing_version":
        connection_id = "missing-connection"
    elif case == "missing_config":
        monkeypatch.setattr(service, "get_version", lambda *_args, **_kwargs: None)
    elif case == "missing_connection":
        monkeypatch.setattr(service, "list", lambda: [])
    with pytest.raises(
        RuntimeError if case == "provider_failure" else ValueError, match=message
    ):
        service.sync_models_from_provider(connection_id, "user-1")
    assert bool(calls) == provider_called
    assert ConfigService.list(service) == before
    assert audit_rows(service.database) == audit_before
