from typing import Annotated, Any, Callable

from fastapi import APIRouter, Depends, HTTPException

from web_backend.api_contracts.accounts import UserCreateRequest, UserStatusRequest
from web_backend.common import add_audit, list_audit, new_id
from web_backend.database import Database
from web_backend.security import hash_password, utc_now


def _email(value: str) -> str:
    email = value.strip().lower()
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        raise ValueError("请输入有效邮箱")
    return email


def _require_account_admin(user: dict[str, Any]) -> None:
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="仅系统管理员可管理团队账号")


def _register_team_routes(
    router: APIRouter,
    database: Database,
    current_user: Callable[..., dict[str, Any]],
) -> None:
    User = Annotated[dict[str, Any], Depends(current_user)]

    @router.get("/api/users")
    def users(user: User) -> list[dict[str, Any]]:
        _require_account_admin(user)
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
        _require_account_admin(actor)
        try:
            email = _email(payload.email)
            password_hash = hash_password(payload.password)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        user_id = new_id("user")
        try:
            with database.transaction(immediate=True) as connection:
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


def _register_user_status_route(
    router: APIRouter,
    database: Database,
    current_user: Callable[..., dict[str, Any]],
) -> None:
    User = Annotated[dict[str, Any], Depends(current_user)]

    @router.patch("/api/users/{user_id}")
    def update_user_status(
        user_id: str,
        payload: UserStatusRequest,
        actor: User,
    ) -> dict[str, Any]:
        _require_account_admin(actor)
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
