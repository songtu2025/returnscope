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
        base_url="https://second.example.com/",
        models=None,
        change_note="沿用已有密钥",
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
