"""邮箱验证与变更流程，保留原有事务和会话撤销规则。"""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from web_backend.authentication.context import AuthContext
from web_backend.authentication.contracts import (
    EMAIL_CHANGE_PURPOSE,
    INVITATION_PURPOSE,
    AuthServiceError,
)
from web_backend.common import insert_audit, new_id
from web_backend.security import normalize_email, token_hash, utc_now, verify_password

logger = logging.getLogger(__name__)


class EmailChangeActions(AuthContext):
    def request_email_change(
        self,
        user_id: str,
        current_password: str,
        new_email: str,
    ) -> None:
        normalized_email = normalize_email(new_email)
        now = utc_now()
        token_id = new_id("auth_token")
        raw_token = secrets.token_urlsafe(36)
        expires_at = (
            datetime.now(UTC)
            + timedelta(minutes=self.settings.password_reset_ttl_minutes)
        ).isoformat()
        with self.database.transaction(immediate=True) as connection:
            user = connection.execute(
                "SELECT * FROM users WHERE id = ? AND active = 1",
                (user_id,),
            ).fetchone()
            if user is None or not verify_password(
                current_password,
                str(user["password_hash"]),
            ):
                raise AuthServiceError(400, "当前密码错误")
            current_email = str(user["email"])
            if current_email == normalized_email:
                raise AuthServiceError(400, "新邮箱不能与当前邮箱相同")
            self._require_available_email(connection, normalized_email, user_id, now)
            connection.execute(
                """
                INSERT INTO auth_action_tokens(
                    id, user_id, email, purpose, token_hash,
                    expires_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    token_id,
                    user_id,
                    normalized_email,
                    EMAIL_CHANGE_PURPOSE,
                    token_hash(raw_token),
                    expires_at,
                    now,
                ),
            )

        change_url = self._action_url("change-email", raw_token)
        try:
            self.mail_sender.send_email_change(normalized_email, change_url)
        except Exception as error:
            self._revoke_token(token_id)
            logger.error("邮箱变更邮件发送失败: error_type=%s", type(error).__name__)
            raise AuthServiceError(502, "验证邮件发送失败，请稍后重试") from error

        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                UPDATE auth_action_tokens SET revoked_at = ?
                WHERE user_id = ? AND purpose = ? AND id <> ?
                  AND used_at IS NULL AND revoked_at IS NULL
                """,
                (utc_now(), user_id, EMAIL_CHANGE_PURPOSE, token_id),
            )
            insert_audit(
                connection,
                "user",
                user_id,
                "request_email_change",
                user_id,
                before={"email": current_email},
                after={"pending_email": normalized_email},
            )

    def validate_email_change(self, raw_token: str) -> dict[str, Any]:
        now = utc_now()
        with self.database.connect() as connection:
            change = self._find_token(connection, raw_token, EMAIL_CHANGE_PURPOSE)
            user = None
            if change is not None and change["user_id"]:
                user = connection.execute(
                    "SELECT id, email, active FROM users WHERE id = ?",
                    (change["user_id"],),
                ).fetchone()
            if not self._email_change_is_valid(change, user, now):
                raise AuthServiceError(400, "邮箱验证链接无效或已过期")
            assert change is not None
            assert user is not None
            self._require_available_email(
                connection,
                str(change["email"]),
                str(user["id"]),
                now,
                exclude_email_change=True,
            )
        return {
            "email": change["email"],
            "expires_at": change["expires_at"],
        }

    def complete_email_change(self, raw_token: str) -> None:
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            change = self._find_token(connection, raw_token, EMAIL_CHANGE_PURPOSE)
            user = None
            if change is not None and change["user_id"]:
                user = connection.execute(
                    "SELECT id, email, active FROM users WHERE id = ?",
                    (change["user_id"],),
                ).fetchone()
            if not self._email_change_is_valid(change, user, now):
                raise AuthServiceError(400, "邮箱验证链接无效或已过期")
            assert change is not None
            assert user is not None
            user_id = str(user["id"])
            new_email = str(change["email"])
            self._require_available_email(
                connection,
                new_email,
                user_id,
                now,
                exclude_email_change=True,
            )
            consumed = connection.execute(
                """
                UPDATE auth_action_tokens SET used_at = ?
                WHERE id = ? AND used_at IS NULL AND revoked_at IS NULL
                  AND expires_at > ?
                """,
                (now, change["id"], now),
            )
            if consumed.rowcount != 1:
                raise AuthServiceError(400, "邮箱验证链接无效或已过期")
            connection.execute(
                "UPDATE users SET email = ? WHERE id = ?",
                (new_email, user_id),
            )
            connection.execute(
                """
                UPDATE auth_action_tokens SET revoked_at = ?
                WHERE user_id = ? AND id <> ?
                  AND used_at IS NULL AND revoked_at IS NULL
                """,
                (now, user_id, change["id"]),
            )
            connection.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            insert_audit(
                connection,
                "user",
                user_id,
                "change_email",
                user_id,
                before={"email": user["email"]},
                after={"email": new_email},
            )

    @staticmethod
    def _require_available_email(
        connection: Any,
        email: str,
        user_id: str,
        now: str,
        *,
        exclude_email_change: bool = False,
    ) -> None:
        existing_user = connection.execute(
            "SELECT id FROM users WHERE email = ? AND id <> ?",
            (email, user_id),
        ).fetchone()
        if existing_user is not None:
            raise AuthServiceError(409, "该邮箱已经存在")
        pending_invitation = connection.execute(
            """
            SELECT id FROM auth_action_tokens
            WHERE email = ? AND purpose = ?
              AND used_at IS NULL AND revoked_at IS NULL AND expires_at > ?
            """,
            (email, INVITATION_PURPOSE, now),
        ).fetchone()
        if pending_invitation is not None:
            raise AuthServiceError(409, "该邮箱已有待接受邀请")
        if exclude_email_change:
            return
        pending_change = connection.execute(
            """
            SELECT id FROM auth_action_tokens
            WHERE email = ? AND purpose = ? AND user_id <> ?
              AND used_at IS NULL AND revoked_at IS NULL AND expires_at > ?
            """,
            (email, EMAIL_CHANGE_PURPOSE, user_id, now),
        ).fetchone()
        if pending_change is not None:
            raise AuthServiceError(409, "该邮箱正在验证修改")

    @staticmethod
    def _email_change_is_valid(
        change: Any,
        user: Any,
        now: str,
    ) -> bool:
        return bool(
            change is not None
            and change["used_at"] is None
            and change["revoked_at"] is None
            and change["expires_at"] > now
            and user is not None
            and bool(user["active"])
            and str(user["email"]) != str(change["email"])
        )
