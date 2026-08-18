from __future__ import annotations

from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from web_backend.app import create_app
from web_backend.security import utc_now
from web_backend.settings import Settings


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "runtime",
        database_path=tmp_path / "runtime" / "app.db",
        session_days=14,
        task_workers=1,
        bootstrap_email="admin@example.com",
        bootstrap_name="管理员",
        bootstrap_password="test-password-123",
        encryption_key=Fernet.generate_key().decode("ascii"),
        secure_cookies=False,
    )


def _connection_payload() -> dict[str, object]:
    return {
        "name": "测试模型服务",
        "provider": "responses-compatible",
        "base_url": "https://models.example.com",
        "api_key": "test-key",
        "primary_model": "test-model",
        "primary_effort": "medium",
        "cheap_model": None,
        "cheap_effort": "low",
        "secondary_model": None,
        "secondary_effort": "high",
        "cheap_audit_percent": 5,
        "requests_per_minute": 60,
        "max_workers": 4,
        "timeout_seconds": 120,
        "change_note": "创建测试接入",
        "models": [
            {
                "model_key": "test-model",
                "display_name": "测试模型",
                "supported_efforts": ["low", "medium", "high"],
                "active": True,
            }
        ],
    }


def test_model_preference_is_personal_and_model_service_is_admin_only(
    tmp_path: Path,
) -> None:
    app = create_app(start_worker=False, settings_override=_settings(tmp_path))
    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "test-password-123"},
        )
        assert login.status_code == 200
        assert login.json()["is_admin"] is True

        created = client.post("/api/configs", json=_connection_payload())
        assert created.status_code == 201, created.text
        config = created.json()
        database = app.state.database
        with database.transaction(immediate=True) as connection:
            connection.execute(
                """
                UPDATE api_config_versions
                SET validation_status = 'validated', validated_at = ?, published_at = ?
                WHERE id = ?
                """,
                (utc_now(), utc_now(), config["id"]),
            )
            connection.execute(
                """
                UPDATE api_models
                SET validation_status = 'validated', validated_at = ?
                WHERE connection_id = ?
                """,
                (utc_now(), config["connection_id"]),
            )
            connection.execute(
                """
                UPDATE api_connections
                SET active_version_id = ?
                WHERE id = ?
                """,
                (config["id"], config["connection_id"]),
            )

        created_user = client.post(
            "/api/users",
            json={
                "email": "member@example.com",
                "display_name": "普通成员",
                "password": "member-password-123",
            },
        )
        assert created_user.status_code == 201, created_user.text
        client.post("/api/auth/logout")
        member_login = client.post(
            "/api/auth/login",
            json={"email": "member@example.com", "password": "member-password-123"},
        )
        assert member_login.status_code == 200
        assert member_login.json()["is_admin"] is False

        denied = client.post(
            f"/api/connections/{config['connection_id']}/models",
            json={
                "model_key": "other-model",
                "display_name": "其他模型",
                "supported_efforts": ["medium"],
                "active": True,
            },
        )
        assert denied.status_code == 403

        preference = {
            "connection_id": config["connection_id"],
            "cheap_model": None,
            "cheap_effort": "low",
            "primary_model": "test-model",
            "primary_effort": "medium",
            "secondary_model": None,
            "secondary_effort": "high",
            "cheap_audit_percent": 8,
        }
        saved = client.put("/api/model-preferences/me", json=preference)
        assert saved.status_code == 200, saved.text
        assert saved.json()["config_version_id"] == config["id"]
        assert saved.json()["cheap_audit_percent"] == 8
        assert (
            client.get("/api/model-preferences/me").json()["primary_model"]
            == "test-model"
        )
