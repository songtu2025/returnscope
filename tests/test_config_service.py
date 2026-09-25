from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from web_backend.config_service import ConfigService
from web_backend.database import Database
from web_backend.security import SecretBox

_TEST_API_KEY = "config-service-test-api-key"


def _secret_box() -> SecretBox:
    key = base64.urlsafe_b64encode(
        hashlib.sha256(b"config-service-test-fernet-key").digest()
    ).decode("ascii")
    return SecretBox(key)


def _database(tmp_path: Path) -> Database:
    database = Database(tmp_path / "app.db")
    database.initialize()
    with database.transaction(immediate=True) as connection:
        connection.execute(
            """
            INSERT INTO users(id, email, display_name, password_hash, created_at)
            VALUES ('user-1', 'admin@example.com', '管理员', 'hash',
                    '2026-09-10T00:00:00+00:00')
            """
        )
    return database


def _create_version(
    service: ConfigService,
    **overrides: Any,
) -> dict[str, Any]:
    values: dict[str, Any] = {
        "actor_id": "user-1",
        "name": "测试接入",
        "provider": "responses-compatible",
        "base_url": "https://api.example.com/v1/",
        "api_key": _TEST_API_KEY,
        "primary_model": "primary-model",
        "primary_effort": "medium",
        "cheap_model": "cheap-model",
        "cheap_effort": "low",
        "secondary_model": None,
        "secondary_effort": "high",
        "cheap_audit_percent": 5,
        "requests_per_minute": 60,
        "max_workers": 4,
        "timeout_seconds": 120,
        "change_note": "创建测试配置",
        "connection_id": None,
        "models": [
            {
                "model_key": "primary-model",
                "display_name": "主模型",
                "supported_efforts": ["medium"],
                "active": True,
            }
        ],
    }
    values.update(overrides)
    return service.create_version(**values)


def _table_counts(database: Database) -> dict[str, int]:
    with database.connect() as connection:
        return {
            table: int(
                connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            )
            for table in (
                "api_connections",
                "api_models",
                "api_config_versions",
                "audit_logs",
            )
        }


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
            {"base_url": "ftp://example.com", "primary_model": ""},
            "Base URL 必须是有效的 HTTP 或 HTTPS 地址",
        ),
        (
            {"base_url": "http://example.com", "primary_model": ""},
            "非本地 API 必须使用 HTTPS",
        ),
        (
            {"primary_model": " ", "primary_effort": "invalid"},
            "主模型不能为空",
        ),
        (
            {"primary_effort": "invalid", "cheap_effort": "invalid"},
            "主模型推理强度 仅支持 low、medium、high",
        ),
        (
            {"cheap_effort": "invalid", "secondary_effort": "invalid"},
            "低成本模型推理强度 仅支持 low、medium、high",
        ),
        (
            {"secondary_effort": "invalid", "cheap_audit_percent": -1},
            "二次复核模型推理强度 仅支持 low、medium、high",
        ),
        (
            {"cheap_audit_percent": -1, "requests_per_minute": 0},
            "低成本模型抽检比例必须在 0 到 100 之间",
        ),
        (
            {"requests_per_minute": 0, "max_workers": 0},
            "每分钟请求数必须在 1 到 10000 之间",
        ),
        (
            {"max_workers": 0, "timeout_seconds": 0},
            "单任务并发必须在 1 到 16 之间",
        ),
        (
            {"timeout_seconds": 0, "change_note": ""},
            "请求超时必须在 5 到 600 秒之间",
        ),
        (
            {
                "change_note": " ",
                "models": [
                    {"model_key": "duplicate"},
                    {"model_key": "duplicate"},
                ],
            },
            "请填写配置变更原因",
        ),
        (
            {
                "models": [
                    {"model_key": "duplicate"},
                    {"model_key": "duplicate"},
                ]
            },
            "模型列表中存在重复的模型 ID",
        ),
    ],
)
def test_create_version_preserves_validation_order(
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


def test_create_version_accepts_numeric_boundaries(tmp_path: Path) -> None:
    database = _database(tmp_path)
    service = ConfigService(database, _secret_box())

    lower = _create_version(
        service,
        name="下边界接入",
        cheap_audit_percent=0,
        requests_per_minute=1,
        max_workers=1,
        timeout_seconds=5,
    )
    upper = _create_version(
        service,
        name="上边界接入",
        cheap_audit_percent=100,
        requests_per_minute=10000,
        max_workers=16,
        timeout_seconds=600,
    )

    assert (
        lower["cheap_audit_percent"],
        lower["requests_per_minute"],
        lower["max_workers"],
        lower["timeout_seconds"],
    ) == (0, 1, 1, 5)
    assert (
        upper["cheap_audit_percent"],
        upper["requests_per_minute"],
        upper["max_workers"],
        upper["timeout_seconds"],
    ) == (100, 10000, 16, 600)


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
