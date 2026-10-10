from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient
from test_auth_flows import (
    FakeMailSender,
    _create_member,
    _login_admin,
    _settings,
    _token_from_url,
)


def test_admin_invites_member_and_member_registers_once(tmp_path: Path) -> None:
    from web_backend.app import create_app

    sender = FakeMailSender()
    app = create_app(
        start_worker=False,
        settings_override=_settings(tmp_path),
        mail_sender_override=sender,
    )

    with TestClient(app) as client:
        _login_admin(client)
        invited = client.post(
            "/api/invitations",
            json={"email": "Member@Example.com"},
        )
        assert invited.status_code == 201
        assert invited.json()["email"] == "member@example.com"
        assert len(sender.invitations) == 1
        raw_token = _token_from_url(sender.invitations[0]["url"])
        assert sender.invitations[0]["url"].startswith(
            "https://feedback.example.com/#register?token="
        )

        with app.state.database.connect() as connection:
            token_row = connection.execute(
                "SELECT token_hash FROM auth_action_tokens WHERE id = ?",
                (invited.json()["id"],),
            ).fetchone()
        assert token_row["token_hash"] != raw_token
        assert raw_token not in token_row["token_hash"]

        validated = client.post(
            "/api/auth/invitations/validate",
            json={"token": raw_token},
        )
        assert validated.status_code == 200
        assert validated.json()["email"] == "member@example.com"

        registered = client.post(
            "/api/auth/register",
            json={
                "token": raw_token,
                "display_name": "测试成员",
                "password": "member-password-123",
            },
        )
        assert registered.status_code == 200
        assert registered.json()["email"] == "member@example.com"
        assert client.get("/api/auth/me").json()["display_name"] == "测试成员"
        reused = client.post(
            "/api/auth/invitations/validate",
            json={"token": raw_token},
        )
        assert reused.status_code == 400


def test_resend_and_revoke_invitation_invalidates_links(tmp_path: Path) -> None:
    from web_backend.app import create_app

    sender = FakeMailSender()
    app = create_app(
        start_worker=False,
        settings_override=_settings(tmp_path),
        mail_sender_override=sender,
    )

    with TestClient(app) as client:
        _login_admin(client)
        invited = client.post(
            "/api/invitations",
            json={"email": "member@example.com"},
        ).json()
        old_token = _token_from_url(sender.invitations[-1]["url"])

        resent = client.post(f"/api/invitations/{invited['id']}/resend")
        assert resent.status_code == 201
        new_token = _token_from_url(sender.invitations[-1]["url"])
        assert new_token != old_token
        assert (
            client.post(
                "/api/auth/invitations/validate",
                json={"token": old_token},
            ).status_code
            == 400
        )
        assert (
            client.post(
                "/api/auth/invitations/validate",
                json={"token": new_token},
            ).status_code
            == 200
        )

        revoked = client.post(f"/api/invitations/{resent.json()['id']}/revoke")
        assert revoked.status_code == 204
        assert (
            client.post(
                "/api/auth/invitations/validate",
                json={"token": new_token},
            ).status_code
            == 400
        )
        assert client.get("/api/invitations").json() == []


def test_invitation_email_sends_are_rate_limited(tmp_path: Path) -> None:
    from web_backend.app import create_app

    sender = FakeMailSender()
    settings = replace(
        _settings(tmp_path),
        invitation_send_limit_per_admin=3,
        invitation_send_limit_per_recipient=2,
        invitation_send_window_seconds=60,
    )
    app = create_app(
        start_worker=False,
        settings_override=settings,
        mail_sender_override=sender,
    )

    with TestClient(app) as client:
        _login_admin(client)
        invited = client.post(
            "/api/invitations",
            json={"email": "member@example.com"},
        )
        assert invited.status_code == 201

        resent = client.post(f"/api/invitations/{invited.json()['id']}/resend")
        assert resent.status_code == 201
        recipient_limited = client.post(
            f"/api/invitations/{resent.json()['id']}/resend"
        )
        assert recipient_limited.status_code == 429
        assert int(recipient_limited.headers["Retry-After"]) > 0

        assert (
            client.post(
                "/api/invitations",
                json={"email": "member2@example.com"},
            ).status_code
            == 201
        )
        admin_limited = client.post(
            "/api/invitations",
            json={"email": "member3@example.com"},
        )
        assert admin_limited.status_code == 429
        assert int(admin_limited.headers["Retry-After"]) > 0


def test_invitation_requires_admin_and_rejects_expired_or_short_password(
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
        invited = client.post(
            "/api/invitations",
            json={"email": "invited@example.com"},
        )
        assert invited.status_code == 201
        raw_token = _token_from_url(sender.invitations[-1]["url"])
        short_password = client.post(
            "/api/auth/register",
            json={
                "token": raw_token,
                "display_name": "受邀成员",
                "password": "short-pass",
            },
        )
        assert short_password.status_code == 400

        with app.state.database.transaction() as connection:
            connection.execute(
                "UPDATE auth_action_tokens SET expires_at = ? WHERE id = ?",
                ("2000-01-01T00:00:00+00:00", invited.json()["id"]),
            )
        expired = client.post(
            "/api/auth/invitations/validate",
            json={"token": raw_token},
        )
        assert expired.status_code == 400

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
        assert client.get("/api/invitations").status_code == 403
        assert (
            client.post(
                "/api/invitations",
                json={"email": "unauthorized@example.com"},
            ).status_code
            == 403
        )
