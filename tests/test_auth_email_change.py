from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from test_auth_flows import FakeMailSender, _login_admin, _settings, _token_from_url


def test_email_change_verifies_new_address_and_preserves_user_id(
    tmp_path: Path,
) -> None:
    from web_backend.app import create_app

    sender = FakeMailSender()
    settings = _settings(tmp_path)
    app = create_app(
        start_worker=False,
        settings_override=settings,
        mail_sender_override=sender,
    )

    with TestClient(app) as client:
        _login_admin(client)
        original_user_id = client.get("/api/auth/me").json()["id"]
        requested = client.post(
            "/api/auth/email-change/request",
            json={
                "current_password": "test-password-123",
                "new_email": "WCH@SeekwayGroup.com",
            },
        )
        assert requested.status_code == 204
        assert sender.email_changes[0]["email"] == "wch@seekwaygroup.com"
        raw_token = _token_from_url(sender.email_changes[0]["url"])
        assert sender.email_changes[0]["url"].startswith(
            "https://feedback.example.com/#change-email?token="
        )

        validated = client.post(
            "/api/auth/email-change/validate",
            json={"token": raw_token},
        )
        assert validated.status_code == 200
        assert validated.json()["email"] == "wch@seekwaygroup.com"

        completed = client.post(
            "/api/auth/email-change/complete",
            json={"token": raw_token},
        )
        assert completed.status_code == 204
        assert client.get("/api/auth/me").status_code == 401
        assert (
            client.post(
                "/api/auth/login",
                json={
                    "email": "admin@example.com",
                    "password": "test-password-123",
                },
            ).status_code
            == 401
        )
        login = client.post(
            "/api/auth/login",
            json={
                "email": "wch@seekwaygroup.com",
                "password": "test-password-123",
            },
        )
        assert login.status_code == 200
        assert login.json()["id"] == original_user_id
        assert (
            client.post(
                "/api/auth/email-change/complete",
                json={"token": raw_token},
            ).status_code
            == 400
        )

        with app.state.database.connect() as connection:
            users = connection.execute(
                "SELECT id, email FROM users ORDER BY created_at"
            ).fetchall()
            audit = connection.execute(
                """
                SELECT action FROM audit_logs
                WHERE entity_type = 'user' AND entity_id = ?
                ORDER BY created_at DESC
                """,
                (original_user_id,),
            ).fetchall()
        assert [dict(row) for row in users] == [
            {"id": original_user_id, "email": "wch@seekwaygroup.com"}
        ]
        assert "change_email" in {row["action"] for row in audit}


def test_email_change_rejects_invalid_password_and_reserved_email(
    tmp_path: Path,
) -> None:
    from web_backend.app import create_app

    sender = FakeMailSender()
    app = create_app(
        start_worker=False,
        settings_override=_settings(tmp_path),
        mail_sender_override=sender,
    )

    with TestClient(app) as client:
        _login_admin(client)
        wrong_password = client.post(
            "/api/auth/email-change/request",
            json={
                "current_password": "wrong-password",
                "new_email": "wch@seekwaygroup.com",
            },
        )
        assert wrong_password.status_code == 400
        assert sender.email_changes == []

        invited = client.post(
            "/api/invitations",
            json={"email": "reserved@example.com"},
        )
        assert invited.status_code == 201
        reserved = client.post(
            "/api/auth/email-change/request",
            json={
                "current_password": "test-password-123",
                "new_email": "reserved@example.com",
            },
        )
        assert reserved.status_code == 409
