from dataclasses import dataclass
from typing import Annotated, Any, Callable

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response

from web_backend.api_contracts.accounts import (
    LoginRequest,
    PasswordChangeRequest,
)
from web_backend.classification_standard_validation_worker import (
    ClassificationStandardValidationWorker,
)
from web_backend.common import add_audit
from web_backend.database import Database
from web_backend.insight_report_worker import InsightReportWorker
from web_backend.routers.account_directory_routes import (
    _email,
    _register_team_routes,
    _register_user_status_route,
)
from web_backend.routers.account_monitoring_routes import (
    _MonitoringDependencies,
    _register_health_route,
    _register_system_status_route,
)
from web_backend.security import (
    SESSION_COOKIE,
    LoginAttemptLimiter,
    SessionService,
    hash_password,
    utc_now,
    verify_password,
)
from web_backend.settings import Settings
from web_backend.task_service import TaskService
from web_backend.worker import TaskWorker


@dataclass(frozen=True)
class _LoginSecurity:
    account_limiter: LoginAttemptLimiter
    address_limiter: LoginAttemptLimiter
    dummy_password_hash: str


def create_account_router(
    database: Database,
    settings: Settings,
    session_service: SessionService,
    account_login_limiter: LoginAttemptLimiter,
    address_login_limiter: LoginAttemptLimiter,
    dummy_password_hash: str,
    task_service: TaskService,
    worker: TaskWorker,
    insight_report_worker: InsightReportWorker,
    standard_validation_worker: ClassificationStandardValidationWorker,
    start_worker: bool,
    current_user: Callable[..., dict[str, Any]],
) -> APIRouter:
    router = APIRouter()
    login_security = _LoginSecurity(
        account_limiter=account_login_limiter,
        address_limiter=address_login_limiter,
        dummy_password_hash=dummy_password_hash,
    )
    monitoring = _MonitoringDependencies(
        task_service=task_service,
        worker=worker,
        insight_report_worker=insight_report_worker,
        standard_validation_worker=standard_validation_worker,
        start_worker=start_worker,
    )
    _register_health_route(router, database, monitoring)
    _register_login_route(router, database, settings, session_service, login_security)
    _register_session_routes(router, session_service, current_user)
    _register_password_route(router, database, settings, current_user)
    _register_team_routes(router, database, current_user)
    _register_user_status_route(router, database, current_user)
    _register_system_status_route(router, database, settings, monitoring, current_user)
    return router


def _register_login_route(
    router: APIRouter,
    database: Database,
    settings: Settings,
    session_service: SessionService,
    security: _LoginSecurity,
) -> None:
    account_login_limiter = security.account_limiter
    address_login_limiter = security.address_limiter
    dummy_password_hash = security.dummy_password_hash

    @router.post("/api/auth/login")
    def login(
        payload: LoginRequest,
        request: Request,
        response: Response,
    ) -> dict[str, Any]:
        try:
            email = _email(payload.email)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        address = request.client.host if request.client else "unknown"
        retry_after = max(
            account_login_limiter.retry_after(email),
            address_login_limiter.retry_after(address),
        )
        if retry_after:
            raise HTTPException(
                status_code=429,
                detail="登录尝试过于频繁，请稍后再试",
                headers={"Retry-After": str(retry_after)},
            )
        with database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE email = ? AND active = 1",
                (email,),
            ).fetchone()
        password_hash = (
            str(row["password_hash"]) if row is not None else dummy_password_hash
        )
        if not verify_password(
            payload.password,
            password_hash,
        ):
            account_login_limiter.record_failure(email)
            address_login_limiter.record_failure(address)
            raise HTTPException(status_code=401, detail="邮箱或密码错误")
        account_login_limiter.clear(email)
        session = session_service.create(str(row["id"]))
        response.set_cookie(
            key=SESSION_COOKIE,
            value=session.token,
            httponly=True,
            secure=settings.secure_cookies,
            samesite="lax",
            max_age=settings.session_days * 24 * 60 * 60,
            path="/",
        )
        with database.transaction() as connection:
            connection.execute(
                "UPDATE users SET last_seen_at = ? WHERE id = ?",
                (utc_now(), row["id"]),
            )
        return {
            "id": row["id"],
            "email": row["email"],
            "display_name": row["display_name"],
            "is_admin": bool(row["is_admin"]),
        }


def _register_session_routes(
    router: APIRouter,
    session_service: SessionService,
    current_user: Callable[..., dict[str, Any]],
) -> None:
    User = Annotated[dict[str, Any], Depends(current_user)]

    @router.post("/api/auth/logout", status_code=204)
    def logout(
        response: Response,
        session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
    ) -> Response:
        session_service.delete(session_token)
        response.delete_cookie(SESSION_COOKIE, path="/")
        response.status_code = 204
        return response

    @router.get("/api/auth/me")
    def me(user: User) -> dict[str, Any]:
        return user


def _register_password_route(
    router: APIRouter,
    database: Database,
    settings: Settings,
    current_user: Callable[..., dict[str, Any]],
) -> None:
    User = Annotated[dict[str, Any], Depends(current_user)]

    @router.post("/api/auth/password", status_code=204)
    def change_password(
        payload: PasswordChangeRequest,
        user: User,
        response: Response,
    ) -> Response:
        with database.connect() as connection:
            row = connection.execute(
                "SELECT password_hash FROM users WHERE id = ?",
                (user["id"],),
            ).fetchone()
        if row is None or not verify_password(
            payload.current_password,
            str(row["password_hash"]),
        ):
            raise HTTPException(status_code=400, detail="当前密码错误")
        if len(payload.new_password) < settings.password_min_length:
            raise HTTPException(
                status_code=400,
                detail=f"密码至少需要 {settings.password_min_length} 位",
            )
        try:
            password_hash = hash_password(payload.new_password)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        with database.transaction(immediate=True) as connection:
            connection.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (password_hash, user["id"]),
            )
            connection.execute(
                "DELETE FROM sessions WHERE user_id = ?",
                (user["id"],),
            )
        add_audit(
            database,
            "user",
            str(user["id"]),
            "change_password",
            str(user["id"]),
        )
        response.delete_cookie(SESSION_COOKIE, path="/")
        response.status_code = 204
        return response
