from typing import Annotated, Any, Callable, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from web_backend.api_schemas import (
    AuthTokenRequest,
    EmailChangeRequest,
    InvitationCreateRequest,
    PasswordResetCompleteRequest,
    PasswordResetRequest,
    RegisterRequest,
)
from web_backend.auth_service import AuthService, AuthServiceError
from web_backend.security import SESSION_COOKIE, LoginAttemptLimiter, normalize_email
from web_backend.settings import Settings


def _raise_http(error: AuthServiceError) -> NoReturn:
    raise HTTPException(status_code=error.status_code, detail=error.detail) from error


def _create_invitation_management_router(
    auth_service: AuthService,
    current_user: Callable[..., dict[str, Any]],
) -> APIRouter:
    router = APIRouter()
    User = Annotated[dict[str, Any], Depends(current_user)]

    def require_admin(user: dict[str, Any]) -> None:
        if not user.get("is_admin"):
            raise HTTPException(status_code=403, detail="仅系统管理员可管理团队邀请")

    @router.get("/api/invitations")
    def invitations(user: User) -> list[dict[str, Any]]:
        require_admin(user)
        return auth_service.list_pending_invitations()

    @router.post("/api/invitations", status_code=201)
    def create_invitation(
        payload: InvitationCreateRequest,
        user: User,
    ) -> dict[str, Any]:
        require_admin(user)
        try:
            return auth_service.create_invitation(payload.email, str(user["id"]))
        except AuthServiceError as error:
            _raise_http(error)

    @router.post("/api/invitations/{invitation_id}/resend", status_code=201)
    def resend_invitation(invitation_id: str, user: User) -> dict[str, Any]:
        require_admin(user)
        try:
            return auth_service.resend_invitation(invitation_id, str(user["id"]))
        except AuthServiceError as error:
            _raise_http(error)

    @router.post("/api/invitations/{invitation_id}/revoke", status_code=204)
    def revoke_invitation(invitation_id: str, user: User) -> Response:
        require_admin(user)
        try:
            auth_service.revoke_invitation(invitation_id, str(user["id"]))
        except AuthServiceError as error:
            _raise_http(error)
        return Response(status_code=204)

    return router


def _create_registration_router(
    auth_service: AuthService,
    settings: Settings,
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/auth/invitations/validate")
    def validate_invitation(payload: AuthTokenRequest) -> dict[str, Any]:
        try:
            return auth_service.validate_invitation(payload.token)
        except AuthServiceError as error:
            _raise_http(error)

    @router.post("/api/auth/register")
    def register(payload: RegisterRequest, response: Response) -> dict[str, Any]:
        try:
            result = auth_service.register(
                payload.token,
                payload.display_name,
                payload.password,
            )
        except AuthServiceError as error:
            _raise_http(error)
        response.set_cookie(
            key=SESSION_COOKIE,
            value=result.session.token,
            httponly=True,
            secure=settings.secure_cookies,
            samesite="lax",
            max_age=settings.session_days * 24 * 60 * 60,
            path="/",
        )
        return result.user

    return router


def _create_password_reset_router(
    auth_service: AuthService,
    reset_account_limiter: LoginAttemptLimiter,
    reset_address_limiter: LoginAttemptLimiter,
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/auth/password-reset/request", status_code=204)
    def request_password_reset(
        payload: PasswordResetRequest,
        request: Request,
    ) -> Response:
        try:
            email = normalize_email(payload.email)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        address = request.client.host if request.client else "unknown"
        retry_after = max(
            reset_account_limiter.retry_after(email),
            reset_address_limiter.retry_after(address),
        )
        if retry_after:
            raise HTTPException(
                status_code=429,
                detail="密码重置请求过于频繁，请稍后再试",
                headers={"Retry-After": str(retry_after)},
            )
        reset_account_limiter.record_failure(email)
        reset_address_limiter.record_failure(address)
        auth_service.request_password_reset(email)
        return Response(status_code=204)

    @router.post("/api/auth/password-reset/validate")
    def validate_password_reset(payload: AuthTokenRequest) -> dict[str, bool]:
        try:
            auth_service.validate_password_reset(payload.token)
        except AuthServiceError as error:
            _raise_http(error)
        return {"valid": True}

    @router.post("/api/auth/password-reset/complete", status_code=204)
    def complete_password_reset(
        payload: PasswordResetCompleteRequest,
    ) -> Response:
        try:
            auth_service.complete_password_reset(payload.token, payload.new_password)
        except AuthServiceError as error:
            _raise_http(error)
        return Response(status_code=204)

    return router


def _create_email_change_router(
    auth_service: AuthService,
    account_limiter: LoginAttemptLimiter,
    address_limiter: LoginAttemptLimiter,
    current_user: Callable[..., dict[str, Any]],
) -> APIRouter:
    router = APIRouter()
    User = Annotated[dict[str, Any], Depends(current_user)]

    @router.post("/api/auth/email-change/request", status_code=204)
    def request_email_change(
        payload: EmailChangeRequest,
        request: Request,
        user: User,
    ) -> Response:
        account_key = f"email-change:{user['id']}"
        address = request.client.host if request.client else "unknown"
        address_key = f"email-change:{address}"
        retry_after = max(
            account_limiter.retry_after(account_key),
            address_limiter.retry_after(address_key),
        )
        if retry_after:
            raise HTTPException(
                status_code=429,
                detail="邮箱修改请求过于频繁，请稍后再试",
                headers={"Retry-After": str(retry_after)},
            )
        account_limiter.record_failure(account_key)
        address_limiter.record_failure(address_key)
        try:
            auth_service.request_email_change(
                str(user["id"]),
                payload.current_password,
                payload.new_email,
            )
        except AuthServiceError as error:
            _raise_http(error)
        return Response(status_code=204)

    @router.post("/api/auth/email-change/validate")
    def validate_email_change(payload: AuthTokenRequest) -> dict[str, Any]:
        try:
            return auth_service.validate_email_change(payload.token)
        except AuthServiceError as error:
            _raise_http(error)

    @router.post("/api/auth/email-change/complete", status_code=204)
    def complete_email_change(
        payload: AuthTokenRequest,
        response: Response,
    ) -> Response:
        try:
            auth_service.complete_email_change(payload.token)
        except AuthServiceError as error:
            _raise_http(error)
        response.delete_cookie(SESSION_COOKIE, path="/")
        response.status_code = 204
        return response

    return router


def create_auth_action_router(
    auth_service: AuthService,
    settings: Settings,
    reset_account_limiter: LoginAttemptLimiter,
    reset_address_limiter: LoginAttemptLimiter,
    current_user: Callable[..., dict[str, Any]],
) -> APIRouter:
    router = APIRouter()
    router.include_router(
        _create_invitation_management_router(auth_service, current_user)
    )
    router.include_router(_create_registration_router(auth_service, settings))
    router.include_router(
        _create_password_reset_router(
            auth_service,
            reset_account_limiter,
            reset_address_limiter,
        )
    )
    router.include_router(
        _create_email_change_router(
            auth_service,
            reset_account_limiter,
            reset_address_limiter,
            current_user,
        )
    )
    return router
