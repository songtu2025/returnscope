import pytest
from account_router_helpers import harness as harness
from test_auth_flows import _login_admin
from test_task_scheduling import _runtime

from web_backend.api_contracts.accounts import UserStatusRequest
from web_backend.api_contracts.datasets import DimensionRowUpdateRequest
from web_backend.api_contracts.tasks import TaskActionRequest, TaskSegmentRetryRequest
from web_backend.common import json_value


def test_operation_contracts_allow_omitted_notes():
    assert TaskActionRequest(expected_revision=1).note == ""
    assert TaskSegmentRetryRequest(expected_revision=1).reason == ""
    assert UserStatusRequest(active=False, expected_active=True).note == ""
    assert (
        DimensionRowUpdateRequest(
            row_index=0, expected_version=1, changes={"产品名称": "验收商品"}
        ).change_note
        == ""
    )


@pytest.mark.parametrize("kind", ["task", "listing", "retry", "resume"])
def test_task_actions_without_notes_keep_audit_and_revision(tmp_path, kind):
    database, service, task = _runtime(tmp_path)
    if kind == "task":
        result = service.cancel(task["id"], "user-1", "", task["revision"])
    elif kind == "listing":
        segment = next(s for s in task["segments"] if s["status"] == "queued")
        result = service.segment_action(
            task["id"], segment["segment_key"], "cancel", "user-1", task["revision"]
        )
    elif kind == "retry":
        segment = next(s for s in task["segments"] if s["status"] == "failed")
        result = service.retry_segment(
            task["id"], segment["segment_key"], "user-1", task["revision"], ""
        )
    else:
        with database.transaction() as connection:
            connection.execute(
                "UPDATE tasks SET status='paused' WHERE id=?", (task["id"],)
            )
        result = service.resume(task["id"], "user-1", task["revision"], "")
    assert result["revision"] == task["revision"] + 1
    with database.connect() as connection:
        audit = connection.execute(
            "SELECT * FROM audit_logs WHERE actor_id='user-1' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    assert audit is not None
    after = json_value(audit["after_json"], {})
    assert after.get("note") or after.get("reason")


@pytest.mark.parametrize("active,target", [(False, "member"), (True, "inactive")])
def test_account_status_without_note_still_revokes_sessions_and_audits(
    harness, active, target
):
    _login_admin(harness.client)
    token = harness.sessions.create(target).token
    response = harness.client.patch(
        f"/api/users/{target}", json={"active": active, "expected_active": not active}
    )
    assert response.status_code == 200
    if not active:
        assert harness.sessions.resolve(token) is None
    with harness.database.connect() as connection:
        row = connection.execute(
            "SELECT after_json FROM audit_logs WHERE entity_id=?", (target,)
        ).fetchone()
    assert json_value(row["after_json"], {})["note"] == (
        "恢复账号" if active else "停用账号"
    )
