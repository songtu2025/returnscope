import json
from pathlib import Path
from typing import Any

import pytest
from task_execution_helpers import audit_rows
from test_config_service import _create_version, _database, _secret_box

from web_backend.config_service import ConfigService


@pytest.fixture
def lifecycle_service(tmp_path: Path) -> tuple[ConfigService, dict[str, Any]]:
    service = ConfigService(_database(tmp_path), _secret_box())
    return service, _create_version(service)


@pytest.mark.parametrize("repeated_model", (False, True))
def test_validation_keeps_pipeline_order_and_deduplicates_models(
    lifecycle_service, monkeypatch, repeated_model
) -> None:
    service, version = lifecycle_service
    if repeated_model:
        version = _create_version(
            service,
            connection_id=version["connection_id"],
            models=None,
            cheap_model="primary-model",
            cheap_effort="medium",
        )
    calls = []

    def probe(config, model_key, effort):
        calls.append((config["id"], model_key, effort))

    monkeypatch.setattr(service.model_probe, "test", probe)
    result = service.validate(version["id"], "user-1")
    expected = [(version["id"], "primary-model", "medium")]
    if not repeated_model:
        expected.append((version["id"], "cheap-model", "low"))
    assert calls == expected
    assert result["validation_status"] == "validated"
    assert result["validation_message"] == f"连接与 {len(expected)} 个模型均测试通过"
    model_keys = {
        model["model_key"]
        for model in service.list()[0]["models"]
        if model["validation_status"] == "validated"
    }
    assert model_keys == {call[1] for call in expected}
    config_audits = [
        row
        for row in audit_rows(service.database)
        if row["entity_type"] == "api_config_version"
        and row["entity_id"] == version["id"]
    ]
    assert len(config_audits) == 1
    assert json.loads(config_audits[0]["after_json"]) == {
        "status": result["validation_status"],
        "message": result["validation_message"],
    }


@pytest.mark.parametrize("failure_index", (0, 1))
@pytest.mark.parametrize("message", ("合成探测失败", "长" * 620))
def test_validation_stops_on_failure_and_saves_truncated_result(
    lifecycle_service, monkeypatch, failure_index, message
) -> None:
    service, version = lifecycle_service
    calls = []

    def probe(_config, model_key, _effort):
        calls.append(model_key)
        if len(calls) == failure_index + 1:
            raise RuntimeError(message)

    monkeypatch.setattr(service.model_probe, "test", probe)
    with pytest.raises(ValueError) as error:
        service.validate(version["id"], "user-1")
    assert str(error.value) == message[:500]
    assert calls == ["primary-model", "cheap-model"][: failure_index + 1]
    result = service.get_version(version["id"])
    assert result["validation_status"] == "failed"
    assert result["validation_message"] == message[:500]
    assert result["validated_at"]
    models = {model["model_key"]: model for model in service.list()[0]["models"]}
    assert models[calls[-1]]["validation_status"] == "failed"
    assert models[calls[-1]]["validation_message"] == message[:500]
    if failure_index:
        assert models["primary-model"]["validation_status"] == "validated"
    else:
        assert models["cheap-model"]["validation_status"] == "draft"
    config_audits = [
        row
        for row in audit_rows(service.database)
        if row["entity_type"] == "api_config_version"
        and row["entity_id"] == version["id"]
    ]
    assert len(config_audits) == 1
    assert json.loads(config_audits[0]["after_json"]) == {
        "status": result["validation_status"],
        "message": result["validation_message"],
    }


@pytest.mark.parametrize("case", ("missing", "ensure_failure"))
def test_validation_preflight_failure_does_not_save_validation_result(
    lifecycle_service, monkeypatch, case
) -> None:
    service, version = lifecycle_service
    before = service.list()
    audits = audit_rows(service.database)
    calls = []
    monkeypatch.setattr(
        service.model_probe, "test", lambda *_args: calls.append("probe")
    )
    if case == "ensure_failure":

        def fail_ensure(*_args, **_kwargs):
            raise RuntimeError("合成目录校验失败")

        monkeypatch.setattr(
            service.model_catalog, "ensure_pipeline_models", fail_ensure
        )
    with pytest.raises(ValueError if case == "missing" else RuntimeError):
        service.validate(
            "missing-version" if case == "missing" else version["id"], "user-1"
        )
    assert calls == []
    assert service.list() == before
    assert audit_rows(service.database) == audits


def test_publish_is_idempotent_after_successful_validation(
    lifecycle_service, monkeypatch
) -> None:
    service, version = lifecycle_service
    monkeypatch.setattr(service.model_probe, "test", lambda *_args: None)
    service.validate(version["id"], "user-1")
    first = service.publish(version["id"], "user-1")
    audits = audit_rows(service.database)
    second = service.publish(version["id"], "user-1")
    assert second == first
    assert first["published_at"]
    assert audit_rows(service.database) == audits


def test_discard_removes_draft_after_failed_validation(
    lifecycle_service, monkeypatch
) -> None:
    service, version = lifecycle_service

    def fail_probe(*_args):
        raise RuntimeError("合成失败")

    monkeypatch.setattr(service.model_probe, "test", fail_probe)
    with pytest.raises(ValueError, match="合成失败"):
        service.validate(version["id"], "user-1")
    result = service.discard_draft(version["id"], "user-1")
    assert result["id"] == version["id"]
    assert service.get_version(version["id"]) is None
    discards = [
        row for row in audit_rows(service.database) if row["action"] == "discard_draft"
    ]
    assert len(discards) == 1
    assert discards[0]["entity_id"] == version["connection_id"]
