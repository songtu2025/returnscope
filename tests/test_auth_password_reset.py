from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from test_auth_flows import (
    FakeMailSender,
    _create_member,
    _login_admin,
    _settings,
    _token_from_url,
)


def test_password_reset_is_private_single_use_and_revokes_sessions(
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
        _create_member(client)
        assert client.post("/api/auth/logout").status_code == 204
        assert (
            client.post(
                "/api/auth/login",
                json={
                    "email": "member@example.com",
                    "password": "member-password-123",
                },
            ).status_code
            == 200
        )

        existing = client.post(
            "/api/auth/password-reset/request",
            json={"email": "member@example.com"},
        )
        missing = client.post(
            "/api/auth/password-reset/request",
            json={"email": "missing@example.com"},
        )
        assert existing.status_code == missing.status_code == 204
        assert len(sender.password_resets) == 1
        raw_token = _token_from_url(sender.password_resets[0]["url"])
        assert (
            client.post(
                "/api/auth/password-reset/validate",
                json={"token": raw_token},
            ).status_code
            == 200
        )

        completed = client.post(
            "/api/auth/password-reset/complete",
            json={
                "token": raw_token,
                "new_password": "new-member-password-456",
            },
        )
        assert completed.status_code == 204
        assert client.get("/api/auth/me").status_code == 401
        assert (
            client.post(
                "/api/auth/login",
                json={
                    "email": "member@example.com",
                    "password": "member-password-123",
                },
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/api/auth/login",
                json={
                    "email": "member@example.com",
                    "password": "new-member-password-456",
                },
            ).status_code
            == 200
        )
        reused = client.post(
            "/api/auth/password-reset/complete",
            json={
                "token": raw_token,
                "new_password": "another-member-password-789",
            },
        )
        assert reused.status_code == 400


def test_password_reset_request_is_rate_limited(tmp_path: Path) -> None:
    from web_backend.app import create_app

    sender = FakeMailSender()
    app = create_app(
        start_worker=False,
        settings_override=_settings(tmp_path),
        mail_sender_override=sender,
    )

    with TestClient(app) as client:
        _login_admin(client)
        for _ in range(3):
            response = client.post(
                "/api/auth/password-reset/request",
                json={"email": "admin@example.com"},
            )
            assert response.status_code == 204
        limited = client.post(
            "/api/auth/password-reset/request",
            json={"email": "admin@example.com"},
        )
        assert limited.status_code == 429
        assert limited.headers["retry-after"]
