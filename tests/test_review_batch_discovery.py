from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from historical_review_fixtures import historical_batch
from test_result_version_reviews import _publish_review_required

from web_backend.review_service import ReviewService
from web_backend.routers.reviews import create_review_router


def _client(context, service: ReviewService) -> TestClient:
    app = FastAPI()

    def current_user() -> dict[str, str]:
        return {"id": "user-1"}

    app.include_router(create_review_router(service, context.database, current_user))
    return TestClient(app)


@pytest.mark.parametrize("status", ["draft", "published"])
def test_historical_batch_list_and_detail_remain_readable(
    tmp_path: Path, status: str
) -> None:
    context, base = _publish_review_required(tmp_path)
    batch = historical_batch(context, base)
    if status == "published":
        with context.database.transaction() as connection:
            connection.execute(
                "UPDATE review_batches SET status='published',published_version_id=? WHERE id=?",
                (base["version_id"], batch["id"]),
            )
    client = _client(context, ReviewService(context.database))
    response = client.get(
        "/api/review-batches",
        params={"base_result_version_id": base["version_id"], "status": status},
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == batch["id"]
    assert client.get(f"/api/review-batches/{batch['id']}").json()["record_count"] == 1


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
    batch = historical_batch(context, base)
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
    # 业务筛选决定入选记录，聚合仍包含该记录关联的全部来源。
    combined_item = combined.json()["items"][0]
    for field in (
        "record_count",
        "order_ids",
        "product_names",
        "listings",
        "source_skus",
        "matched_mskus",
        "product_skus",
    ):
        assert combined_item[field] == item[field]
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
