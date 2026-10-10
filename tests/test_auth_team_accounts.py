from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from test_auth_flows import FakeMailSender, _login_admin, _settings, _token_from_url

from web_backend.security import SESSION_COOKIE


def test_team_accounts_are_not_limited_to_five(tmp_path: Path) -> None:
    from web_backend.app import create_app

    sender = FakeMailSender()
    app = create_app(
        start_worker=False,
        settings_override=_settings(tmp_path),
        mail_sender_override=sender,
    )

    with TestClient(app) as client:
        _login_admin(client)
        for index in range(1, 7):
            response = client.post(
                "/api/invitations",
                json={"email": f"member{index}@example.com"},
            )
            assert response.status_code == 201
        assert len(client.get("/api/invitations").json()) == 6

        for index, invitation in enumerate(sender.invitations, start=1):
            registered = client.post(
                "/api/auth/register",
                json={
                    "token": _token_from_url(invitation["url"]),
                    "display_name": f"成员 {index}",
                    "password": "member-password-123",
                },
            )
            assert registered.status_code == 200

        member = registered.json()
        member_session = client.cookies.get(SESSION_COOKIE)
        assert member_session is not None
        _login_admin(client)
        assert len(client.get("/api/users").json()) == 7

        deactivated = client.patch(
            f"/api/users/{member['id']}",
            json={"active": False, "expected_active": True, "note": "暂时离岗"},
        )
        assert deactivated.status_code == 200
        assert deactivated.json()["active"] == 0
        with app.state.database.connect() as connection:
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM sessions WHERE user_id = ?", (member["id"],)
                ).fetchone()[0]
                == 0
            )

        stale_update = client.patch(
            f"/api/users/{member['id']}",
            json={"active": True, "expected_active": True, "note": "过期页面"},
        )
        assert stale_update.status_code == 409
        reactivated = client.patch(
            f"/api/users/{member['id']}",
            json={"active": True, "expected_active": False, "note": "恢复工作"},
        )
        assert reactivated.status_code == 200
        assert reactivated.json()["active"] == 1
        users = client.get("/api/users").json()
        assert sum(user["active"] for user in users) == 7
        restored = next(user for user in users if user["id"] == member["id"])
        assert restored["audit"][0]["action"] == "activate"
        assert restored["audit"][0]["before"] == {"active": False}
        assert restored["audit"][0]["after"] == {
            "active": True,
            "note": "恢复工作",
        }
        client.cookies.clear()
        client.cookies.set(SESSION_COOKIE, member_session)
        assert client.get("/api/auth/me").status_code == 401
        login = client.post(
            "/api/auth/login",
            json={"email": member["email"], "password": "member-password-123"},
        )
        assert login.status_code == 200
        assert client.get("/api/auth/me").json()["id"] == member["id"]


def test_direct_team_accounts_are_not_limited_to_five(tmp_path: Path) -> None:
    from web_backend.app import create_app

    app = create_app(
        start_worker=False,
        settings_override=_settings(tmp_path),
        mail_sender_override=FakeMailSender(),
    )
    with TestClient(app) as client:
        _login_admin(client)
        admin_id = client.get("/api/auth/me").json()["id"]
        for index in range(1, 7):
            response = client.post(
                "/api/users",
                json={
                    "email": f"direct{index}@example.com",
                    "display_name": f"直接创建成员 {index}",
                    "password": "member-password-123",
                },
            )
            assert response.status_code == 201
            assert response.json()["created_by"] == admin_id
        users = client.get("/api/users").json()
        assert len(users) == 7
        assert sum(user["active"] for user in users) == 7
        member = next(user for user in users if user["email"] == "direct6@example.com")
        assert member["audit"][0]["action"] == "create"
        assert member["audit"][0]["actor_id"] == admin_id
        duplicate = client.post(
            "/api/users",
            json={
                "email": " Direct6@Example.com ",
                "display_name": "重复成员",
                "password": "member-password-123",
            },
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["detail"] == "该邮箱已存在"
        assert len(client.get("/api/users").json()) == 7
