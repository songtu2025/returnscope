from typing import Annotated, Any, Callable

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response

from web_backend.api_schemas import (
    LoginRequest,
    PasswordChangeRequest,
    UserCreateRequest,
    UserStatusRequest,
)
from web_backend.common import add_audit, list_audit, new_id
from web_backend.database import Database
from web_backend.security import (
    LoginAttemptLimiter,
    SessionService,
    hash_password,
    utc_now,
    verify_password,
)
from web_backend.settings import Settings
from web_backend.task_service import TaskService
from web_backend.worker import TaskWorker

SESSION_COOKIE = "seekway_session"


def _email(value: str) -> str:
    email = value.strip().lower()
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        raise ValueError("请输入有效邮箱")
    return email


def create_account_router(
    database: Database,
    settings: Settings,
    session_service: SessionService,
    account_login_limiter: LoginAttemptLimiter,
    address_login_limiter: LoginAttemptLimiter,
    dummy_password_hash: str,
    task_service: TaskService,
    worker: TaskWorker,
    start_worker: bool,
    current_user: Callable[..., dict[str, Any]],
) -> APIRouter:
    router = APIRouter()
    User = Annotated[dict[str, Any], Depends(current_user)]

    @router.get("/api/health")
    def health() -> dict[str, Any]:
        with database.connect() as connection:
            connection.execute("SELECT 1").fetchone()
        worker_ready = not start_worker or worker.is_alive
        payload = {
            "status": "ok" if worker_ready else "degraded",
            "database": "ok",
            "worker": "ok" if worker_ready else "unavailable",
            "time": utc_now(),
        }
        if not worker_ready:
            raise HTTPException(status_code=503, detail=payload)
        return payload

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

    @router.get("/api/users")
    def users(_user: User) -> list[dict[str, Any]]:
        with database.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, email, display_name, active, created_at, last_seen_at
                FROM users ORDER BY created_at ASC
                """
            ).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            item["audit"] = list_audit(database, "user", str(row["id"]))
            output.append(item)
        return output

    @router.post("/api/users", status_code=201)
    def create_user(payload: UserCreateRequest, actor: User) -> dict[str, Any]:
        try:
            email = _email(payload.email)
            password_hash = hash_password(payload.password)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        user_id = new_id("user")
        try:
            with database.transaction(immediate=True) as connection:
                active_count = connection.execute(
                    "SELECT COUNT(*) AS count FROM users WHERE active = 1"
                ).fetchone()
                if int(active_count["count"]) >= 5:
                    raise HTTPException(
                        status_code=409,
                        detail="最多可启用 5 个团队账号",
                    )
                connection.execute(
                    """
                    INSERT INTO users(
                        id, email, display_name, password_hash, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        email,
                        payload.display_name.strip(),
                        password_hash,
                        utc_now(),
                    ),
                )
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise HTTPException(status_code=409, detail="该邮箱已存在") from exc
            raise
        add_audit(
            database,
            "user",
            user_id,
            "create",
            str(actor["id"]),
            after={
                "email": email,
                "display_name": payload.display_name.strip(),
            },
        )
        return {
            "id": user_id,
            "email": email,
            "display_name": payload.display_name.strip(),
            "created_by": actor["id"],
        }

    @router.patch("/api/users/{user_id}")
    def update_user_status(
        user_id: str,
        payload: UserStatusRequest,
        actor: User,
    ) -> dict[str, Any]:
        if user_id == actor["id"] and not payload.active:
            raise HTTPException(status_code=400, detail="不能停用自己的账号")
        clean_note = payload.note.strip()
        if not clean_note:
            raise HTTPException(status_code=400, detail="请填写账号状态修改原因")
        with database.transaction(immediate=True) as connection:
            target = connection.execute(
                """
                SELECT id, email, display_name, active, created_at, last_seen_at
                FROM users WHERE id = ?
                """,
                (user_id,),
            ).fetchone()
            if target is None:
                raise HTTPException(status_code=404, detail="团队账号不存在")
            before_active = bool(target["active"])
            if before_active != payload.expected_active:
                raise HTTPException(
                    status_code=409,
                    detail="账号状态已被他人修改，请刷新后重试",
                )
            if before_active == payload.active:
                raise HTTPException(status_code=400, detail="账号状态没有变化")
            if payload.active and not before_active:
                active_count = connection.execute(
                    "SELECT COUNT(*) AS count FROM users WHERE active = 1"
                ).fetchone()
                if int(active_count["count"]) >= 5:
                    raise HTTPException(
                        status_code=409,
                        detail="最多可启用 5 个团队账号",
                    )
            connection.execute(
                "UPDATE users SET active = ? WHERE id = ?",
                (int(payload.active), user_id),
            )
            if not payload.active:
                connection.execute(
                    "DELETE FROM sessions WHERE user_id = ?",
                    (user_id,),
                )
        if before_active != payload.active:
            add_audit(
                database,
                "user",
                user_id,
                "activate" if payload.active else "deactivate",
                str(actor["id"]),
                before={"active": before_active},
                after={"active": payload.active, "note": clean_note},
            )
        return {
            **dict(target),
            "active": int(payload.active),
        }

    @router.get("/api/system/status")
    def system_status(user: User) -> dict[str, Any]:
        with database.connect() as connection:
            task_counts = {
                row["status"]: row["count"]
                for row in connection.execute(
                    "SELECT status, COUNT(*) AS count FROM tasks GROUP BY status"
                ).fetchall()
            }
            pending_reviews = connection.execute(
                """
                SELECT COUNT(*) AS count FROM review_records
                WHERE workflow_status = 'pending' AND batch_id IS NOT NULL
                """
            ).fetchone()["count"]
            pending_review_batches = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM review_batches AS batch
                WHERE batch.status = 'draft'
                  AND EXISTS (
                      SELECT 1
                      FROM review_records AS record
                      WHERE record.batch_id = batch.id
                        AND record.workflow_status = 'pending'
                  )
                """
            ).fetchone()["count"]
        warnings = []
        if settings.bootstrap_password == "change-me-now":
            warnings.append("仍在使用默认初始密码")
        if not settings.encryption_key:
            warnings.append("仍在使用开发环境加密密钥")
        running_segments = task_service.running_count(str(user["id"]))
        return {
            "user": user,
            "task_counts": task_counts,
            "pending_reviews": pending_reviews,
            "pending_review_batches": pending_review_batches,
            "my_running_tasks": running_segments,
            "my_running_segments": running_segments,
            "worker_concurrency": settings.task_workers,
            "worker_status": (
                "ok" if not start_worker or worker.is_alive else "unavailable"
            ),
            "warnings": warnings,
        }

    return router
