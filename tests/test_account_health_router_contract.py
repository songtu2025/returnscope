import pytest
from account_router_helpers import harness as harness
from test_auth_flows import _login_admin

from web_backend.security import (
    SESSION_COOKIE,
)


@pytest.mark.parametrize(
    "harness", [{"start_worker": False}, {"start_worker": True}], indirect=True
)
@pytest.mark.parametrize(
    "worker_name",
    [
        "listing",
        "insight_report",
        "classification_standard_validation",
        "result_export",
    ],
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
        "result_export",
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
