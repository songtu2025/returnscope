from pathlib import Path

from test_classification_result_pool import _publish, _seed_result_context

from web_backend.common import add_audit
from web_backend.dashboard_service import DashboardService
from web_backend.operations_service import AuditLogService


def test_global_audit_filters_targets_and_dashboard_audit(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)
    version = _publish(context)
    version_id = str(version["version_id"])
    dashboard_service = DashboardService(context.database)
    plan = dashboard_service.preflight([version_id], {})
    dashboard = dashboard_service.create(
        name="审计看板",
        description="",
        result_version_ids=[version_id],
        filters={},
        plan_hash=plan["plan_hash"],
        reason="验证审计",
        actor_id="user-1",
    )
    now = "2026-08-12T05:00:00+00:00"
    with context.database.transaction() as connection:
        result_id = str(
            connection.execute(
                "SELECT result_id FROM classification_result_versions WHERE id = ?",
                (version_id,),
            ).fetchone()["result_id"]
        )
        connection.execute(
            """
            INSERT INTO classification_result_versions(
                id, result_id, source_segment_id, version_no, content_hash,
                quality_status, publish_status, unit_count, record_count,
                parent_version_id, version_reason, created_by, created_at,
                published_at
            ) VALUES ('result-version-2', ?, 'segment-1', 2, 'hash-v2',
                      'ready', 'published', 1, 3, ?, '审计验证',
                      'user-1', ?, ?)
            """,
            (result_id, version_id, now, now),
        )
        connection.execute(
            """
            INSERT INTO review_batches(
                id, base_result_version_id, result_id, status, revision,
                created_by, created_at, updated_at
            ) VALUES ('batch-1', ?, ?, 'draft', 1, 'user-1', ?, ?)
            """,
            (version_id, result_id, now, now),
        )
        connection.execute(
            """
            INSERT INTO review_records(
                id, task_id, batch_id, base_result_version_id,
                classification_key, comment, workflow_status,
                classification_json, revision, updated_by, updated_at
            ) VALUES ('review-1', 'task-1', NULL, NULL, 'legacy-key',
                      'legacy comment', 'resolved', '{}', 1, 'user-1', ?)
            """,
            (now,),
        )
        connection.execute(
            """
            INSERT INTO api_models(
                id, connection_id, model_key, display_name,
                supported_efforts_json, active, validation_status,
                validation_message, created_by, created_at, updated_by,
                updated_at
            ) VALUES ('model-audit', 'connection-1', 'audit-model',
                      '审计模型', '["low"]', 1, 'draft', '',
                      'user-1', ?, 'user-1', ?)
            """,
            (now, now),
        )
    add_audit(
        context.database,
        "task",
        "task-1",
        "pause",
        "user-1",
        before={"status": "running"},
        after={"status": "paused"},
    )
    add_audit(
        context.database,
        "unknown_entity",
        "unknown-1",
        "inspect",
        "user-1",
    )
    add_audit(
        context.database,
        "review",
        "review-1",
        "resolve",
        "user-1",
    )
    add_audit(
        context.database,
        "review_batch",
        "batch-1",
        "create",
        "user-1",
    )
    for entity_type, entity_id in (
        ("task_segment", "segment-1"),
        ("classification_result_version", "result-version-2"),
        ("classification_result", result_id),
        ("dataset", "dataset-returns"),
        ("dataset", "dataset-products"),
        ("api_connection", "connection-1"),
        ("api_config_version", "config-1"),
        ("api_model", "model-audit"),
        ("user", "user-1"),
        ("task", "missing-task"),
    ):
        add_audit(
            context.database,
            entity_type,
            entity_id,
            "inspect",
            "user-1",
        )
    service = AuditLogService(context.database)

    dashboard_audit = service.list(
        entity_type="analysis_dashboard",
        entity_id=str(dashboard["id"]),
    )
    assert dashboard_audit["total"] == 1
    assert dashboard_audit["items"][0]["action"] == "create"
    assert dashboard_audit["items"][0]["target"] == {
        "route": "analysis-dashboards",
        "dashboard_id": dashboard["id"],
        "version_id": dashboard["current_version_id"],
    }
    task_audit = service.list(actor_id="user-1", entity_type="task", action="pause")
    assert task_audit["total"] == 1
    assert task_audit["items"][0]["before"] == {"status": "running"}
    assert task_audit["items"][0]["after"] == {"status": "paused"}
    assert task_audit["items"][0]["actor_name"] == "用户一"
    unknown = service.list(entity_type="unknown_entity")
    assert unknown["items"][0]["target"] is None
    review = service.list(entity_type="review")["items"][0]
    assert review["target"] == {
        "route": "review",
        "review_id": "review-1",
        "workflow_status": "resolved",
    }
    review_batch = service.list(entity_type="review_batch")["items"][0]
    assert review_batch["target"] == {
        "route": "review-center",
        "batch_id": "batch-1",
    }
    expected_targets = {
        ("task_segment", "segment-1"): {
            "route": "tasks",
            "task_id": "task-1",
            "segment_id": "segment-1",
        },
        ("classification_result_version", "result-version-2"): {
            "route": "classification-results",
            "result_version_id": "result-version-2",
        },
        ("classification_result", result_id): {
            "route": "classification-results",
            "result_version_id": "result-version-2",
        },
        ("dataset", "dataset-returns"): None,
        ("dataset", "dataset-products"): {
            "route": "data",
            "dataset_id": "dataset-products",
            "view": "products",
        },
        ("api_connection", "connection-1"): {
            "route": "api",
            "tab": "api",
            "connection_id": "connection-1",
        },
        ("api_config_version", "config-1"): {
            "route": "api",
            "tab": "api",
            "connection_id": "connection-1",
            "config_version_id": "config-1",
        },
        ("api_model", "model-audit"): {
            "route": "api",
            "tab": "models",
            "connection_id": "connection-1",
            "model_id": "model-audit",
        },
        ("user", "user-1"): {
            "route": "team",
            "tab": "users",
            "user_id": "user-1",
        },
    }
    all_items = service.list(page_size=200)["items"]
    items_by_entity = {
        (item["entity_type"], item["entity_id"]): item for item in all_items
    }
    for key, target in expected_targets.items():
        assert items_by_entity[key]["target"] == target
    assert items_by_entity[("task", "missing-task")]["target"] is None
