from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from test_classification_result_pool import _seed_result_context

import web_backend.data_quality_service as data_quality_module
from return_semantics.data import (
    PRODUCT_CATEGORY_COLUMNS,
    PRODUCT_COLUMNS,
    PRODUCT_DETAIL_COLUMNS,
    RETURN_COLUMNS,
    RETURN_STORE_COLUMN,
)
from web_backend.common import json_text
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


@pytest.mark.parametrize(
    ("category_a", "category_b", "missing"),
    [("SYNTHETIC-A", "", 0), ("", "SYNTHETIC-B", 0), ("", "", 1)],
)
def test_quality_category_requires_both_levels_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    category_a: str,
    category_b: str,
    missing: int,
) -> None:
    context = _seed_result_context(tmp_path)
    records = pd.DataFrame(
        [
            {
                "store": "SYNTHETIC-STORE",
                "source_sku": "SYNTHETIC-SKU",
                "listing": "SYNTHETIC-LISTING",
                "product_name": "SYNTHETIC-PRODUCT",
                "category_a": category_a,
                "category_b": category_b,
                "product_match_status": "matched",
            }
        ]
    )
    original = records.copy(deep=True)
    monkeypatch.setattr(
        data_quality_module,
        "load_cached_dataset",
        lambda *_args: SimpleNamespace(records=records),
    )
    service = DataQualityService(context.database)
    preflight = service.preflight("version-returns", "version-products")
    issues = service.issues(
        "version-returns", "version-products", issue_type="missing_category"
    )
    assert preflight["counts"]["missing_category_records"] == missing
    assert issues["total"] == missing
    assert [item["record_count"] for item in issues["items"]] == (
        [1] if missing else []
    )
    pd.testing.assert_frame_equal(records, original)


def test_data_quality_cache_is_bounded_invalidates_and_isolation_safe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _seed_result_context(tmp_path)
    returns_id, products_id, products_v3 = _insert_quality_versions(
        context,
        tmp_path,
    )
    real_loader = data_quality_module.load_cached_dataset
    calls = 0

    def counting_loader(*args, **kwargs):
        nonlocal calls
        calls += 1
        return real_loader(*args, **kwargs)

    monkeypatch.setattr(data_quality_module, "load_cached_dataset", counting_loader)
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
            lambda: {"id": "user-1", "is_admin": True},
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
    managed_returns = client.get(
        "/api/datasets?kind=returns&usage_scope=managed"
    ).json()
    assert managed_returns[0]["task_reference_count"] == references.json()["total"]
    assert client.get("/api/audit-logs?page=1&page_size=1").status_code == 200
    invalid_date = client.get("/api/audit-logs?date_to=2026-02-30")
    assert invalid_date.status_code == 400

    member_app = FastAPI()
    member_app.include_router(
        create_operations_router(
            workbench,
            quality,
            audit,
            lambda: {"id": "user-2", "is_admin": False},
        )
    )
    member_client = TestClient(member_app)
    assert member_client.get("/api/workbench/summary").status_code == 200
    assert member_client.get("/api/audit-logs").status_code == 403

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
