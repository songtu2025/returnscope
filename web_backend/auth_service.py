from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

from web_backend.common import insert_audit, new_id
from web_backend.database import Database
from web_backend.mail_service import MailSender
from web_backend.security import (
    Session,
    SessionService,
    hash_password,
    normalize_email,
    token_hash,
    utc_now,
    verify_password,
)
from web_backend.settings import Settings

logger = logging.getLogger(__name__)

TEAM_ACCOUNT_LIMIT = 5
INVITATION_PURPOSE = "invitation"
PASSWORD_RESET_PURPOSE = "password_reset"


class AuthServiceError(Exception):
    """表示可安全返回给调用方的认证业务错误。"""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class RegistrationResult:
    user: dict[str, Any]
    session: Session


class AuthService:
    def __init__(
        self,
        database: Database,
        settings: Settings,
        mail_sender: MailSender,
        session_service: SessionService,
    ) -> None:
        self.database = database
        self.settings = settings
        self.mail_sender = mail_sender
        self.session_service = session_service

    def list_pending_invitations(self) -> list[dict[str, Any]]:
        now = utc_now()
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, email, expires_at, created_by, created_at
                FROM auth_action_tokens
                WHERE purpose = ?
                  AND used_at IS NULL
                  AND revoked_at IS NULL
                  AND expires_at > ?
                ORDER BY created_at DESC
                """,
                (INVITATION_PURPOSE, now),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_invitation(self, email: str, actor_id: str) -> dict[str, Any]:
        normalized_email = normalize_email(email)
        token_id, raw_token = self._insert_invitation(normalized_email, actor_id)
        invitation_url = self._action_url("register", raw_token)
        try:
            self.mail_sender.send_invitation(normalized_email, invitation_url)
        except Exception as error:
            self._revoke_token(token_id)
            logger.error("邀请邮件发送失败: error_type=%s", type(error).__name__)
            raise AuthServiceError(502, "邀请邮件发送失败，请稍后重试") from error
        self._audit_invitation(token_id, actor_id, "invite")
        return self._get_invitation(token_id)

    def resend_invitation(self, invitation_id: str, actor_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            current = connection.execute(
                """
                SELECT email FROM auth_action_tokens
                WHERE id = ? AND purpose = ?
                  AND used_at IS NULL AND revoked_at IS NULL
                """,
                (invitation_id, INVITATION_PURPOSE),
            ).fetchone()
        if current is None:
            raise AuthServiceError(409, "该邀请已不能重发")

        email = str(current["email"])
        replacement_id, raw_token = self._insert_replacement_invitation(
            email,
            actor_id,
        )
        invitation_url = self._action_url("register", raw_token)
        try:
            self.mail_sender.send_invitation(email, invitation_url)
        except Exception as error:
            self._revoke_token(replacement_id)
            logger.error("邀请邮件发送失败: error_type=%s", type(error).__name__)
            raise AuthServiceError(502, "邀请邮件发送失败，请稍后重试") from error

        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                UPDATE auth_action_tokens SET revoked_at = ?
                WHERE email = ? AND purpose = ? AND id <> ?
                  AND used_at IS NULL AND revoked_at IS NULL
                """,
                (now, email, INVITATION_PURPOSE, replacement_id),
            )
            insert_audit(
                connection,
                "invitation",
                replacement_id,
                "resend",
                actor_id,
                after={"email": email},
            )
        return self._get_invitation(replacement_id)

    def revoke_invitation(self, invitation_id: str, actor_id: str) -> None:
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            invitation = connection.execute(
                """
                SELECT email FROM auth_action_tokens
                WHERE id = ? AND purpose = ?
                  AND used_at IS NULL AND revoked_at IS NULL
                """,
                (invitation_id, INVITATION_PURPOSE),
            ).fetchone()
            if invitation is None:
                raise AuthServiceError(409, "该邀请已不能撤销")
            connection.execute(
                "UPDATE auth_action_tokens SET revoked_at = ? WHERE id = ?",
                (now, invitation_id),
            )
            insert_audit(
                connection,
                "invitation",
                invitation_id,
                "revoke",
                actor_id,
                before={"email": invitation["email"]},
            )

    def validate_invitation(self, raw_token: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            invitation = self._find_token(
                connection,
                raw_token,
                INVITATION_PURPOSE,
            )
        self._require_valid_invitation(invitation)
        assert invitation is not None
        return {
            "email": invitation["email"],
            "expires_at": invitation["expires_at"],
        }

    def register(
        self,
        raw_token: str,
        display_name: str,
        password: str,
    ) -> RegistrationResult:
        clean_name = display_name.strip()
        if not clean_name:
            raise AuthServiceError(400, "请填写姓名")
        self._validate_new_password(password)
        now = utc_now()
        hashed_token = token_hash(raw_token)
        with self.database.transaction(immediate=True) as connection:
            invitation = connection.execute(
                """
                SELECT * FROM auth_action_tokens
                WHERE token_hash = ? AND purpose = ?
                """,
                (hashed_token, INVITATION_PURPOSE),
            ).fetchone()
            self._require_valid_invitation(invitation, now)
            assert invitation is not None
            email = str(invitation["email"])
            existing_user = connection.execute(
                "SELECT id FROM users WHERE email = ?",
                (email,),
            ).fetchone()
            if existing_user is not None:
                raise AuthServiceError(409, "该邮箱已经存在")
            active_count = connection.execute(
                "SELECT COUNT(*) AS count FROM users WHERE active = 1"
            ).fetchone()
            if int(active_count["count"]) >= TEAM_ACCOUNT_LIMIT:
                raise AuthServiceError(409, "团队账号席位已满")

            consumed = connection.execute(
                """
                UPDATE auth_action_tokens
                SET used_at = ?
                WHERE id = ? AND used_at IS NULL AND revoked_at IS NULL
                  AND expires_at > ?
                """,
                (now, invitation["id"], now),
            )
            if consumed.rowcount != 1:
                raise AuthServiceError(400, "邀请链接无效或已过期")

            user_id = new_id("user")
            connection.execute(
                """
                INSERT INTO users(id, email, display_name, password_hash, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, email, clean_name, hash_password(password), now),
            )
            connection.execute(
                "UPDATE auth_action_tokens SET user_id = ? WHERE id = ?",
                (user_id, invitation["id"]),
            )
            connection.execute(
                """
                UPDATE auth_action_tokens SET revoked_at = ?
                WHERE email = ? AND purpose = ? AND id <> ?
                  AND used_at IS NULL AND revoked_at IS NULL
                """,
                (now, email, INVITATION_PURPOSE, invitation["id"]),
            )
            session = self.session_service.create_in_connection(connection, user_id)
            insert_audit(
                connection,
                "user",
                user_id,
                "register",
                user_id,
                after={"email": email, "display_name": clean_name},
            )
        return RegistrationResult(
            user={
                "id": user_id,
                "email": email,
                "display_name": clean_name,
                "is_admin": False,
            },
            session=session,
        )

    def request_password_reset(self, email: str) -> None:
        normalized_email = normalize_email(email)
        with self.database.connect() as connection:
            user = connection.execute(
                "SELECT id, email FROM users WHERE email = ? AND active = 1",
                (normalized_email,),
            ).fetchone()
        if user is None:
            return

        token_id = new_id("auth_token")
        raw_token = secrets.token_urlsafe(36)
        now = utc_now()
        expires_at = (
            datetime.now(UTC)
            + timedelta(minutes=self.settings.password_reset_ttl_minutes)
        ).isoformat()
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                INSERT INTO auth_action_tokens(
                    id, user_id, email, purpose, token_hash,
                    expires_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    token_id,
                    user["id"],
                    normalized_email,
                    PASSWORD_RESET_PURPOSE,
                    token_hash(raw_token),
                    expires_at,
                    now,
                ),
            )
        reset_url = self._action_url("reset-password", raw_token)
        try:
            self.mail_sender.send_password_reset(normalized_email, reset_url)
        except Exception as error:
            self._revoke_token(token_id)
            logger.error("密码重置邮件发送失败: error_type=%s", type(error).__name__)
            return

        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                UPDATE auth_action_tokens SET revoked_at = ?
                WHERE user_id = ? AND purpose = ? AND id <> ?
                  AND used_at IS NULL AND revoked_at IS NULL
                """,
                (utc_now(), user["id"], PASSWORD_RESET_PURPOSE, token_id),
            )

    def validate_password_reset(self, raw_token: str) -> None:
        with self.database.connect() as connection:
            reset = self._find_token(connection, raw_token, PASSWORD_RESET_PURPOSE)
            user = None
            if reset is not None and reset["user_id"]:
                user = connection.execute(
                    "SELECT id, active FROM users WHERE id = ?",
                    (reset["user_id"],),
                ).fetchone()
        if not self._password_reset_is_valid(reset, user):
            raise AuthServiceError(400, "重置链接无效或已过期")

    def complete_password_reset(self, raw_token: str, new_password: str) -> None:
        self._validate_new_password(new_password)
        now = utc_now()
        hashed_token = token_hash(raw_token)
        with self.database.transaction(immediate=True) as connection:
            reset = connection.execute(
                """
                SELECT * FROM auth_action_tokens
                WHERE token_hash = ? AND purpose = ?
                """,
                (hashed_token, PASSWORD_RESET_PURPOSE),
            ).fetchone()
            user = None
            if reset is not None and reset["user_id"]:
                user = connection.execute(
                    "SELECT * FROM users WHERE id = ?",
                    (reset["user_id"],),
                ).fetchone()
            if not self._password_reset_is_valid(reset, user, now):
                raise AuthServiceError(400, "重置链接无效或已过期")
            assert reset is not None
            assert user is not None
            if verify_password(new_password, str(user["password_hash"])):
                raise AuthServiceError(400, "新密码不能与当前密码相同")

            consumed = connection.execute(
                """
                UPDATE auth_action_tokens SET used_at = ?
                WHERE id = ? AND used_at IS NULL AND revoked_at IS NULL
                  AND expires_at > ?
                """,
                (now, reset["id"], now),
            )
            if consumed.rowcount != 1:
                raise AuthServiceError(400, "重置链接无效或已过期")
            connection.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (hash_password(new_password), user["id"]),
            )
            connection.execute(
                """
                UPDATE auth_action_tokens SET revoked_at = ?
                WHERE user_id = ? AND purpose = ? AND id <> ?
                  AND used_at IS NULL AND revoked_at IS NULL
                """,
                (now, user["id"], PASSWORD_RESET_PURPOSE, reset["id"]),
            )
            connection.execute(
                "DELETE FROM sessions WHERE user_id = ?",
                (user["id"],),
            )
            insert_audit(
                connection,
                "user",
                str(user["id"]),
                "reset_password",
                str(user["id"]),
            )

    def _insert_invitation(self, email: str, actor_id: str) -> tuple[str, str]:
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            existing_user = connection.execute(
                "SELECT active FROM users WHERE email = ?",
                (email,),
            ).fetchone()
            if existing_user is not None:
                detail = (
                    "该邮箱已经存在" if existing_user["active"] else "该邮箱账号已停用"
                )
                raise AuthServiceError(409, detail)
            pending_for_email = connection.execute(
                """
                SELECT id FROM auth_action_tokens
                WHERE email = ? AND purpose = ?
                  AND used_at IS NULL AND revoked_at IS NULL AND expires_at > ?
                """,
                (email, INVITATION_PURPOSE, now),
            ).fetchone()
            if pending_for_email is not None:
                raise AuthServiceError(409, "该邮箱已有待接受邀请")
            active_count = connection.execute(
                "SELECT COUNT(*) AS count FROM users WHERE active = 1"
            ).fetchone()
            pending_count = connection.execute(
                """
                SELECT COUNT(*) AS count FROM auth_action_tokens
                WHERE purpose = ? AND used_at IS NULL AND revoked_at IS NULL
                  AND expires_at > ?
                """,
                (INVITATION_PURPOSE, now),
            ).fetchone()
            if int(active_count["count"]) + int(pending_count["count"]) >= (
                TEAM_ACCOUNT_LIMIT
            ):
                raise AuthServiceError(409, "最多可保留 5 个团队账号或有效邀请")
            return self._insert_invitation_row(connection, email, actor_id, now)

    def _insert_replacement_invitation(
        self,
        email: str,
        actor_id: str,
    ) -> tuple[str, str]:
        with self.database.transaction(immediate=True) as connection:
            existing_user = connection.execute(
                "SELECT id FROM users WHERE email = ?",
                (email,),
            ).fetchone()
            if existing_user is not None:
                raise AuthServiceError(409, "该邮箱已经完成注册")
            return self._insert_invitation_row(connection, email, actor_id, utc_now())

    def _insert_invitation_row(
        self,
        connection: Any,
        email: str,
        actor_id: str,
        now: str,
    ) -> tuple[str, str]:
        token_id = new_id("auth_token")
        raw_token = secrets.token_urlsafe(36)
        expires_at = (
            datetime.now(UTC) + timedelta(hours=self.settings.invitation_ttl_hours)
        ).isoformat()
        connection.execute(
            """
            INSERT INTO auth_action_tokens(
                id, email, purpose, token_hash, expires_at, created_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                token_id,
                email,
                INVITATION_PURPOSE,
                token_hash(raw_token),
                expires_at,
                actor_id,
                now,
            ),
        )
        return token_id, raw_token

    def _get_invitation(self, invitation_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT id, email, expires_at, created_by, created_at
                FROM auth_action_tokens WHERE id = ?
                """,
                (invitation_id,),
            ).fetchone()
        if row is None:
            raise AuthServiceError(404, "邀请不存在")
        return dict(row)

    def _audit_invitation(
        self,
        invitation_id: str,
        actor_id: str,
        action: str,
    ) -> None:
        invitation = self._get_invitation(invitation_id)
        with self.database.transaction() as connection:
            insert_audit(
                connection,
                "invitation",
                invitation_id,
                action,
                actor_id,
                after={"email": invitation["email"]},
            )

    def _revoke_token(self, token_id: str) -> None:
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                UPDATE auth_action_tokens SET revoked_at = ?
                WHERE id = ? AND used_at IS NULL AND revoked_at IS NULL
                """,
                (utc_now(), token_id),
            )

    def _action_url(self, page: str, raw_token: str) -> str:
        return (
            f"{self.settings.public_web_url.rstrip('/')}/"
            f"#{page}?token={quote(raw_token, safe='')}"
        )

    @staticmethod
    def _find_token(connection: Any, raw_token: str, purpose: str) -> Any:
        return connection.execute(
            """
            SELECT * FROM auth_action_tokens
            WHERE token_hash = ? AND purpose = ?
            """,
            (token_hash(raw_token), purpose),
        ).fetchone()

    @staticmethod
    def _require_valid_invitation(
        invitation: Any,
        now: str | None = None,
    ) -> None:
        current_time = now or utc_now()
        if (
            invitation is None
            or invitation["used_at"] is not None
            or invitation["revoked_at"] is not None
            or invitation["expires_at"] <= current_time
        ):
            raise AuthServiceError(400, "邀请链接无效或已过期")

    @staticmethod
    def _password_reset_is_valid(
        reset: Any,
        user: Any,
        now: str | None = None,
    ) -> bool:
        current_time = now or utc_now()
        return bool(
            reset is not None
            and reset["used_at"] is None
            and reset["revoked_at"] is None
            and reset["expires_at"] > current_time
            and user is not None
            and bool(user["active"])
        )

    def _validate_new_password(self, password: str) -> None:
        if len(password) < self.settings.password_min_length:
            raise AuthServiceError(
                400,
                f"密码至少需要 {self.settings.password_min_length} 位",
            )
