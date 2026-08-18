from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from test_classification_result_pool import _publish, _seed_result_context

import web_backend.data_quality_service as data_quality_module
from return_semantics.data import (
    PRODUCT_CATEGORY_COLUMNS,
    PRODUCT_COLUMNS,
    PRODUCT_DETAIL_COLUMNS,
    RETURN_COLUMNS,
    RETURN_STORE_COLUMN,
)
from web_backend.common import add_audit, json_text
from web_backend.dashboard_service import DashboardService
from web_backend.data_quality_service import DataQualityService
from web_backend.dataset_service import (
    ALLOWED_EXTENSIONS,
    PRODUCT_WORKSHEET,
    DatasetService,
)
from web_backend.import_rule_service import list_import_rules
from web_backend.operations_service import AuditLogService, WorkbenchService
from web_backend.routers.datasets import create_dataset_router
from web_backend.routers.operations import create_operations_router


def _insert_paused_task(database) -> None:
    with database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO tasks(
                id, title, owner_id, dataset_version_id, product_version_id,
                config_version_id, store, listing, status, stage,
                snapshot_json, created_at, heartbeat_at
            ) VALUES ('task-paused', '暂停任务', 'user-1', 'version-returns',
                      'version-products', 'config-1', 'SEEKWAY:US', 'L2',
                      'paused', '语义分析', '{}', ?, ?)
            """,
            ("2026-08-12T03:00:00+00:00", "2026-08-12T03:00:00+00:00"),
        )
        connection.execute(
            """
            INSERT INTO task_segments(
                id, task_id, segment_key, agent_key, agent_family,
                taxonomy_version, scope_json, status, created_at, heartbeat_at
            ) VALUES ('segment-paused', 'task-paused', 'L2', 'footwear',
                      '鞋履智能体', 'taxonomy-v1', ?, 'paused', ?, ?)
            """,
            (
                json_text({"store": "SEEKWAY:US", "listing": "L2"}),
                "2026-08-12T03:00:00+00:00",
                "2026-08-12T03:00:00+00:00",
            ),
        )


def test_workbench_actions_are_fact_based_and_priority_sorted(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)
    version = _publish(context)
    _insert_paused_task(context.database)
    with context.database.transaction() as connection:
        connection.execute(
            """
            UPDATE tasks SET status = 'blocked', message = '缺少品类',
                             heartbeat_at = '2026-08-12T01:00:00+00:00'
            WHERE id = 'task-1'
            """
        )
        connection.execute(
            """
            UPDATE task_segments SET status = 'failed', error = '调用失败',
                   heartbeat_at = '2026-08-12T02:00:00+00:00'
            WHERE id = 'segment-1'
            """
        )
        connection.execute(
            """
            UPDATE classification_result_versions
            SET quality_status = 'review_required',
                published_at = '2026-08-12T04:00:00+00:00'
            WHERE id = ?
            """,
            (version["version_id"],),
        )

    summary = WorkbenchService(context.database).summary(limit=10)
    assert [item["type"] for item in summary["actions"]] == [
        "blocked",
        "failed",
        "review_required",
        "paused",
        "paused",
    ]
    blocked = summary["actions"][0]
    assert blocked["object_id"] == "task-1"
    assert blocked["target"] == {"route": "tasks", "task_id": "task-1"}
    review = summary["actions"][2]
    assert review["result_version_id"] == version["version_id"]
    assert review["target"]["action"] == "review"
    assert summary["counts"]["blocked_tasks"] == 1
    assert summary["counts"]["failed_segments"] == 1
    assert summary["counts"]["review_required_results"] == 1
    assert summary["counts"]["paused_segments"] == 1


def test_workbench_distinguishes_derived_results_and_dashboards(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)
    first = _publish(context)
    first_id = str(first["version_id"])
    with context.database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO classification_result_versions(
                id, result_id, source_segment_id, version_no, content_hash,
                quality_status, publish_status, unit_count, record_count,
                parent_version_id, version_reason, created_by, created_at,
                published_at
            ) SELECT 'derived-v2', result_id, source_segment_id, 2, 'hash-v2',
                     'ready', 'published', unit_count, record_count, id,
                     '人工复核发布', 'user-1', '2026-08-12T02:00:00+00:00',
                     '2026-08-12T02:00:00+00:00'
              FROM classification_result_versions WHERE id = ?
            """,
            (first_id,),
        )
        connection.execute(
            """
            INSERT INTO classification_result_versions(
                id, result_id, source_segment_id, version_no, content_hash,
                quality_status, publish_status, unit_count, record_count,
                parent_version_id, version_reason, created_by, created_at,
                published_at
            ) SELECT 'review-v3', result_id, source_segment_id, 3, 'hash-v3',
                     'review_required', 'published', unit_count, record_count,
                     id, '待复核', 'user-1', '2026-08-12T03:00:00+00:00',
                     '2026-08-12T03:00:00+00:00'
              FROM classification_result_versions WHERE id = 'derived-v2'
            """
        )
    dashboard_service = DashboardService(context.database)
    plan = dashboard_service.preflight([first_id], {})
    dashboard = dashboard_service.create(
        name="确定性看板",
        description="",
        result_version_ids=[first_id],
        filters={},
        plan_hash=plan["plan_hash"],
        reason="创建看板",
        actor_id="user-1",
    )

    summary = WorkbenchService(context.database).summary(limit=10)
    types = [item["type"] for item in summary["recent_outputs"]]
    assert "classification_result" in types
    assert "derived_result" in types
    assert "dashboard" in types
    assert all(item["version_id"] != "review-v3" for item in summary["recent_outputs"])
    derived = next(
        item for item in summary["recent_outputs"] if item["type"] == "derived_result"
    )
    assert derived["version_id"] == "derived-v2"
    dashboard_output = next(
        item for item in summary["recent_outputs"] if item["type"] == "dashboard"
    )
    assert dashboard_output["object_id"] == dashboard["id"]
    assert dashboard_output["version_id"] == dashboard["current_version_id"]


def test_data_version_references_cover_both_snapshot_roles_and_history(
    tmp_path: Path,
) -> None:
    context = _seed_result_context(tmp_path)
    snapshot = {
        "returns": {
            "version_id": "version-returns",
            "version": 1,
            "name": "退货数据",
            "sha256": "returns-sha",
        },
        "products": {
            "version_id": "version-products",
            "version": 1,
            "name": "产品信息",
            "sha256": "products-sha",
        },
    }
    with context.database.transaction() as connection:
        connection.execute(
            "UPDATE tasks SET snapshot_json = ? WHERE id = 'task-1'",
            (json_text(snapshot),),
        )
        connection.execute(
            """
            INSERT INTO tasks(
                id, title, owner_id, dataset_version_id, product_version_id,
                config_version_id, store, status, stage, snapshot_json, created_at
            ) VALUES ('task-2', '第二个任务', 'user-1', 'version-returns',
                      'version-products', 'config-1', 'SEEKWAY:US', 'completed',
                      '完成', ?, '2026-08-12T01:00:00+00:00')
            """,
            (json_text(snapshot),),
        )
        connection.execute(
            "UPDATE datasets SET archived_at = ? WHERE id = 'dataset-returns'",
            ("2026-08-12T02:00:00+00:00",),
        )
    service = DatasetService(
        context.database,
        SimpleNamespace(data_dir=tmp_path),
    )
    first_page = service.references("version-returns", page=1, page_size=1)
    second_page = service.references("version-returns", page=2, page_size=1)
    products = service.references("version-products")

    assert first_page["total"] == 2
    assert second_page["total"] == 2
    assert first_page["items"][0]["reference_type"] == "returns"
    assert first_page["items"][0]["version_snapshot"]["version_id"] == (
        "version-returns"
    )
    assert products["total"] == 2
    assert {item["reference_type"] for item in products["items"]} == {"products"}


def _insert_quality_versions(context, tmp_path: Path) -> tuple[str, str, str]:
    returns_path = tmp_path / "quality-returns.csv"
    products_path = tmp_path / "quality-products.xlsx"
    base = {
        "return-date": "2026-08-01",
        "asin": "ASIN",
        "fnsku": "FNSKU",
        "product-name": "退货文件名称不能作为产品名称",
        "quantity": "1",
        "reason": "OTHER",
        "customer-comments": "Return comment",
    }
    pd.DataFrame(
        [
            {**base, "order-id": "O-1", "sku": "GOOD", "店铺/站点": "US"},
            {**base, "order-id": "O-2", "sku": "MISS", "店铺/站点": "US"},
            {**base, "order-id": "O-3", "sku": "GOOD", "店铺/站点": ""},
            {**base, "order-id": "O-4", "sku": "", "店铺/站点": "US"},
            {**base, "order-id": "O-5", "sku": "INCOMPLETE", "店铺/站点": "US"},
        ]
    ).to_csv(returns_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(
        [
            {
                "MSKU": "GOOD",
                "店铺/站点": "US",
                "Listing": "L1",
                "产品名称": "权威产品名",
                "SKU": "PRODUCT-1",
                "品类A": "水鞋",
                "品类B": "薄底水鞋",
            },
            {
                "MSKU": "INCOMPLETE",
                "店铺/站点": "US",
                "Listing": "L2",
                "产品名称": "",
                "SKU": "PRODUCT-2",
                "品类A": "",
                "品类B": "",
            },
        ]
    ).to_excel(products_path, sheet_name="产品信息汇总表", index=False)
    returns_sha = hashlib.sha256(returns_path.read_bytes()).hexdigest()
    products_sha = hashlib.sha256(products_path.read_bytes()).hexdigest()
    now = "2026-08-12T04:00:00+00:00"
    with context.database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO dataset_versions(
                id, dataset_id, version, file_path, original_name, content_type,
                size_bytes, sha256, row_count, column_count, schema_json,
                quality_json, created_by, created_at
            ) VALUES ('quality-returns', 'dataset-returns', 2, ?, 'quality.csv',
                      'text/csv', ?, ?, 5, 10, '[]', '{}', 'user-1', ?)
            """,
            (str(returns_path), returns_path.stat().st_size, returns_sha, now),
        )
        connection.execute(
            """
            INSERT INTO dataset_versions(
                id, dataset_id, version, file_path, original_name, content_type,
                size_bytes, sha256, row_count, column_count, schema_json,
                quality_json, created_by, created_at
            ) VALUES ('quality-products', 'dataset-products', 2, ?, 'quality.xlsx',
                      'application/xlsx', ?, ?, 2, 7, '[]', '{}', 'user-1', ?)
            """,
            (str(products_path), products_path.stat().st_size, products_sha, now),
        )
        connection.execute(
            """
            INSERT INTO dataset_versions(
                id, dataset_id, version, file_path, original_name, content_type,
                size_bytes, sha256, row_count, column_count, schema_json,
                quality_json, created_by, created_at
            ) VALUES ('quality-products-v3', 'dataset-products', 3, ?,
                      'quality.xlsx', 'application/xlsx', ?, ?, 2, 7, '[]', '{}',
                      'user-1', ?)
            """,
            (str(products_path), products_path.stat().st_size, products_sha, now),
        )
    return "quality-returns", "quality-products", "quality-products-v3"


def test_data_quality_preflight_hash_issues_and_zero_model_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _seed_result_context(tmp_path)
    returns_id, products_id, products_v3 = _insert_quality_versions(
        context,
        tmp_path,
    )

    def forbid_model(*_args, **_kwargs):
        raise AssertionError("数据质量预检不得调用模型")

    monkeypatch.setattr("return_semantics.model_client.Sub2APIClient", forbid_model)
    service = DataQualityService(context.database)
    baseline = service.preflight("version-returns", "version-products")
    first = service.preflight(returns_id, products_id)
    second = service.preflight(returns_id, products_id)
    changed = service.preflight(returns_id, products_v3)

    assert baseline["counts"]["total_records"] == 3
    assert baseline["counts"]["matched_records"] == 3
    assert baseline["counts"]["unmatched_records"] == 0
    assert first["quality_hash"] == second["quality_hash"]
    assert first["quality_hash"] != changed["quality_hash"]
    assert first["counts"] == {
        "total_records": 5,
        "match_key_ready_records": 3,
        "match_key_ready_keys": 3,
        "matched_records": 2,
        "unmatched_records": 3,
        "missing_store_records": 1,
        "missing_source_sku_records": 1,
        "missing_category_records": 1,
        "missing_product_name_records": 1,
    }
    issues = service.issues(
        returns_id,
        products_id,
        issue_type="unmatched_product",
        page=1,
        page_size=1,
    )
    assert issues["total"] == 3
    assert len(issues["items"]) == 1
    assert issues["items"][0]["record_count"] == 1
    searched = service.issues(returns_id, products_id, q="MISS")
    assert searched["total"] == 1
    assert searched["items"][0]["source_sku"] == "MISS"
    missing_name = service.issues(
        returns_id,
        products_id,
        issue_type="missing_product_name",
    )
    assert missing_name["items"][0]["product_name"] == ""


def test_data_quality_cache_is_bounded_invalidates_and_isolation_safe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _seed_result_context(tmp_path)
    returns_id, products_id, products_v3 = _insert_quality_versions(
        context,
        tmp_path,
    )
    real_loader = data_quality_module.load_return_dataset_auto
    calls = 0

    def counting_loader(*args, **kwargs):
        nonlocal calls
        calls += 1
        return real_loader(*args, **kwargs)

    monkeypatch.setattr(data_quality_module, "load_return_dataset_auto", counting_loader)
    service = DataQualityService(context.database)
    first = service.preflight(returns_id, products_id)
    first_issues = service.issues(returns_id, products_id, q="MISS")
    assert calls == 1

    first["counts"]["matched_records"] = 999
    first_issues["items"][0]["source_sku"] = "被外部修改"
    repeated = service.preflight(returns_id, products_id)
    repeated_issues = service.issues(returns_id, products_id, q="MISS")
    assert repeated["counts"]["matched_records"] == 2
    assert repeated_issues["items"][0]["source_sku"] == "MISS"
    assert calls == 1

    service.preflight(returns_id, products_v3)
    assert calls == 2
    with context.database.transaction() as connection:
        connection.execute(
            "UPDATE dataset_versions SET sha256 = 'corrected-sha' WHERE id = ?",
            (products_id,),
        )
    service.preflight(returns_id, products_id)
    assert calls == 3
    assert len(service._cache) == 2

    with context.database.transaction() as connection:
        connection.execute(
            "UPDATE dataset_versions SET sha256 = ? WHERE id = ?",
            (first["products_version"]["sha256"], products_id),
        )
    service.preflight(returns_id, products_id)
    assert calls == 4
    assert len(service._cache) == 2


def test_import_rules_follow_runtime_constants_and_hash_is_stable() -> None:
    first = list_import_rules()
    second = list_import_rules()
    assert first == second
    assert [item["id"] for item in first["items"]] == [
        "returns-standard-v1",
        "products-standard-v1",
    ]
    returns, products = first["items"]
    assert returns["required_columns"] == RETURN_COLUMNS
    assert returns["optional_columns"] == [RETURN_STORE_COLUMN]
    assert returns["file_extensions"] == sorted(ALLOWED_EXTENSIONS["returns"])
    assert returns["worksheet"] is None
    assert returns["match_key"] == [RETURN_STORE_COLUMN, "sku"]
    assert products["required_columns"] == PRODUCT_COLUMNS
    assert products["optional_columns"] == (
        PRODUCT_CATEGORY_COLUMNS + PRODUCT_DETAIL_COLUMNS
    )
    assert products["file_extensions"] == sorted(ALLOWED_EXTENSIONS["products"])
    assert products["worksheet"] == PRODUCT_WORKSHEET
    assert products["match_key"] == [RETURN_STORE_COLUMN, "MSKU"]
    assert all(len(item["content_hash"]) == 64 for item in first["items"])


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
        ("dataset", "dataset-returns"): {
            "route": "data",
            "dataset_id": "dataset-returns",
            "view": "returns",
        },
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


def test_audit_date_only_includes_whole_day_and_iso_is_exact(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)
    with context.database.transaction() as connection:
        for audit_id, created_at in (
            ("audit-day-start", "2026-08-12T00:00:00+00:00"),
            ("audit-day-late", "2026-08-12T18:30:00+00:00"),
            ("audit-next-day", "2026-08-13T00:00:00+00:00"),
        ):
            connection.execute(
                """
                INSERT INTO audit_logs(
                    id, entity_type, entity_id, action, actor_id, created_at
                ) VALUES (?, 'date_case', ?, 'inspect', 'user-1', ?)
                """,
                (audit_id, audit_id, created_at),
            )
    service = AuditLogService(context.database)

    whole_day = service.list(
        entity_type="date_case",
        date_from="2026-08-12",
        date_to="2026-08-12",
    )
    assert whole_day["total"] == 2
    assert {item["id"] for item in whole_day["items"]} == {
        "audit-day-start",
        "audit-day-late",
    }
    exact = service.list(
        entity_type="date_case",
        date_from="2026-08-12T18:30:00+00:00",
        date_to="2026-08-12T18:30:00+00:00",
    )
    assert [item["id"] for item in exact["items"]] == ["audit-day-late"]
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        service.list(date_to="2026-02-30")


def test_new_read_apis_require_login_and_keep_pagination_contract(
    tmp_path: Path,
) -> None:
    context = _seed_result_context(tmp_path)
    workbench = WorkbenchService(context.database)
    quality = DataQualityService(context.database)
    audit = AuditLogService(context.database)
    datasets = DatasetService(
        context.database,
        SimpleNamespace(data_dir=tmp_path),
    )
    app = FastAPI()
    app.include_router(
        create_operations_router(
            workbench,
            quality,
            audit,
            lambda: {"id": "user-1"},
        )
    )
    app.include_router(
        create_dataset_router(
            datasets,
            SimpleNamespace(data_dir=tmp_path),
            lambda: {"id": "user-1"},
        )
    )
    client = TestClient(app)
    assert client.get("/api/workbench/summary").status_code == 200
    import_rules = client.get("/api/import-rules")
    assert import_rules.status_code == 200
    assert len(import_rules.json()["items"]) == 2
    references = client.get(
        "/api/data-versions/version-returns/references?page=1&page_size=1"
    )
    assert references.status_code == 200
    assert references.json()["page_size"] == 1
    assert client.get("/api/audit-logs?page=1&page_size=1").status_code == 200
    invalid_date = client.get("/api/audit-logs?date_to=2026-02-30")
    assert invalid_date.status_code == 400

    def reject_user():
        raise HTTPException(status_code=401, detail="请先登录")

    denied = FastAPI()
    denied.include_router(
        create_operations_router(workbench, quality, audit, reject_user)
    )
    denied.include_router(
        create_dataset_router(
            datasets,
            SimpleNamespace(data_dir=tmp_path),
            reject_user,
        )
    )
    denied_client = TestClient(denied)
    assert denied_client.get("/api/workbench/summary").status_code == 401
    assert denied_client.get("/api/import-rules").status_code == 401
    assert (
        denied_client.get("/api/data-versions/version-returns/references").status_code
        == 401
    )
