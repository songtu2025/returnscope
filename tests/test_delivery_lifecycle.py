import pytest
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.testclient import TestClient
from test_dashboard_versions import _create_dashboard, _ready_result
from test_insight_reports import _complete_report, _service_context

from return_semantics.model_client import JsonModelCallResult
from web_backend.classification_result_service import ClassificationResultService
from web_backend.delivery_lifecycle import (
    DeliveryLifecycleConflict,
    DeliveryLifecycleService,
)
from web_backend.operations_service import WorkbenchService
from web_backend.routers.delivery_lifecycle_routes import (
    register_delivery_actions,
    register_report_cancel,
)
from web_backend.task_service import TaskService


@pytest.mark.parametrize("source_removed", [False, True])
def test_referenced_result_deletion_and_dashboard_restore_are_guarded(
    tmp_path, source_removed
):
    context, version, dashboards = _ready_result(tmp_path)
    _, dashboard = _create_dashboard(dashboards, version["version_id"])
    lifecycle = DeliveryLifecycleService(context.database)
    results = ClassificationResultService(context.database)
    if source_removed:
        with context.database.transaction() as connection:
            connection.execute(
                "UPDATE task_segments SET status='paused',deleted_at='2026-10-15T00:00:00Z'"
            )
    with pytest.raises(DeliveryLifecycleConflict, match="关联看板"):
        lifecycle.result(
            version["version_id"], revision=1, deleted=True, actor="user-1"
        )
    lifecycle.dashboard(
        dashboard["id"], revision=dashboard["revision"], deleted=True, actor="user-1"
    )
    assert dashboards.list()["total"] == 0
    assert dashboards.list(status="deleted")["total"] == 1
    lifecycle.result(version["version_id"], revision=1, deleted=True, actor="user-1")
    assert results.list()["total"] == 0
    assert results.list(lifecycle="deleted")["total"] == 1
    assert results.search_record_groups("Too")["total"] == 0
    assert dashboards.sources(dashboard["id"], dashboard["version"]["version_id"])
    with pytest.raises(DeliveryLifecycleConflict, match="先恢复"):
        lifecycle.dashboard(
            dashboard["id"],
            revision=dashboard["revision"] + 1,
            deleted=False,
            actor="user-1",
        )
    with pytest.raises(DeliveryLifecycleConflict, match="已更新"):
        lifecycle.result(
            version["version_id"], revision=1, deleted=False, actor="user-1"
        )
    lifecycle.result(version["version_id"], revision=2, deleted=False, actor="user-1")
    lifecycle.dashboard(
        dashboard["id"],
        revision=dashboard["revision"] + 1,
        deleted=False,
        actor="user-1",
    )
    assert results.list()["total"] == 1
    assert dashboards.list()["total"] == 1
    context.database.validate_production_schema()


def test_cancelled_queued_generation_is_not_claimed_or_reported_as_failure(tmp_path):
    context, dashboard, reports, _ = _service_context(tmp_path)
    queued = reports.create_for_dashboard(
        dashboard["id"],
        dashboard["version"]["version_id"],
        model_id="model-1",
        reasoning_effort="high",
        actor_id="user-1",
    )
    lifecycle = DeliveryLifecycleService(context.database)
    with pytest.raises(DeliveryLifecycleConflict, match="先取消"):
        lifecycle.dashboard(
            dashboard["id"],
            revision=dashboard["revision"],
            deleted=True,
            actor="user-1",
        )
    lifecycle.cancel_report(queued["id"], "user-1")
    assert reports.get(queued["id"])["status"] == "cancelled"
    assert reports.claim_next() is None
    assert WorkbenchService(context.database).summary()["counts"]["failed_reports"] == 0
    lifecycle.dashboard(
        dashboard["id"], revision=dashboard["revision"], deleted=True, actor="user-1"
    )
    with pytest.raises(ValueError, match="恢复"):
        reports.create_for_dashboard(
            dashboard["id"],
            dashboard["version"]["version_id"],
            model_id="model-1",
            reasoning_effort="high",
            actor_id="user-1",
        )


def test_cancelled_running_generation_cannot_publish_late_response(tmp_path):
    context, dashboard, reports, _ = _service_context(tmp_path)
    published = _complete_report(dashboard, reports)
    queued = reports.create_for_dashboard(
        dashboard["id"],
        dashboard["version"]["version_id"],
        model_id="model-1",
        reasoning_effort="high",
        actor_id="user-1",
    )
    assert reports.claim_next() == queued["id"]
    lifecycle = DeliveryLifecycleService(context.database)
    original = reports.client_factory

    def factory(settings):
        client = original(settings)
        generate = client.generate_json

        def cancel_and_return(*args, **kwargs):
            response = generate(*args, **kwargs)
            lifecycle.cancel_report(queued["id"], "user-1")
            return response

        client.generate_json = cancel_and_return
        return client

    reports.client_factory = factory
    reports.run(queued["id"])
    cancelled = reports.get(queued["id"])
    assert cancelled["status"] == "cancelled"
    assert cancelled["content"] is None
    assert reports.get(published["id"])["status"] == "completed"
    reports._publish_report(
        queued["id"],
        {"dashboard_id": dashboard["id"]},
        JsonModelCallResult(payload={}, model_name="model", usage={}, metrics={}),
        "{}",
    )
    assert reports.get(queued["id"])["version_no"] is None


def test_lifecycle_http_validates_login_revision_and_actions(tmp_path):
    context, version, _ = _ready_result(tmp_path)
    authenticated = False

    def user():
        if not authenticated:
            raise HTTPException(status_code=401, detail="请登录")
        return {"id": "user-1"}

    router = APIRouter()
    register_delivery_actions(router, lambda: context.database, user, kind="result")
    register_report_cancel(router, lambda: context.database, user)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    url = f"/api/classification-results/{version['version_id']}/lifecycle"
    payload = {"action": "delete", "expected_revision": 1}
    assert client.post(url, json=payload).status_code == 401
    authenticated = True
    assert client.post(url, json={**payload, "action": "purge"}).status_code == 422
    assert client.post(url, json=payload).status_code == 200
    assert client.post(url, json=payload).status_code == 409
    assert (
        client.post(url, json={"action": "restore", "expected_revision": 2}).status_code
        == 200
    )


def test_legacy_schema_upgrade_preserves_delivery_objects_and_is_repeatable(tmp_path):
    context, version, dashboards = _ready_result(tmp_path)
    _, dashboard = _create_dashboard(dashboards, version["version_id"])
    with context.database.transaction() as connection:
        connection.execute("ALTER TABLE classification_results DROP COLUMN deleted_at")
        connection.execute("ALTER TABLE classification_results DROP COLUMN revision")
        connection.execute("ALTER TABLE analysis_dashboards DROP COLUMN deleted_at")
        connection.execute("ALTER TABLE ai_insight_reports DROP COLUMN cancelled_at")
        connection.execute(
            "DELETE FROM app_migrations WHERE migration_id='20261013_delivery_lifecycle'"
        )
    context.database.upgrade_schema()
    context.database.upgrade_schema()
    context.database.validate_production_schema()
    assert (
        ClassificationResultService(context.database).get(version["version_id"])[
            "revision"
        ]
        == 1
    )
    assert dashboards.get(dashboard["id"])["deleted_at"] is None


def test_removed_result_requires_restore_before_resuming_source_task(tmp_path):
    context, version, _ = _ready_result(tmp_path)
    with context.database.transaction() as connection:
        connection.execute("UPDATE task_segments SET status='cancelled'")
        connection.execute("UPDATE tasks SET status='cancelled'")
    DeliveryLifecycleService(context.database).result(
        version["version_id"], revision=1, deleted=True, actor="user-1"
    )
    service = TaskService(context.database)
    task = service.get(context.task_id)
    with pytest.raises(ValueError, match="恢复分类结果"):
        service.segment_action(
            task["id"],
            task["segments"][0]["segment_key"],
            "resume",
            "user-1",
            task["revision"],
        )
    with pytest.raises(ValueError, match="恢复分类结果"):
        service.resume(task["id"], "user-1", task["revision"], "合成继续")


@pytest.mark.parametrize(
    "status,removed,removing,message",
    [
        ("running", False, False, "等待执行停止"),
        ("running", True, False, "等待执行停止"),
        ("paused", False, True, "等待执行停止"),
        ("completed", False, True, "等待执行停止"),
        ("paused", False, False, "移除来源 Listing"),
        ("queued", False, False, "移除来源 Listing"),
        ("retry_pending", False, False, "移除来源 Listing"),
        ("not_started", False, False, "移除来源 Listing"),
        ("paused", True, False, None),
        ("completed", False, False, None),
    ],
)
def test_result_deletion_respects_execution_and_removal_state(
    tmp_path, status, removed, removing, message
):
    context, version, _ = _ready_result(tmp_path)
    now = "2026-10-15T00:00:00Z"
    with context.database.transaction() as connection:
        connection.execute(
            "UPDATE task_segments SET status=?,deleted_at=?,removal_requested_at=?",
            (status, now if removed else None, now if removing else None),
        )
    router = APIRouter()
    register_delivery_actions(
        router, lambda: context.database, lambda: {"id": "user-1"}, kind="result"
    )
    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).post(
        f"/api/classification-results/{version['version_id']}/lifecycle",
        json={"action": "delete", "expected_revision": 1},
    )
    assert response.status_code == (409 if message else 200)
    if message:
        assert message in response.json()["detail"]
    result = ClassificationResultService(context.database).get(version["version_id"])
    assert bool(result["deleted_at"]) is (message is None)
    assert result["revision"] == (1 if message else 2)


def test_paused_listing_removal_enables_deletion_and_restore_reinstates_guard(tmp_path):
    context, version, _ = _ready_result(tmp_path)
    with context.database.transaction() as connection:
        connection.execute("UPDATE task_segments SET status='paused'")
    tasks = TaskService(context.database)
    task = tasks.get(context.task_id)
    key = task["segments"][0]["segment_key"]
    removed = tasks.segment_action(
        task["id"], key, "delete", "user-1", task["revision"]
    )
    lifecycle = DeliveryLifecycleService(context.database)
    lifecycle.result(version["version_id"], revision=1, deleted=True, actor="user-1")
    lifecycle.result(version["version_id"], revision=2, deleted=False, actor="user-1")
    task = tasks.get(removed["id"])
    tasks.segment_action(task["id"], key, "restore", "user-1", task["revision"])
    with pytest.raises(DeliveryLifecycleConflict, match="移除来源 Listing"):
        lifecycle.result(
            version["version_id"], revision=3, deleted=True, actor="user-1"
        )
