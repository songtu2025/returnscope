from __future__ import annotations

import logging
from typing import Any

from web_backend.authentication.contracts import (
    INVITATION_PURPOSE,
    AuthServiceError,
)
from web_backend.authentication.invitation_storage import InvitationStorage
from web_backend.common import insert_audit
from web_backend.security import normalize_email, utc_now

logger = logging.getLogger(__name__)


class InvitationActions(InvitationStorage):
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
        email = self.pending_invitation_email(invitation_id)
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

    def pending_invitation_email(self, invitation_id: str) -> str:
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
        return str(current["email"])

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
