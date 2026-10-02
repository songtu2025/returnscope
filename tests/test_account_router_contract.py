from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated, Any
from unittest.mock import Mock

import pytest
from fastapi import Cookie, FastAPI, HTTPException
from fastapi.testclient import TestClient
from test_auth_flows import _login_admin, _settings

from web_backend.database import Database
from web_backend.routers import accounts
from web_backend.security import (
    SESSION_COOKIE,
    LoginAttemptLimiter,
    SessionService,
    hash_password,
    verify_password,
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
        for name in ("listing", "insight_report", "classification_standard_validation")
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


@pytest.mark.parametrize("method,path,payload", PROTECTED_ROUTES)
def test_protected_routes_require_session(harness, method, path, payload) -> None:
    response = harness.client.request(method, path, json=payload)
    assert response.status_code == 401
    assert response.json() == {"detail": "请先登录"}
    harness.task_service.running_count.assert_not_called()


@pytest.mark.parametrize("method,path,payload", PROTECTED_ROUTES[2:5])
def test_team_routes_require_admin(harness, method, path, payload) -> None:
    token = harness.sessions.create("member").token
    harness.client.cookies.set(SESSION_COOKIE, token)
    response = harness.client.request(method, path, json=payload)
    assert response.status_code == 403
    assert response.json() == {"detail": "仅系统管理员可管理团队账号"}
    with harness.database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 3
        assert connection.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0] == 0


@pytest.mark.parametrize("email", ["invalid", "@example.com", "user@", " "])
def test_login_rejects_invalid_email(harness, email) -> None:
    response = harness.client.post(
        "/api/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "请输入有效邮箱"}
    harness.account_limiter.retry_after.assert_not_called()
    harness.address_limiter.retry_after.assert_not_called()


@pytest.mark.parametrize(
    "account_delay,address_delay", [(12, 31), (31, 12), (0, 31), (31, 0)]
)
def test_login_uses_larger_retry_after(harness, account_delay, address_delay) -> None:
    harness.account_limiter.retry_after.return_value = account_delay
    harness.address_limiter.retry_after.return_value = address_delay
    response = harness.client.post(
        "/api/auth/login", json={"email": " Admin@Example.com ", "password": PASSWORD}
    )
    assert response.status_code == 429
    assert response.headers["retry-after"] == "31"
    harness.account_limiter.retry_after.assert_called_once_with("admin@example.com")
    harness.address_limiter.retry_after.assert_called_once_with("testclient")
    harness.account_limiter.record_failure.assert_not_called()
    harness.address_limiter.record_failure.assert_not_called()
    assert SESSION_COOKIE not in harness.client.cookies


@pytest.mark.parametrize(
    "email", ["admin@example.com", "missing@example.com", "inactive@example.com"]
)
def test_failed_login_records_both_limiters(harness, monkeypatch, email) -> None:
    verifier = Mock(return_value=False)
    monkeypatch.setattr(accounts, "verify_password", verifier)
    response = harness.client.post(
        "/api/auth/login", json={"email": email, "password": "wrong"}
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "邮箱或密码错误"}
    verifier.assert_called_once_with("wrong", harness.password_hash)
    harness.account_limiter.record_failure.assert_called_once_with(email)
    harness.address_limiter.record_failure.assert_called_once_with("testclient")
    harness.account_limiter.clear.assert_not_called()
    assert SESSION_COOKIE not in harness.client.cookies


@pytest.mark.parametrize(
    "harness",
    [{"secure_cookies": False}, {"secure_cookies": True, "session_days": 2}],
    indirect=True,
)
def test_login_cookie_and_session_contract(harness) -> None:
    response = harness.client.post(
        "/api/auth/login", json={"email": " Admin@Example.com ", "password": PASSWORD}
    )
    assert response.status_code == 200
    assert response.json() == {
        "id": "admin",
        "email": "admin@example.com",
        "display_name": "管理员",
        "is_admin": True,
    }
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Path=/" in cookie
    assert f"Max-Age={harness.settings.session_days * 86400}" in cookie
    assert ("Secure" in cookie) == harness.settings.secure_cookies
    assert harness.client.get("/api/auth/me").json()["id"] == "admin"
    harness.account_limiter.clear.assert_called_once_with("admin@example.com")
    harness.address_limiter.clear.assert_not_called()
    with harness.database.connect() as connection:
        assert connection.execute(
            "SELECT last_seen_at FROM users WHERE id = 'admin'"
        ).fetchone()[0]


@pytest.mark.parametrize("with_session", [False, True])
def test_logout_only_removes_current_session(harness, with_session) -> None:
    preserved = harness.sessions.create("member").token
    if with_session:
        _login_admin(harness.client)
        removed = harness.client.cookies.get(SESSION_COOKIE)
    response = harness.client.post("/api/auth/logout")
    assert response.status_code == 204
    assert response.content == b""
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert "Path=/" in response.headers["set-cookie"]
    assert harness.sessions.resolve(preserved)["id"] == "member"
    if with_session:
        assert harness.sessions.resolve(removed) is None


@pytest.mark.parametrize(
    "current_password,new_password,status",
    [
        ("wrong", "replacement-password", 400),
        (PASSWORD, "12345678901", 400),
        (PASSWORD, "short", 422),
    ],
)
def test_rejected_password_change_preserves_state(
    harness, current_password, new_password, status
) -> None:
    _login_admin(harness.client)
    response = harness.client.post(
        "/api/auth/password",
        json={"current_password": current_password, "new_password": new_password},
    )
    assert response.status_code == status
    assert harness.client.get("/api/auth/me").status_code == 200
    with harness.database.connect() as connection:
        assert (
            connection.execute(
                "SELECT password_hash FROM users WHERE id = 'admin'"
            ).fetchone()[0]
            == harness.password_hash
        )
        assert connection.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0] == 0


def test_password_change_revokes_all_own_sessions_and_records_audit(harness) -> None:
    _login_admin(harness.client)
    second = harness.sessions.create("admin").token
    other = harness.sessions.create("member").token
    response = harness.client.post(
        "/api/auth/password",
        json={"current_password": PASSWORD, "new_password": "replacement-password"},
    )
    assert response.status_code == 204
    assert response.content == b""
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert harness.client.get("/api/auth/me").status_code == 401
    assert harness.sessions.resolve(second) is None
    assert harness.sessions.resolve(other)["id"] == "member"
    with harness.database.connect() as connection:
        row = connection.execute(
            "SELECT password_hash FROM users WHERE id = 'admin'"
        ).fetchone()
        assert verify_password("replacement-password", row["password_hash"])
        audit = connection.execute("SELECT * FROM audit_logs").fetchone()
        assert (
            audit["entity_type"],
            audit["entity_id"],
            audit["action"],
            audit["actor_id"],
        ) == ("user", "admin", "change_password", "admin")


@pytest.mark.parametrize(
    "target,payload,status,detail",
    [
        ("admin", STATUS_BODY, 400, "不能停用自己的账号"),
        ("member", {**STATUS_BODY, "note": "  "}, 400, "请填写账号状态修改原因"),
        ("missing", STATUS_BODY, 404, "团队账号不存在"),
        (
            "member",
            {**STATUS_BODY, "expected_active": False},
            409,
            "账号状态已被他人修改，请刷新后重试",
        ),
        ("member", {**STATUS_BODY, "active": True}, 400, "账号状态没有变化"),
    ],
)
def test_status_rejections_leave_user_session_and_audit_unchanged(
    harness, target, payload, status, detail
) -> None:
    _login_admin(harness.client)
    member_session = harness.sessions.create("member").token
    response = harness.client.patch(f"/api/users/{target}", json=payload)
    assert response.status_code == status
    assert response.json() == {"detail": detail}
    assert harness.sessions.resolve(member_session)["id"] == "member"
    with harness.database.connect() as connection:
        assert (
            connection.execute(
                "SELECT active FROM users WHERE id = 'member'"
            ).fetchone()[0]
            == 1
        )
        assert connection.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0] == 0


@pytest.mark.parametrize("active,target", [(False, "member"), (True, "inactive")])
def test_status_change_records_before_after_and_revokes_disabled_sessions(
    harness, active, target
) -> None:
    _login_admin(harness.client)
    tokens = [harness.sessions.create(target).token for _ in range(2)]
    response = harness.client.patch(
        f"/api/users/{target}",
        json={"active": active, "expected_active": not active, "note": " 状态调整 "},
    )
    assert response.status_code == 200
    assert response.json()["id"] == target
    assert response.json()["active"] == int(active)
    users = harness.client.get("/api/users").json()
    user = next(user for user in users if user["id"] == target)
    assert user["audit"][0]["action"] == ("activate" if active else "deactivate")
    assert user["audit"][0]["actor_id"] == "admin"
    assert user["audit"][0]["before"] == {"active": not active}
    assert user["audit"][0]["after"] == {"active": active, "note": "状态调整"}
    if not active:
        assert all(harness.sessions.resolve(token) is None for token in tokens)


def test_team_creation_normalizes_fields_and_listing_contains_audit(harness) -> None:
    _login_admin(harness.client)
    created = harness.client.post(
        "/api/users",
        json={**CREATE_BODY, "email": " New@Example.com ", "display_name": " 新成员 "},
    )
    assert created.status_code == 201
    user_id = created.json()["id"]
    assert created.json() == {
        "id": user_id,
        "email": "new@example.com",
        "display_name": "新成员",
        "created_by": "admin",
    }
    users = harness.client.get("/api/users").json()
    assert [user["id"] for user in users[:3]] == ["admin", "member", "inactive"]
    user = next(user for user in users if user["id"] == user_id)
    assert set(user) == {
        "id",
        "email",
        "display_name",
        "active",
        "created_at",
        "last_seen_at",
        "audit",
    }
    assert user["audit"][0]["action"] == "create"
    assert user["audit"][0]["after"] == {
        "email": "new@example.com",
        "display_name": "新成员",
    }
    duplicate = harness.client.post("/api/users", json=CREATE_BODY)
    assert duplicate.status_code == 409
    assert duplicate.json() == {"detail": "该邮箱已存在"}
    with harness.database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 4


@pytest.mark.parametrize(
    "payload,status",
    [
        ({**CREATE_BODY, "email": "invalid"}, 400),
        ({**CREATE_BODY, "password": "short"}, 422),
    ],
)
def test_invalid_creation_does_not_write_user_or_audit(
    harness, payload, status
) -> None:
    _login_admin(harness.client)
    assert harness.client.post("/api/users", json=payload).status_code == status
    with harness.database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 3
        assert connection.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0] == 0


@pytest.mark.parametrize(
    "harness", [{"start_worker": False}, {"start_worker": True}], indirect=True
)
@pytest.mark.parametrize(
    "worker_name", ["listing", "insight_report", "classification_standard_validation"]
)
@pytest.mark.parametrize("issue", ["stopped", "error"])
def test_health_tracks_each_worker_and_disabled_mode(
    harness, worker_name, issue
) -> None:
    worker = harness.workers[worker_name]
    worker.is_alive = issue != "stopped"
    worker.health = {
        "last_error_type": "SyntheticError" if issue == "error" else None,
        "last_error_at": "2026-10-02" if issue == "error" else None,
    }
    response = harness.client.get("/api/health")
    if not harness.start_worker:
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == payload["worker"] == "ok"
        assert all(
            item == {"status": "ok", "last_error": None, "last_error_at": None}
            for item in payload["workers"].values()
        )
    else:
        status = 200 if issue == "error" else 503
        assert response.status_code == status
        payload = response.json()["detail"] if status == 503 else response.json()
        assert payload["status"] == "degraded"
        assert payload["worker"] == ("degraded" if issue == "error" else "unavailable")
        assert payload["workers"][worker_name]["status"] == (
            "degraded" if issue == "error" else "unavailable"
        )
        assert (
            payload["workers"][worker_name]["last_error"]
            == worker.health["last_error_type"]
        )
    assert payload["database"] == "ok"
    assert set(payload["workers"]) == {
        "listing",
        "insight_report",
        "classification_standard_validation",
    }


@pytest.mark.parametrize(
    "harness", [{"start_worker": False}, {"start_worker": True}], indirect=True
)
def test_system_status_uses_current_user_and_worker_switch(harness) -> None:
    token = harness.sessions.create("member").token
    harness.client.cookies.set(SESSION_COOKIE, token)
    harness.workers["listing"].is_alive = False
    response = harness.client.get("/api/system/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["user"]["id"] == "member"
    assert payload["task_counts"] == {}
    assert payload["pending_reviews"] == payload["pending_review_batches"] == 0
    assert payload["my_running_tasks"] == payload["my_running_segments"] == 3
    assert payload["worker_concurrency"] == harness.settings.task_workers
    assert payload["warnings"] == []
    assert payload["worker_status"] == ("unavailable" if harness.start_worker else "ok")
    harness.task_service.running_count.assert_called_once_with("member")


@pytest.mark.parametrize("harness", [{"start_worker": True}], indirect=True)
def test_health_prioritizes_stopped_worker_over_recent_error(harness) -> None:
    harness.workers["listing"].health = {
        "last_error_type": "SyntheticError",
        "last_error_at": "2026-10-02",
    }
    harness.workers["insight_report"].is_alive = False
    response = harness.client.get("/api/health")
    assert response.status_code == 503
    payload = response.json()["detail"]
    assert payload["worker"] == "unavailable"
    assert payload["workers"]["listing"]["status"] == "degraded"
    assert payload["workers"]["insight_report"]["status"] == "unavailable"


@pytest.mark.parametrize(
    "harness,warnings",
    [
        ({"bootstrap_password": "change-me-now"}, ["仍在使用默认初始密码"]),
        ({"encryption_key": ""}, ["仍在使用开发环境加密密钥"]),
        (
            {"bootstrap_password": "change-me-now", "encryption_key": ""},
            ["仍在使用默认初始密码", "仍在使用开发环境加密密钥"],
        ),
    ],
    indirect=["harness"],
)
def test_system_status_preserves_configuration_warnings(harness, warnings) -> None:
    _login_admin(harness.client)
    assert harness.client.get("/api/system/status").json()["warnings"] == warnings
