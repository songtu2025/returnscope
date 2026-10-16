from pathlib import Path

import pandas as pd
import pytest
from test_dataset_catalog import catalog_context as catalog_context

from web_backend.dataset_files import DatasetRevisionConflict, _sha256_file
from web_backend.datasets.product_store import save_product_workbook


def _store_fixture(service, source):
    digest = _sha256_file(source)
    with service.database.transaction() as connection:
        connection.execute(
            "UPDATE dataset_versions SET sha256=? WHERE id='version-products'",
            (digest,),
        )
        save_product_workbook(
            connection, digest, pd.read_excel(source, sheet_name=None, dtype=str)
        )


@pytest.fixture
def product_completion_context(catalog_context):
    service, _queries = catalog_context
    source = Path(service.version_file("dataset-products")["file_path"])
    original = pd.read_excel(source, dtype=str)
    frame = original.copy()
    notes = pd.DataFrame({"说明": ["SYNTHETIC-NOTES"]})
    with pd.ExcelWriter(source, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name="产品信息汇总表", index=False)
        notes.to_excel(writer, sheet_name="附加信息", index=False)
    _store_fixture(service, source)
    existing = {
        "store": "SEEKWAY:US",
        "msku": "SOURCE-MSKU-1",
        "listing": "SYNTHETIC-LISTING",
        "category_a": "SYNTHETIC-A",
        "category_b": "SYNTHETIC-B",
        "product_name": "",
    }
    added = {**existing, "msku": "SYNTHETIC-NEW", "product_name": "SYNTHETIC-NAME"}
    return service, source, frame, notes, [existing, added]


@pytest.mark.parametrize("with_product_name", [True, False])
def test_product_category_completion_preserves_workbook_and_audit(
    product_completion_context, with_product_name: bool
) -> None:
    service, source, original, notes, items = product_completion_context
    if not with_product_name:
        original = original.drop(columns=["产品名称"])
        with pd.ExcelWriter(source, engine="openpyxl") as writer:
            original.to_excel(writer, sheet_name="产品信息汇总表", index=False)
            notes.to_excel(writer, sheet_name="附加信息", index=False)
        _store_fixture(service, source)
    result = service.complete_product_categories(
        "dataset-products", 1, None, items, " 合成品类补全 ", "user-1"
    )
    assert result["current_version"] == 2
    destination = service.version_file("dataset-products")["file_path"]
    workbook = pd.read_excel(destination, sheet_name=None, dtype=str)
    saved = workbook["产品信息汇总表"].fillna("")
    assert saved["MSKU"].tolist() == ["SOURCE-MSKU-1", "SYNTHETIC-NEW"]
    assert saved["Listing"].tolist() == ["SYNTHETIC-LISTING"] * 2
    assert saved["品类A"].tolist() == ["SYNTHETIC-A"] * 2
    assert saved["品类B"].tolist() == ["SYNTHETIC-B"] * 2
    if with_product_name:
        assert saved["产品名称"].tolist() == [*original["产品名称"], "SYNTHETIC-NAME"]
    else:
        assert "产品名称" not in saved.columns
    assert saved["SKU"].tolist() == [*original["SKU"], ""]
    pd.testing.assert_frame_equal(workbook["附加信息"], notes)
    audit = next(
        item
        for item in result["audit"]
        if item["action"] == "dimension_category_completion"
    )
    assert audit["before"]["items"] == [
        {
            "msku": "SOURCE-MSKU-1",
            "store": "SEEKWAY:US",
            "rows": [0],
            "category_a": "水鞋",
            "category_b": "薄底水鞋",
        },
        {"store": "SEEKWAY:US", "msku": "SYNTHETIC-NEW", "rows": []},
    ]
    assert audit["after"]["items"] == items
    assert audit["after"]["note"] == "合成品类补全"
    assert not list((service.settings.data_dir / "tmp").glob("dimension_*.xlsx"))


def test_product_category_completion_rejects_duplicate_before_write(
    product_completion_context,
) -> None:
    service, source, _original, _notes, items = product_completion_context
    original_bytes = source.read_bytes()
    with pytest.raises(ValueError, match="商品重复提交"):
        service.complete_product_categories(
            "dataset-products", 1, None, [items[0], items[0]], "合成重复", "user-1"
        )
    assert source.read_bytes() == original_bytes
    result = service.get("dataset-products")
    assert result["current_version"] == 1
    assert len(result["versions"]) == 1
    assert result["audit"] == []


def test_product_category_completion_rejects_stale_version_before_write(
    product_completion_context,
) -> None:
    service, source, _original, _notes, items = product_completion_context
    original_bytes = source.read_bytes()
    with pytest.raises(DatasetRevisionConflict, match="刷新后重试"):
        service.complete_product_categories(
            "dataset-products", 2, None, items, "合成旧版本", "user-1"
        )
    assert source.read_bytes() == original_bytes
    result = service.get("dataset-products")
    assert result["current_version"] == 1
    assert len(result["versions"]) == 1
    assert result["audit"] == []


def test_product_import_rejects_duplicate_keys(product_completion_context):
    service, source, original, _, _ = product_completion_context
    pd.concat([original, original], ignore_index=True).to_excel(
        source, sheet_name="产品信息汇总表", index=False
    )
    with pytest.raises(ValueError, match="必须唯一"):
        service.add_version(
            "dataset-products",
            source,
            source.name,
            "application/xlsx",
            "重复商品",
            "user-1",
        )
    assert service.get("dataset-products")["current_version"] == 1
