from unittest.mock import Mock

import pytest
from account_router_helpers import PASSWORD, PROTECTED_ROUTES
from account_router_helpers import harness as harness
from test_auth_flows import _login_admin

from web_backend.routers import accounts
from web_backend.security import (
    SESSION_COOKIE,
    verify_password,
)


@pytest.mark.parametrize("method,path,payload", PROTECTED_ROUTES)
def test_protected_routes_require_session(harness, method, path, payload) -> None:
    response = harness.client.request(method, path, json=payload)
    assert response.status_code == 401
    assert response.json() == {"detail": "请先登录"}
    harness.task_service.running_count.assert_not_called()


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
