from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from test_classification_result_pool import _seed_result_context

from web_backend.common import add_audit
from web_backend.dataset_files import DatasetRevisionConflict
from web_backend.dataset_service import DatasetService
from web_backend.tasks.snapshots import frozen_product_input


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


def test_product_save_updates_current_input_and_preserves_task_input(
    catalog_context,
) -> None:
    service, _queries = catalog_context
    before = service.get("dataset-products")
    original = Path(service.version_file("dataset-products")["file_path"]).read_bytes()
    saved = service.update_product_row(
        "dataset-products", 0, 1, {"产品名称": "最新合成商品"}, "修正名称", "user-1"
    )
    assert saved["version_id"] == before["version_id"]
    assert len(saved["versions"]) == len(service.list_versions("products")) == 1
    assert (
        service.preview_rows("dataset-products")["records"][0]["产品名称"]
        == "最新合成商品"
    )
    assert service.version_file("dataset-products", 1) == service.version_file(
        "dataset-products"
    )
    with service.database.connect() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM dataset_versions WHERE dataset_id = 'dataset-products'"
            ).fetchone()[0]
            == 1
        )
        task = dict(
            connection.execute(
                "SELECT snapshot_json FROM tasks WHERE id = 'task-1'"
            ).fetchone()
        )
    current = service.version_file("dataset-products")
    task.update(
        product_file_path=current["file_path"],
        product_sha256=saved["versions"][0]["sha256"],
    )
    frozen = frozen_product_input(task)
    assert Path(frozen["product_file_path"]).read_bytes() == original
    assert (
        pd.read_excel(frozen["product_file_path"], dtype=str).iloc[0]["产品名称"]
        == "产品表权威名称"
    )
    with pytest.raises(DatasetRevisionConflict):
        service.update_product_row(
            "dataset-products", 0, 1, {"产品名称": "过期修改"}, "验证冲突", "user-1"
        )
    assert service.get("dataset-products")["current_version"] == 2
    assert service.references(saved["version_id"])["total"] == 1


def test_product_update_rolls_back_when_dependent_refresh_fails(
    catalog_context, monkeypatch
) -> None:
    service, _queries = catalog_context
    before = service.get("dataset-products")

    def fail(*args, **kwargs):
        raise RuntimeError("合成关联更新失败")

    monkeypatch.setattr("web_backend.dataset_service.refresh_product_dependents", fail)
    with pytest.raises(RuntimeError, match="合成关联更新失败"):
        service.update_product_row(
            "dataset-products", 0, 1, {"产品名称": "失败修改"}, "验证回滚", "user-1"
        )
    assert service.get("dataset-products") == before


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


def test_product_alias_can_return_to_its_own_identifier(catalog_context):
    service, _ = catalog_context
    service.update_product_row(
        "dataset-products", 0, 1, {"MSKU": "UPDATED-MSKU"}, "修改标识", "user-1"
    )
    result = service.update_product_row(
        "dataset-products", 0, 2, {"MSKU": "SOURCE-MSKU-1"}, "恢复标识", "user-1"
    )
    assert result["current_version"] == 3


def test_product_alias_rejects_ambiguous_duplicate_rows(product_completion_context):
    service, _, _, _, _ = product_completion_context
    with pytest.raises(ValueError, match="存在重复"):
        service.update_product_row(
            "dataset-products", 0, 1, {"MSKU": "UPDATED-MSKU"}, "重复商品", "user-1"
        )
    assert service.get("dataset-products")["current_version"] == 1


def test_product_audit_failure_rolls_back_saved_data(catalog_context, monkeypatch):
    service, _ = catalog_context
    before = service.get("dataset-products")

    def fail(*args, **kwargs):
        raise RuntimeError("合成留痕失败")

    monkeypatch.setattr("web_backend.datasets.current_products.insert_audit", fail)
    with pytest.raises(RuntimeError, match="合成留痕失败"):
        service.update_product_row(
            "dataset-products", 0, 1, {"MSKU": "UPDATED-MSKU"}, "验证事务", "user-1"
        )
    assert service.get("dataset-products") == before
    with service.database.connect() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM product_identity_aliases"
            ).fetchone()[0]
            == 0
        )
