from __future__ import annotations

from web_backend.authentication.context import AuthContext
from web_backend.authentication.contracts import (
    INVITATION_PURPOSE,
    AuthServiceError,
    RegistrationResult,
)
from web_backend.common import insert_audit, new_id
from web_backend.security import hash_password, token_hash, utc_now


class RegistrationActions(AuthContext):
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
