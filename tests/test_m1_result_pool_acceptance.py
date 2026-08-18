from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_classification_result_pool import _publish, _seed_result_context

from return_semantics.data import ReturnDataset, load_return_dataset_auto
from web_backend.classification_result_service import ClassificationResultService
from web_backend.routers.classification_results import (
    create_classification_result_router,
)


def test_exact_product_match_is_isolated_by_store_and_msku(tmp_path: Path) -> None:
    returns_path = tmp_path / "returns.csv"
    products_path = tmp_path / "products.xlsx"
    common = {
        "return-date": "2026-08-01",
        "asin": "SHARED-ASIN",
        "fnsku": "FNSKU",
        "product-name": "退货文件名称不得进入产品快照",
        "quantity": "1",
        "reason": "APPAREL_TOO_SMALL",
        "customer-comments": "Too small",
    }
    pd.DataFrame(
        [
            {
                **common,
                "order-id": "US-MATCHED",
                "sku": "SHARED-MSKU",
                "店铺/站点": "SEEKWAY:US",
            },
            {
                **common,
                "order-id": "CA-MATCHED",
                "sku": "SHARED-MSKU",
                "店铺/站点": "SEEKWAY:CA",
            },
            {
                **common,
                "order-id": "PRODUCT-SKU-NOT-A-KEY",
                "sku": "PRODUCT-SKU-US",
                "店铺/站点": "SEEKWAY:US",
            },
        ]
    ).to_csv(returns_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(
        [
            {
                "MSKU": "SHARED-MSKU",
                "店铺/站点": "SEEKWAY:US",
                "产品名称": "美国站产品名称",
                "SKU": "PRODUCT-SKU-US",
                "品类A": "水鞋",
                "品类B": "薄底水鞋",
                "Listing": "US-LISTING",
            },
            {
                "MSKU": "SHARED-MSKU",
                "店铺/站点": "SEEKWAY:CA",
                "产品名称": "加拿大站产品名称",
                "SKU": "PRODUCT-SKU-CA",
                "品类A": "眼镜",
                "品类B": "儿童眼镜",
                "Listing": "CA-LISTING",
            },
        ]
    ).to_excel(products_path, sheet_name="产品信息汇总表", index=False)

    dataset = load_return_dataset_auto(returns_path, products_path)
    records = dataset.records.set_index("order-id")

    us = records.loc["US-MATCHED"]
    assert us["matched_msku"] == "SHARED-MSKU"
    assert us["product_sku"] == "PRODUCT-SKU-US"
    assert us["product_name"] == "美国站产品名称"
    assert us["listing"] == "US-LISTING"
    assert us["category_a"] == "水鞋"
    assert us["category_b"] == "薄底水鞋"

    ca = records.loc["CA-MATCHED"]
    assert ca["matched_msku"] == "SHARED-MSKU"
    assert ca["product_sku"] == "PRODUCT-SKU-CA"
    assert ca["product_name"] == "加拿大站产品名称"
    assert ca["listing"] == "CA-LISTING"
    assert ca["category_a"] == "眼镜"
    assert ca["category_b"] == "儿童眼镜"

    aliased = records.loc["PRODUCT-SKU-NOT-A-KEY"]
    assert aliased["source_sku"] == "PRODUCT-SKU-US"
    assert aliased["product_match_status"] == "matched"
    assert aliased["matched_msku"] == "SHARED-MSKU"
    assert aliased["product_sku"] == "PRODUCT-SKU-US"
    assert aliased["product_name"] == "美国站产品名称"
    assert aliased["listing"] == "US-LISTING"
    assert aliased["category_a"] == "水鞋"
    assert aliased["category_b"] == "薄底水鞋"


def test_result_pool_api_keeps_pagination_summary_and_download_consistent(
    tmp_path: Path,
) -> None:
    context = _seed_result_context(tmp_path)
    template = context.dataset.records.iloc[0].copy()
    rows = []
    for offset in range(205):
        row = template.copy()
        row["source_row"] = offset + 2
        row["order-id"] = f"ORDER-{offset // 2:03d}"
        rows.append(row)
    records = pd.DataFrame(rows).reset_index(drop=True)
    comments = context.dataset.unique_comments.copy()
    comments.loc[:, "record_count"] = 205
    context.dataset = ReturnDataset(
        records=records,
        unique_comments=comments,
        mskus=context.dataset.mskus,
        scopes=context.dataset.scopes,
        primary_store=context.dataset.primary_store,
        scope_mode=context.dataset.scope_mode,
    )
    version = _publish(context)
    version_id = str(version["version_id"])
    service = ClassificationResultService(context.database)
    app = FastAPI()
    app.include_router(
        create_classification_result_router(
            service,
            lambda: {"id": "user-other-than-owner"},
        )
    )
    client = TestClient(app)

    detail = client.get(f"/api/classification-results/{version_id}")
    assert detail.status_code == 200
    assert detail.json()["unit_count"] == 1
    assert detail.json()["record_count"] == 205
    assert detail.json()["product_names"] == ["产品表权威名称"]

    listed = client.get(
        "/api/classification-results",
        params={
            "q": "PRODUCT-SKU-1",
            "store_site": "SEEKWAY:US",
            "listing": "L1",
            "quality_status": "ready",
        },
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["page_size"] == 50
    assert listed.json()["items"][0]["version_id"] == version_id
    assert listed.json()["items"][0]["product_names"] == ["产品表权威名称"]
    assert (
        client.get(
            "/api/classification-results",
            params={"q": "PRODUCT-SKU-1", "store_site": "OTHER"},
        ).json()["total"]
        == 0
    )
    assert (
        client.get(
            "/api/classification-results",
            params={"page_size": 201},
        ).status_code
        == 422
    )

    first_default = client.get(f"/api/classification-results/{version_id}/records")
    assert first_default.status_code == 200
    assert first_default.json()["page_size"] == 50
    assert first_default.json()["total"] == 205
    assert len(first_default.json()["items"]) == 50
    by_product_name = client.get(
        f"/api/classification-results/{version_id}/records",
        params={"product_name": "产品表权威名称"},
    )
    assert by_product_name.status_code == 200
    assert by_product_name.json()["total"] == 205
    assert (
        client.get(
            f"/api/classification-results/{version_id}/records",
            params={"product_name": "其他产品名称"},
        ).json()["total"]
        == 0
    )

    first = client.get(
        f"/api/classification-results/{version_id}/records",
        params={"page": 1, "page_size": 200},
    ).json()
    second = client.get(
        f"/api/classification-results/{version_id}/records",
        params={"page": 2, "page_size": 200},
    ).json()
    items = first["items"] + second["items"]
    assert first["total"] == second["total"] == 205
    assert len(first["items"]) == 200
    assert len(second["items"]) == 5
    assert [item["source_row"] for item in items] == list(range(2, 207))
    assert len({item["source_record_id"] for item in items}) == 205
    assert (
        client.get(
            f"/api/classification-results/{version_id}/records",
            params={"page_size": 201},
        ).status_code
        == 422
    )

    summary = client.get(f"/api/classification-results/{version_id}/summary").json()
    assert summary["quality"][0]["record_count"] == 205
    assert summary["top_problems"][0]["record_count"] == 205
    drilldown = client.get(
        f"/api/classification-results/{version_id}/drilldown",
        params={"group_by": "problem"},
    ).json()
    assert drilldown["page_size"] == 50
    assert drilldown["items"][0]["record_count"] == 205
    assert drilldown["items"][0]["unit_count"] == 1
    assert (
        client.get(
            f"/api/classification-results/{version_id}/drilldown",
            params={"group_by": "problem", "page_size": 201},
        ).status_code
        == 422
    )

    download = client.get(f"/api/classification-results/{version_id}/download")
    assert download.status_code == 200
    exported = pd.read_excel(BytesIO(download.content), dtype=str).fillna("")
    assert len(exported) == 205
    assert exported["source_record_id"].tolist() == [
        item["source_record_id"] for item in items
    ]
    assert set(
        [
            "order_id",
            "store_site",
            "listing",
            "product_name",
            "source_sku",
            "matched_msku",
            "product_sku",
            "classification_json",
        ]
    ).issubset(exported.columns)
