from pathlib import Path

import pandas as pd

from return_semantics.capabilities import load_capability_registry
from return_semantics.data import (
    load_return_dataset,
    load_return_dataset_auto,
    normalize_comment,
    read_return_csv,
)
from return_semantics.task_plan import build_category_execution_plan

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_normalize_comment_decodes_html_and_whitespace() -> None:
    assert normalize_comment("  It&#39;s\n too\t small  ") == "It's too small"


def test_return_csv_supports_utf8_cp1252_and_gb18030(tmp_path: Path) -> None:
    utf8_path = tmp_path / "utf8.csv"
    utf8_path.write_text("comment\n鞋子太大\n", encoding="utf-8-sig")
    cp1252_path = tmp_path / "cp1252.csv"
    cp1252_path.write_bytes("comment\nDidn’t fit\n".encode("cp1252"))
    gb18030_path = tmp_path / "gb18030.csv"
    gb18030_path.write_bytes("comment\n鞋子太大\n".encode("gb18030"))

    assert read_return_csv(utf8_path).iloc[0]["comment"] == "鞋子太大"
    assert read_return_csv(cp1252_path).iloc[0]["comment"] == "Didn’t fit"
    assert read_return_csv(gb18030_path).iloc[0]["comment"] == "鞋子太大"


def test_real_sk001_data_matches_business_baseline(
    seekway_business_baseline_files: tuple[Path, Path],
) -> None:
    returns_path, products_path = seekway_business_baseline_files
    dataset = load_return_dataset(
        returns_path,
        products_path,
        store="SEEKWAY:US",
        listing="SK001",
    )

    assert len(dataset.mskus) == 280
    assert len(dataset.records) == 9140
    assert int(dataset.records["has_text_evidence"].sum()) == 5758
    assert len(dataset.unique_comments) == 3347
    assert set(dataset.unique_comments["category_a"]) == {"水鞋"}


def test_classification_key_isolated_by_product_category(tmp_path: Path) -> None:
    returns_path = tmp_path / "returns.csv"
    products_path = tmp_path / "products.xlsx"
    pd.DataFrame(
        [
            {
                "return-date": "2026-01-01",
                "order-id": "1",
                "sku": "SKU-HAT",
                "asin": "",
                "fnsku": "",
                "product-name": "hat",
                "quantity": "1",
                "reason": "NOT_AS_DESCRIBED",
                "customer-comments": "Too small",
            },
            {
                "return-date": "2026-01-01",
                "order-id": "2",
                "sku": "SKU-GLASSES",
                "asin": "",
                "fnsku": "",
                "product-name": "glasses",
                "quantity": "1",
                "reason": "NOT_AS_DESCRIBED",
                "customer-comments": "Too small",
            },
        ]
    ).to_csv(returns_path, index=False, encoding="utf-8-sig")
    products = pd.DataFrame(
        [
            {
                "MSKU": "SKU-HAT",
                "店铺/站点": "STORE",
                "Listing": "HAT",
                "品类A": "遮阳帽",
                "品类B": "儿童渔夫帽",
            },
            {
                "MSKU": "SKU-GLASSES",
                "店铺/站点": "STORE",
                "Listing": "GLASSES",
                "品类A": "眼镜",
                "品类B": "儿童眼镜",
            },
        ]
    )
    with pd.ExcelWriter(products_path, engine="openpyxl") as writer:
        products.to_excel(writer, sheet_name="产品信息汇总表", index=False)

    dataset = load_return_dataset(
        returns_path,
        products_path,
        store="STORE",
    )

    assert len(dataset.unique_comments) == 2
    assert dataset.unique_comments["classification_key"].nunique() == 2


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
