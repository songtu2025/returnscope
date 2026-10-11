from pathlib import Path

import pandas as pd

from return_semantics.capabilities import load_capability_registry
from return_semantics.data import (
    load_return_dataset_auto,
)
from return_semantics.task_plan import build_category_execution_plan

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_auto_scope_matches_product_by_store_and_sku(tmp_path: Path) -> None:
    returns_path = tmp_path / "returns.csv"
    products_path = tmp_path / "products.xlsx"
    rows = []
    for order_id, store in (("1", "STORE-US"), ("2", "STORE-CA")):
        rows.append(
            {
                "return-date": "2026-01-01",
                "order-id": order_id,
                "sku": "SHARED-SKU",
                "asin": "",
                "fnsku": "",
                "product-name": "glasses",
                "quantity": "1",
                "reason": "NOT_AS_DESCRIBED",
                "customer-comments": "Too small",
                "店铺/站点": store,
            }
        )
    pd.DataFrame(rows).to_csv(returns_path, index=False, encoding="utf-8-sig")
    products = pd.DataFrame(
        [
            {
                "MSKU": "SHARED-SKU",
                "店铺/站点": "STORE-US",
                "Listing": "GLASSES-US",
                "产品名称": "儿童眼镜",
                "品类A": "眼镜",
                "品类B": "儿童眼镜",
            },
            {
                "MSKU": "SHARED-SKU",
                "店铺/站点": "STORE-CA",
                "Listing": "HAT-CA",
                "产品名称": "儿童渔夫帽",
                "品类A": "遮阳帽",
                "品类B": "儿童渔夫帽",
            },
        ]
    )
    with pd.ExcelWriter(products_path, engine="openpyxl") as writer:
        products.to_excel(writer, sheet_name="产品信息汇总表", index=False)

    dataset = load_return_dataset_auto(returns_path, products_path)

    matched = dataset.records.set_index("store")
    assert matched.loc["STORE-US", "listing"] == "GLASSES-US"
    assert matched.loc["STORE-US", "category_a"] == "眼镜"
    assert matched.loc["STORE-CA", "listing"] == "HAT-CA"
    assert matched.loc["STORE-CA", "category_a"] == "遮阳帽"
    assert dataset.unique_comments["classification_key"].nunique() == 2
    registry = load_capability_registry(
        PROJECT_ROOT / "config" / "category_capabilities.json"
    )
    plan = build_category_execution_plan(dataset, registry)
    ready_segments = {
        segment["segment_key"]: segment
        for segment in plan.summary["segments"]
        if segment["status"] == "ready"
    }
    assert set(ready_segments) == {
        "STORE-US/GLASSES-US/eyewear",
        "STORE-CA/HAT-CA/headwear",
    }
    assert ready_segments["STORE-US/GLASSES-US/eyewear"]["scope"] == {
        "store": "STORE-US",
        "listing": "GLASSES-US",
    }


def test_auto_scope_does_not_guess_store_for_legacy_returns(tmp_path: Path) -> None:
    returns_path = tmp_path / "returns.csv"
    products_path = tmp_path / "products.xlsx"
    pd.DataFrame(
        [
            {
                "return-date": "2026-01-01",
                "order-id": str(index),
                "sku": sku,
                "asin": "",
                "fnsku": "",
                "product-name": "water shoes",
                "quantity": "1",
                "reason": "NOT_AS_DESCRIBED",
                "customer-comments": "Too small",
            }
            for index, sku in enumerate(
                ("SHARED-SKU", "US-ONLY", "US-ONLY-2", "CA-ONLY"),
                start=1,
            )
        ]
    ).to_csv(returns_path, index=False, encoding="utf-8-sig")
    products = pd.DataFrame(
        [
            {
                "MSKU": "SHARED-SKU",
                "店铺/站点": "STORE-US",
                "Listing": "US-LISTING",
                "产品名称": "涉水鞋",
                "品类A": "水鞋",
                "品类B": "薄底水鞋",
            },
            {
                "MSKU": "US-ONLY",
                "店铺/站点": "STORE-US",
                "Listing": "US-LISTING",
                "产品名称": "涉水鞋",
                "品类A": "水鞋",
                "品类B": "薄底水鞋",
            },
            {
                "MSKU": "US-ONLY-2",
                "店铺/站点": "STORE-US",
                "Listing": "US-LISTING",
                "产品名称": "涉水鞋",
                "品类A": "水鞋",
                "品类B": "薄底水鞋",
            },
            {
                "MSKU": "SHARED-SKU",
                "店铺/站点": "STORE-CA",
                "Listing": "CA-LISTING",
                "产品名称": "涉水鞋",
                "品类A": "水鞋",
                "品类B": "厚底水鞋",
            },
            {
                "MSKU": "CA-ONLY",
                "店铺/站点": "STORE-CA",
                "Listing": "CA-LISTING",
                "产品名称": "涉水鞋",
                "品类A": "水鞋",
                "品类B": "厚底水鞋",
            },
        ]
    )
    with pd.ExcelWriter(products_path, engine="openpyxl") as writer:
        products.to_excel(writer, sheet_name="产品信息汇总表", index=False)

    dataset = load_return_dataset_auto(returns_path, products_path)

    assert dataset.primary_store == ""
    assert set(dataset.records["store"]) == {""}
    assert set(dataset.records["listing"]) == {""}
    assert set(dataset.records["product_match_status"]) == {"unmatched"}
    assert dataset.records["matched_msku"].isna().all()
    assert dataset.records["product_name"].isna().all()
