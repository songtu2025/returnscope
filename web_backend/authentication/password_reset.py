from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from web_backend.authentication.context import AuthContext
from web_backend.authentication.contracts import (
    PASSWORD_RESET_PURPOSE,
    AuthServiceError,
)
from web_backend.common import insert_audit, new_id
from web_backend.security import (
    hash_password,
    normalize_email,
    token_hash,
    utc_now,
    verify_password,
)

logger = logging.getLogger(__name__)


class PasswordResetActions(AuthContext):
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
