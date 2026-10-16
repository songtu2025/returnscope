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


def test_product_alias_can_return_to_its_own_identifier(catalog_context):
    service, _ = catalog_context
    service.update_product_row(
        "dataset-products", 0, 1, {"MSKU": "UPDATED-MSKU"}, "修改标识", "user-1"
    )
    result = service.update_product_row(
        "dataset-products", 0, 2, {"MSKU": "SOURCE-MSKU-1"}, "恢复标识", "user-1"
    )
    assert result["current_version"] == 3


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
