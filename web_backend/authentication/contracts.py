from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from web_backend.security import Session

INVITATION_PURPOSE = "invitation"
PASSWORD_RESET_PURPOSE = "password_reset"
EMAIL_CHANGE_PURPOSE = "email_change"


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
