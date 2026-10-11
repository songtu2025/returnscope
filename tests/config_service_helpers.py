from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from typing import Any

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
