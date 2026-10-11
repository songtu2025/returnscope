import pytest
from account_router_helpers import CREATE_BODY, PROTECTED_ROUTES, STATUS_BODY
from account_router_helpers import harness as harness
from test_auth_flows import _login_admin

from web_backend.security import (
    SESSION_COOKIE,
)


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
