from __future__ import annotations

from typing import Any
from urllib.parse import quote

from web_backend.authentication.contracts import (
    AuthServiceError,
)
from web_backend.database import Database
from web_backend.mail_service import MailSender
from web_backend.security import (
    SessionService,
    token_hash,
    utc_now,
)
from web_backend.settings import Settings


class AuthContext:
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

    def _validate_new_password(self, password: str) -> None:
        if len(password) < self.settings.password_min_length:
            raise AuthServiceError(
                400,
                f"密码至少需要 {self.settings.password_min_length} 位",
            )
