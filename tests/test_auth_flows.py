from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from web_backend.database import Database
from web_backend.database_migrations import (
    AUTH_ACTION_TOKEN_MIGRATION,
    AUTH_ACTION_TOKEN_MIGRATION_CHECKSUM,
    EMAIL_CHANGE_TOKEN_MIGRATION,
    EMAIL_CHANGE_TOKEN_MIGRATION_CHECKSUM,
)
from web_backend.settings import Settings


@dataclass
class FakeMailSender:
    invitations: list[dict[str, str]] = field(default_factory=list)
    password_resets: list[dict[str, str]] = field(default_factory=list)
    email_changes: list[dict[str, str]] = field(default_factory=list)
    fail_invitation: bool = False
    fail_password_reset: bool = False
    fail_email_change: bool = False

    def send_invitation(self, email: str, invitation_url: str) -> None:
        if self.fail_invitation:
            raise RuntimeError("模拟邀请邮件失败")
        self.invitations.append({"email": email, "url": invitation_url})

    def send_password_reset(self, email: str, reset_url: str) -> None:
        if self.fail_password_reset:
            raise RuntimeError("模拟重置邮件失败")
        self.password_resets.append({"email": email, "url": reset_url})

    def send_email_change(self, email: str, change_url: str) -> None:
        if self.fail_email_change:
            raise RuntimeError("模拟邮箱变更邮件失败")
        self.email_changes.append({"email": email, "url": change_url})


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
        public_web_url="https://feedback.example.com",
    )


def _token_from_url(url: str) -> str:
    fragment = urlsplit(url).fragment
    query = fragment.split("?", maxsplit=1)[1]
    return parse_qs(query)["token"][0]


def _login_admin(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={
            "email": "admin@example.com",
            "password": "test-password-123",
        },
    )
    assert response.status_code == 200


def _create_member(client: TestClient) -> None:
    response = client.post(
        "/api/users",
        json={
            "email": "member@example.com",
            "display_name": "测试成员",
            "password": "member-password-123",
        },
    )
    assert response.status_code == 201


def test_auth_action_token_migration_is_idempotent(tmp_path: Path) -> None:
    database = Database(tmp_path / "app.db")

    database.initialize()
    database.initialize()

    with database.connect() as connection:
        migration = connection.execute(
            "SELECT * FROM app_migrations WHERE migration_id = ?",
            (AUTH_ACTION_TOKEN_MIGRATION,),
        ).fetchone()
        email_change_migration = connection.execute(
            "SELECT * FROM app_migrations WHERE migration_id = ?",
            (EMAIL_CHANGE_TOKEN_MIGRATION,),
        ).fetchone()
        columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(auth_action_tokens)"
            ).fetchall()
        }
    assert migration["checksum"] == AUTH_ACTION_TOKEN_MIGRATION_CHECKSUM
    assert email_change_migration["checksum"] == EMAIL_CHANGE_TOKEN_MIGRATION_CHECKSUM
    assert {
        "id",
        "user_id",
        "email",
        "purpose",
        "token_hash",
        "expires_at",
        "used_at",
        "revoked_at",
        "created_by",
        "created_at",
    } == columns

    with database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO auth_action_tokens(
                id, user_id, email, purpose, token_hash, expires_at, created_at
            ) VALUES ('email-change-test', NULL, 'new@example.com',
                'email_change', 'hash', '2099-01-01T00:00:00+00:00',
                '2026-09-20T00:00:00+00:00')
            """
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


def test_team_accounts_are_not_limited_to_five(tmp_path: Path) -> None:
    from web_backend.app import create_app

    sender = FakeMailSender()
    app = create_app(
        start_worker=False,
        settings_override=_settings(tmp_path),
        mail_sender_override=sender,
    )

    with TestClient(app) as client:
        _login_admin(client)
        for index in range(1, 7):
            response = client.post(
                "/api/invitations",
                json={"email": f"member{index}@example.com"},
            )
            assert response.status_code == 201
        assert len(client.get("/api/invitations").json()) == 6

        for index, invitation in enumerate(sender.invitations, start=1):
            registered = client.post(
                "/api/auth/register",
                json={
                    "token": _token_from_url(invitation["url"]),
                    "display_name": f"成员 {index}",
                    "password": "member-password-123",
                },
            )
            assert registered.status_code == 200

        _login_admin(client)
        assert len(client.get("/api/users").json()) == 7


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


def test_bootstrap_email_is_only_used_for_initial_user(tmp_path: Path) -> None:
    from web_backend.app import create_app

    settings = _settings(tmp_path)
    first_app = create_app(start_worker=False, settings_override=settings)
    with first_app.state.database.transaction() as connection:
        connection.execute(
            "UPDATE users SET email = 'wch@seekwaygroup.com' WHERE email = ?",
            (settings.bootstrap_email,),
        )

    restarted_app = create_app(start_worker=False, settings_override=settings)
    with restarted_app.state.database.connect() as connection:
        users = connection.execute(
            "SELECT email, is_admin FROM users ORDER BY created_at"
        ).fetchall()
    assert [dict(row) for row in users] == [
        {"email": "wch@seekwaygroup.com", "is_admin": 1}
    ]


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


def test_mail_failures_leave_no_usable_tokens(tmp_path: Path) -> None:
    from web_backend.app import create_app

    sender = FakeMailSender(fail_invitation=True)
    app = create_app(
        start_worker=False,
        settings_override=_settings(tmp_path),
        mail_sender_override=sender,
    )

    with TestClient(app) as client:
        _login_admin(client)
        failed_invitation = client.post(
            "/api/invitations",
            json={"email": "member@example.com"},
        )
        assert failed_invitation.status_code == 502
        assert client.get("/api/invitations").json() == []

        sender.fail_invitation = False
        _create_member(client)
        sender.fail_password_reset = True
        reset = client.post(
            "/api/auth/password-reset/request",
            json={"email": "member@example.com"},
        )
        assert reset.status_code == 204
        sender.fail_email_change = True
        email_change = client.post(
            "/api/auth/email-change/request",
            json={
                "current_password": "test-password-123",
                "new_email": "wch@seekwaygroup.com",
            },
        )
        assert email_change.status_code == 502
        with app.state.database.connect() as connection:
            usable_tokens = connection.execute(
                """
                SELECT COUNT(*) AS count FROM auth_action_tokens
                WHERE used_at IS NULL AND revoked_at IS NULL
                """
            ).fetchone()["count"]
        assert usable_tokens == 0
