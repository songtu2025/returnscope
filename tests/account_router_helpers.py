from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated, Any
from unittest.mock import Mock

import pytest
from fastapi import Cookie, FastAPI, HTTPException
from fastapi.testclient import TestClient
from test_auth_flows import _settings

from web_backend.database import Database
from web_backend.routers import accounts
from web_backend.security import (
    SESSION_COOKIE,
    LoginAttemptLimiter,
    SessionService,
    hash_password,
)
from web_backend.task_service import TaskService

PASSWORD = "test-password-123"


CREATE_BODY = {
    "email": "new@example.com",
    "display_name": "新成员",
    "password": PASSWORD,
}


STATUS_BODY = {"active": False, "expected_active": True, "note": "暂时离岗"}


PROTECTED_ROUTES = (
    ("GET", "/api/auth/me", None),
    (
        "POST",
        "/api/auth/password",
        {"current_password": PASSWORD, "new_password": PASSWORD},
    ),
    ("GET", "/api/users", None),
    ("POST", "/api/users", CREATE_BODY),
    ("PATCH", "/api/users/member", STATUS_BODY),
    ("GET", "/api/system/status", None),
)


@pytest.fixture
def harness(
    tmp_path: Path, request: pytest.FixtureRequest
) -> Iterator[SimpleNamespace]:
    options = dict(getattr(request, "param", {}))
    start_worker = options.pop("start_worker", False)
    settings = replace(_settings(tmp_path), **options)
    database = Database(tmp_path / "app.db")
    database.initialize()
    password_hash = hash_password(PASSWORD)
    with database.transaction() as connection:
        connection.executemany(
            """
            INSERT INTO users(id, email, display_name, password_hash,
                active, is_admin, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "admin",
                    "admin@example.com",
                    "管理员",
                    password_hash,
                    1,
                    1,
                    "2026-01-01",
                ),
                (
                    "member",
                    "member@example.com",
                    "成员",
                    password_hash,
                    1,
                    0,
                    "2026-01-02",
                ),
                (
                    "inactive",
                    "inactive@example.com",
                    "停用成员",
                    password_hash,
                    0,
                    0,
                    "2026-01-03",
                ),
            ],
        )
    sessions = SessionService(database, settings.session_days)
    account_limiter = Mock(spec=LoginAttemptLimiter)
    address_limiter = Mock(spec=LoginAttemptLimiter)
    account_limiter.retry_after.return_value = 0
    address_limiter.retry_after.return_value = 0
    task_service = Mock(spec=TaskService)
    task_service.running_count.return_value = 3
    workers = {
        name: SimpleNamespace(
            is_alive=True,
            health={"last_error_type": None, "last_error_at": None},
        )
        for name in (
            "listing",
            "insight_report",
            "classification_standard_validation",
            "result_export",
        )
    }

    def current_user(
        token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
    ) -> dict[str, Any]:
        user = sessions.resolve(token)
        if user is None:
            raise HTTPException(status_code=401, detail="请先登录")
        return dict(user)

    app = FastAPI()
    router = accounts.create_account_router(
        database=database,
        settings=settings,
        session_service=sessions,
        account_login_limiter=account_limiter,
        address_login_limiter=address_limiter,
        dummy_password_hash=password_hash,
        task_service=task_service,
        worker=workers["listing"],
        insight_report_worker=workers["insight_report"],
        standard_validation_worker=workers["classification_standard_validation"],
        export_worker=workers["result_export"],
        start_worker=start_worker,
        current_user=current_user,
    )
    app.include_router(router)
    with TestClient(app, base_url="https://example.test") as client:
        yield SimpleNamespace(
            app=app,
            router=router,
            client=client,
            database=database,
            sessions=sessions,
            account_limiter=account_limiter,
            address_limiter=address_limiter,
            task_service=task_service,
            workers=workers,
            settings=settings,
            password_hash=password_hash,
            start_worker=start_worker,
        )
