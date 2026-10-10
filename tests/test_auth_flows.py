from __future__ import annotations

from dataclasses import dataclass, field
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
