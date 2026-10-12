from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from config_service_helpers import (
    _TEST_API_KEY,
    _create_version,
    _database,
    _secret_box,
    _table_counts,
)

from web_backend.config_service import ConfigService


def test_create_version_creates_connection_models_version_and_audit(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    secret_box = _secret_box()
    service = ConfigService(database, secret_box)

    result = _create_version(service, provider=" ")

    assert result["version"] == 1
    assert result["base_url"] == "https://api.example.com/v1"
    assert result["validation_status"] == "draft"
    assert result["primary_model"] == "primary-model"
    assert result["cheap_model"] == "cheap-model"
    assert set(result) >= {
        "id",
        "connection_id",
        "connection_name",
        "provider",
        "api_key_masked",
        "created_at",
    }

    with database.connect() as connection:
        saved_connection = connection.execute(
            "SELECT * FROM api_connections WHERE id = ?",
            (result["connection_id"],),
        ).fetchone()
        saved_version = connection.execute(
            "SELECT * FROM api_config_versions WHERE id = ?",
            (result["id"],),
        ).fetchone()
        model_rows = connection.execute(
            """
            SELECT model_key, display_name, supported_efforts_json
            FROM api_models WHERE connection_id = ? ORDER BY model_key
            """,
            (result["connection_id"],),
        ).fetchall()
        audit = connection.execute(
            """
            SELECT action, after_json FROM audit_logs
            WHERE entity_type = 'api_connection' AND entity_id = ?
            """,
            (result["connection_id"],),
        ).fetchone()

    assert saved_connection["provider"] == "responses-compatible"
    assert [row["model_key"] for row in model_rows] == [
        "cheap-model",
        "primary-model",
    ]
    assert model_rows[0]["display_name"] == "cheap-model"
    assert json.loads(model_rows[0]["supported_efforts_json"]) == [
        "low",
        "medium",
        "high",
    ]
    ciphertext = str(saved_version["api_key_ciphertext"])
    actual_digest = hashlib.sha256(secret_box.decrypt(ciphertext).encode()).digest()
    expected_digest = hashlib.sha256(_TEST_API_KEY.encode()).digest()
    assert actual_digest == expected_digest
    assert audit["action"] == "create_version"
    assert json.loads(audit["after_json"]) == {
        "note": "创建测试配置",
        "version": 1,
        "version_id": result["id"],
        "name": result["connection_name"],
        "base_url": result["base_url"],
        "primary_model": result["primary_model"],
        "primary_effort": result["primary_effort"],
        "requests_per_minute": result["requests_per_minute"],
        "max_workers": result["max_workers"],
        "timeout_seconds": result["timeout_seconds"],
        "key_updated": True,
    }


def test_initialize_restores_legacy_models_without_duplicates(tmp_path: Path) -> None:
    database = _database(tmp_path)
    result = _create_version(ConfigService(database, _secret_box()))
    with database.transaction() as connection:
        connection.execute(
            "DELETE FROM api_models WHERE connection_id = ?",
            (result["connection_id"],),
        )

    database.initialize()
    database.initialize()

    with database.connect() as connection:
        model_keys = [
            row["model_key"]
            for row in connection.execute(
                "SELECT model_key FROM api_models WHERE connection_id = ? ORDER BY model_key",
                (result["connection_id"],),
            ).fetchall()
        ]
    assert model_keys == ["cheap-model", "primary-model"]


def test_blank_reason_is_generated_for_creation_and_key_update(tmp_path: Path) -> None:
    database = _database(tmp_path)
    service = ConfigService(database, _secret_box())
    first = _create_version(service, change_note="")
    assert first["change_note"] == "新增模型服务"
    updated = _create_version(
        service,
        connection_id=first["connection_id"],
        api_key="synthetic-new-api-key",
        models=None,
        change_note="",
    )
    assert updated["change_note"] == "更新模型服务配置及密钥"
    with database.connect() as connection:
        after = json.loads(
            connection.execute(
                "SELECT after_json FROM audit_logs WHERE entity_id = ? ORDER BY rowid DESC LIMIT 1",
                (first["connection_id"],),
            ).fetchone()["after_json"]
        )
    assert after["key_updated"] is True
    assert "api_key" not in after and "api_key_ciphertext" not in after


def test_existing_connection_inherits_ciphertext_and_increments_version(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    service = ConfigService(database, _secret_box())
    first = _create_version(service)

    second = _create_version(
        service,
        connection_id=first["connection_id"],
        api_key=" ",
        name="调整后的模型服务",
        base_url="https://second.example.com/",
        models=None,
        change_note="",
    )

    with database.connect() as connection:
        versions = connection.execute(
            """
            SELECT version, api_key_ciphertext FROM api_config_versions
            WHERE connection_id = ? ORDER BY version
            """,
            (first["connection_id"],),
        ).fetchall()
        audit_count = connection.execute(
            """
            SELECT COUNT(*) FROM audit_logs
            WHERE entity_type = 'api_connection' AND entity_id = ?
                  AND action = 'create_version'
            """,
            (first["connection_id"],),
        ).fetchone()[0]

    assert second["version"] == 2
    assert second["connection_name"] == "调整后的模型服务"
    assert second["change_note"] == "更新模型服务配置"
    with database.connect() as connection:
        audit = connection.execute(
            "SELECT before_json, after_json FROM audit_logs WHERE action = 'create_version' AND entity_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 1",
            (first["connection_id"],),
        ).fetchone()
    before, after = json.loads(audit["before_json"]), json.loads(audit["after_json"])
    assert before["name"] == first["connection_name"]
    assert before["base_url"] == first["base_url"]
    assert after["name"] == "调整后的模型服务"
    assert after["base_url"] == second["base_url"]
    assert after["key_updated"] is False
    assert "api_key" not in before and "api_key_ciphertext" not in after
    assert second["base_url"] == "https://second.example.com"
    assert [row["version"] for row in versions] == [1, 2]
    assert versions[0]["api_key_ciphertext"] == versions[1]["api_key_ciphertext"]
    assert audit_count == 2


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {"name": " ", "api_key": ""},
            "接入名称不能为空",
        ),
        (
            {"api_key": ""},
            "API 密钥不能为空",
        ),
    ],
)
def test_new_connection_errors_roll_back_transaction(
    tmp_path: Path,
    overrides: dict[str, Any],
    message: str,
) -> None:
    database = _database(tmp_path)
    service = ConfigService(database, _secret_box())

    with pytest.raises(ValueError) as error:
        _create_version(service, **overrides)

    assert str(error.value) == message
    assert _table_counts(database) == {
        "api_connections": 0,
        "api_models": 0,
        "api_config_versions": 0,
        "audit_logs": 0,
    }


def test_existing_connection_rejects_embedded_model_definitions(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    service = ConfigService(database, _secret_box())
    first = _create_version(service)

    with pytest.raises(ValueError) as error:
        _create_version(
            service,
            connection_id=first["connection_id"],
            api_key="",
            models=[{"model_key": "new-model"}],
        )

    assert str(error.value) == "已有接入请通过模型列表单独维护模型"
    assert _table_counts(database) == {
        "api_connections": 1,
        "api_models": 2,
        "api_config_versions": 1,
        "audit_logs": 1,
    }


def test_create_version_transaction_failure_leaves_no_partial_rows(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    service = ConfigService(database, _secret_box())
    with database.transaction(immediate=True) as connection:
        connection.execute(
            """
            CREATE TRIGGER fail_config_version_insert
            BEFORE INSERT ON api_config_versions
            BEGIN
                SELECT RAISE(ABORT, 'forced config version failure');
            END
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="forced config version failure"):
        _create_version(service)

    assert _table_counts(database) == {
        "api_connections": 0,
        "api_models": 0,
        "api_config_versions": 0,
        "audit_logs": 0,
    }
