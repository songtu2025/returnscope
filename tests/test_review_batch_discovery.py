from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_result_version_reviews import _publish_review_required

from web_backend.review_service import ReviewService
from web_backend.routers.reviews import create_review_router


def _client(context, service: ReviewService) -> TestClient:
    app = FastAPI()

    def current_user() -> dict[str, str]:
        return {"id": "user-1"}

    app.include_router(create_review_router(service, context.database, current_user))
    return TestClient(app)


def test_review_batch_list_discovery_conflict_and_derived_summary(
    tmp_path: Path,
) -> None:
    context, base = _publish_review_required(tmp_path)
    base_id = str(base["version_id"])
    service = ReviewService(context.database)
    client = _client(context, service)

    created = client.post(
        f"/api/classification-results/{base_id}/review-batches",
        json={"reason": "创建复核草稿"},
    )
    assert created.status_code == 201
    batch = created.json()
    with context.database.connect() as connection:
        records_before = connection.execute(
            "SELECT COUNT(*) FROM review_records WHERE batch_id = ?",
            (batch["id"],),
        ).fetchone()[0]

    duplicate = client.post(
        f"/api/classification-results/{base_id}/review-batches",
        json={"reason": "重复创建"},
    )
    assert duplicate.status_code == 409
    with context.database.connect() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM review_batches WHERE base_result_version_id = ?",
                (base_id,),
            ).fetchone()[0]
            == 1
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM review_records WHERE batch_id = ?",
                (batch["id"],),
            ).fetchone()[0]
            == records_before
        )
        result_id = connection.execute(
            "SELECT result_id FROM classification_result_versions WHERE id = ?",
            (base_id,),
        ).fetchone()[0]
        connection.execute(
            """
            INSERT INTO review_batches(
                id, base_result_version_id, result_id, status, revision,
                created_by, created_at, updated_at,
                published_version_id, published_at
            ) VALUES ('batch-published', ?, ?, 'published', 2, 'user-2',
                      '2026-08-12T00:05:00+00:00',
                      '2026-08-12T00:05:00+00:00', ?,
                      '2026-08-12T00:05:00+00:00')
            """,
            (base_id, result_id, base_id),
        )

    discovered = client.get(
        "/api/review-batches",
        params={
            "base_result_version_id": base_id,
            "status": "draft",
        },
    )
    assert discovered.status_code == 200
    assert discovered.json()["total"] == 1
    item = discovered.json()["items"][0]
    assert item["id"] == batch["id"]
    assert item["base_version_no"] == 1
    assert item["store_site"] == "SEEKWAY:US"
    assert item["listing"] == "L1"
    assert item["base_quality_status"] == "review_required"
    assert item["base_unit_count"] == 1
    assert item["base_record_count"] == 3
    assert item["record_count"] == 1
    assert item["resolved_count"] == 0
    assert item["remaining_count"] == 1
    assert item["creator"]["id"] == "user-1"

    paged = client.get(
        "/api/review-batches",
        params={"page": 2, "page_size": 1, "base_result_version_id": base_id},
    )
    assert paged.status_code == 200
    assert paged.json()["total"] == 2
    assert len(paged.json()["items"]) == 1
    assert (
        client.get("/api/review-batches", params={"q": "batch-published"}).json()[
            "total"
        ]
        == 1
    )
    assert (
        client.get("/api/review-batches", params={"q": "user-2"}).json()["total"] == 1
    )
    assert client.get("/api/review-batches", params={"q": "L1"}).json()["total"] == 2

    review = service.batch_records(batch["id"])["items"][0]
    service.update_batch_record(
        batch["id"],
        review["id"],
        review["revision"],
        "user-1",
        "FIT_TOO_SMALL",
        "确认尺码偏小",
    )
    current = service.get_batch(batch["id"])
    derived = service.publish_batch(
        batch["id"],
        current["revision"],
        "user-1",
        "发布复核结果",
    )
    detail = client.get(f"/api/review-batches/{batch['id']}")
    assert detail.status_code == 200
    assert detail.json()["derived_result_version_id"] == derived["version_id"]
    assert detail.json()["derived_version_no"] == 2
    assert detail.json()["resolved_count"] == 1
    assert detail.json()["remaining_count"] == 0


def test_review_batch_records_aggregate_business_fields_and_filter_without_n_plus_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, base = _publish_review_required(tmp_path)
    base_id = str(base["version_id"])
    with context.database.transaction() as connection:
        connection.execute(
            """
            UPDATE classification_result_records
            SET listing = CASE source_row WHEN 3 THEN 'L2' ELSE 'L1' END,
                product_name = CASE source_row
                    WHEN 3 THEN 'Product Beta' ELSE 'Product Alpha' END,
                source_sku = CASE source_row
                    WHEN 3 THEN 'RETURN-MSKU-B' ELSE 'RETURN-MSKU-A' END,
                matched_msku = CASE source_row
                    WHEN 3 THEN 'MATCHED-MSKU-B' ELSE 'MATCHED-MSKU-A' END,
                product_sku = CASE source_row
                    WHEN 3 THEN 'PRODUCT-SKU-B' ELSE 'PRODUCT-SKU-A' END
            WHERE result_version_id = ?
            """,
            (base_id,),
        )
    service = ReviewService(context.database)
    batch = service.create_batch(base_id, "user-1", "聚合业务字段")
    client = _client(context, service)

    response = client.get(f"/api/review-batches/{batch['id']}/records")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    item = payload["items"][0]
    assert item["record_count"] == 3
    assert item["order_ids"] == ["ORDER-DUP", "ORDER-OTHER"]
    assert item["product_names"] == ["Product Alpha", "Product Beta"]
    assert item["listings"] == ["L1", "L2"]
    assert item["source_skus"] == ["RETURN-MSKU-A", "RETURN-MSKU-B"]
    assert item["matched_mskus"] == ["MATCHED-MSKU-A", "MATCHED-MSKU-B"]
    assert item["product_skus"] == ["PRODUCT-SKU-A", "PRODUCT-SKU-B"]
    assert item["workflow_status"] == "pending"
    assert item["revision"] == 1
    assert item["comment"]
    assert item["classification"]

    combined = client.get(
        f"/api/review-batches/{batch['id']}/records",
        params={
            "listing": "L2",
            "product_name": "Product Beta",
            "product_sku": "PRODUCT-SKU-B",
            "order_id": "ORDER-DUP",
            "page": 1,
            "page_size": 1,
        },
    )
    assert combined.status_code == 200
    assert combined.json()["total"] == 1
    assert (
        client.get(
            f"/api/review-batches/{batch['id']}/records",
            params={"q": "RETURN-MSKU-B"},
        ).json()["total"]
        == 1
    )
    assert (
        client.get(
            f"/api/review-batches/{batch['id']}/records",
            params={"q": "not-present"},
        ).json()["total"]
        == 0
    )

    statements: list[str] = []
    original_connect = context.database.connect

    def traced_connect():
        connection = original_connect()
        connection.set_trace_callback(statements.append)
        return connection

    monkeypatch.setattr(context.database, "connect", traced_connect)
    traced = service.batch_records(batch["id"], q="Product Alpha")
    assert traced["total"] == 1
    record_queries = [
        statement
        for statement in statements
        if statement.lstrip().upper().startswith("SELECT")
        and "classification_result_records" in statement
    ]
    assert len(record_queries) == 2

    monkeypatch.setattr(context.database, "connect", original_connect)
    with context.database.transaction() as connection:
        connection.execute(
            """
            UPDATE classification_result_records SET product_name = NULL
            WHERE result_version_id = ?
            """,
            (base_id,),
        )
    empty_names = service.batch_records(batch["id"])["items"][0]
    assert empty_names["product_names"] == []
