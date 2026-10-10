from typing import Any, NoReturn

from fastapi import HTTPException

from web_backend.auth_service import AuthServiceError
from web_backend.security import LoginAttemptLimiter, normalize_email


def _raise_http(error: AuthServiceError) -> NoReturn:
    raise HTTPException(status_code=error.status_code, detail=error.detail) from error


def _require_invitation_admin(user: dict[str, Any]) -> None:
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="仅系统管理员可管理团队邀请")


def _check_invitation_send_limit(
    actor_id: str,
    email: str,
    admin_limiter: LoginAttemptLimiter,
    recipient_limiter: LoginAttemptLimiter,
) -> str:
    try:
        normalized_email = normalize_email(email)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    admin_key = f"invitation-admin:{actor_id}"
    recipient_key = f"invitation-recipient:{normalized_email}"
    retry_after = max(
        admin_limiter.retry_after(admin_key),
        recipient_limiter.retry_after(recipient_key),
    )
    if retry_after:
        raise HTTPException(
            status_code=429,
            detail="邀请邮件发送过于频繁，请稍后再试",
            headers={"Retry-After": str(retry_after)},
        )
    admin_limiter.record_failure(admin_key)
    recipient_limiter.record_failure(recipient_key)
    return normalized_email
