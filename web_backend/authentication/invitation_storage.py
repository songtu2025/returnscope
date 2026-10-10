from __future__ import annotations

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
from web_backend.security import token_hash, utc_now


class InvitationStorage(AuthContext):
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
            pending_email_change = connection.execute(
                """
                SELECT id FROM auth_action_tokens
                WHERE email = ? AND purpose = ?
                  AND used_at IS NULL AND revoked_at IS NULL AND expires_at > ?
                """,
                (email, EMAIL_CHANGE_PURPOSE, now),
            ).fetchone()
            if pending_email_change is not None:
                raise AuthServiceError(409, "该邮箱正在验证修改")
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
