from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from test_classification_result_pool import _seed_result_context

from web_backend.common import add_audit
from web_backend.dataset_files import DatasetRevisionConflict
from web_backend.dataset_service import DatasetService


@pytest.fixture
def catalog_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    context = _seed_result_context(tmp_path)
    add_audit(context.database, "dataset", "dataset-returns", "inspect", "user-1")
    with context.database.transaction() as connection:
        for import_id in ["import-1", "import-2"]:
            connection.execute(
                """
                INSERT INTO dataset_imports(
                    id, dataset_id, resulting_version_id, mode,
                    raw_file_path, original_name, content_type, size_bytes,
                    raw_sha256, row_count, column_count, schema_json,
                    quality_json, created_by, created_at
                ) VALUES (?, 'dataset-returns', 'version-returns', 'create',
                          'synthetic.csv', 'synthetic.csv', 'text/csv', 1,
                          'synthetic-sha', 3, 10, '[]', '{}', 'user-1',
                          '2026-08-12T00:00:00+00:00')
                """,
                (import_id,),
            )
    queries = []
    original_connect = context.database.connect

    def connect():
        connection = original_connect()
        connection.set_trace_callback(queries.append)
        return connection

    monkeypatch.setattr(context.database, "connect", connect)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    return service, queries


@pytest.mark.parametrize(
    "include,expected_fields,query_count",
    [
        (None, {"versions", "imports", "audit"}, 4),
        (set(), set(), 1),
        ({"unknown"}, set(), 1),
        ({"versions"}, {"versions"}, 2),
        ({"imports"}, {"imports"}, 2),
        ({"audit"}, {"audit"}, 2),
    ],
)
def test_dataset_details_include_only_requested_history(
    catalog_context, include, expected_fields, query_count
) -> None:
    service, queries = catalog_context

    item = service.get("dataset-returns", include)

    assert item is not None
    assert item.keys() & {"versions", "imports", "audit"} == expected_fields
    assert item["task_reference_count"] == 1
    assert item["source_name"] == "退货数据"
    assert len(queries) == query_count
    if "versions" in expected_fields:
        assert [version["version"] for version in item["versions"]] == [1]
        assert "file_path" not in item["versions"][0]
    if "imports" in expected_fields:
        assert [entry["id"] for entry in item["imports"]] == ["import-2", "import-1"]
        assert all("raw_file_path" not in entry for entry in item["imports"])
    if "audit" in expected_fields:
        assert len(item["audit"]) == 1


def test_missing_dataset_does_not_query_history(catalog_context) -> None:
    service, queries = catalog_context

    assert service.get("absent") is None
    assert len(queries) == 1


@pytest.fixture
def product_completion_context(catalog_context):
    service, _queries = catalog_context
    source = Path(service.version_file("dataset-products")["file_path"])
    original = pd.read_excel(source, dtype=str)
    frame = pd.concat([original, original], ignore_index=True)
    notes = pd.DataFrame({"说明": ["SYNTHETIC-NOTES"]})
    with pd.ExcelWriter(source, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name="产品信息汇总表", index=False)
        notes.to_excel(writer, sheet_name="附加信息", index=False)
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
    result = service.complete_product_categories(
        "dataset-products", 1, None, items, " 合成品类补全 ", "user-1"
    )
    assert result["current_version"] == 2
    destination = service.version_file("dataset-products")["file_path"]
    workbook = pd.read_excel(destination, sheet_name=None, dtype=str)
    saved = workbook["产品信息汇总表"].fillna("")
    assert saved["MSKU"].tolist() == ["SOURCE-MSKU-1", "SOURCE-MSKU-1", "SYNTHETIC-NEW"]
    assert saved["Listing"].tolist() == ["SYNTHETIC-LISTING"] * 3
    assert saved["品类A"].tolist() == ["SYNTHETIC-A"] * 3
    assert saved["品类B"].tolist() == ["SYNTHETIC-B"] * 3
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
            "rows": [0, 1],
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
