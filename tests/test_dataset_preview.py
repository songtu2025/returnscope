from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd
from return_import_helpers import (
    _create_task_input,
    _return_row,
    _write_returns,
)
from test_classification_result_pool import _seed_result_context

from return_semantics.data import (
    PRODUCT_COLUMNS,
)
from web_backend.common import add_audit
from web_backend.dataset_service import DatasetService


def _write_products(path: Path) -> None:
    rows = [
        {
            PRODUCT_COLUMNS[0]: "MSKU-1",
            PRODUCT_COLUMNS[1]: "SENWAYZON:US",
            PRODUCT_COLUMNS[2]: "LISTING-1",
            "品类A": "眼镜",
            "品类B": "太阳镜",
            "产品名称": "测试商品",
            "SKU": "SKU-1",
        },
        {
            PRODUCT_COLUMNS[0]: "MSKU-2",
            PRODUCT_COLUMNS[1]: "SENWAYZON:US",
            PRODUCT_COLUMNS[2]: "LISTING-2",
            "品类A": "手套",
            "品类B": "",
            "产品名称": "测试手套",
            "SKU": "SKU-2",
        },
    ]
    pd.DataFrame(rows).to_excel(path, sheet_name="产品信息汇总表", index=False)


def test_product_preview_uses_database_without_excel(
    tmp_path: Path, monkeypatch
) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    source = tmp_path / "products.xlsx"
    _write_products(source)

    created = service.create(
        name="商品信息",
        kind="products",
        description="",
        source_path=source,
        original_name=source.name,
        content_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        change_note="首次导入",
        actor_id="user-1",
    )

    def fail_excel(*args, **kwargs):
        raise AssertionError("产品预览不应解析 Excel")

    monkeypatch.setattr(pd, "read_excel", fail_excel)
    assert service.preview_rows(str(created["id"]))["facets"]["categories"] == [
        "手套",
        "眼镜 > 太阳镜",
    ]
    assert service.preview_rows(str(created["id"]), query="MSKU-1")["total"] == 1


def test_return_preview_reads_database_without_parsing_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    source = tmp_path / "bounded.csv"
    _write_returns(
        source,
        [_return_row(f"O-{index}", "偏小") for index in range(20)],
    )
    created = _create_task_input(service, source)

    def no_file(*args, **kwargs):
        raise AssertionError("反馈预览不应解析文件")

    monkeypatch.setattr(pd, "read_csv", no_file)
    monkeypatch.setattr(pd, "read_excel", no_file)
    preview = service.preview_rows(str(created["id"]), offset=5, limit=2)

    assert preview["source_total"] == 20
    assert [record["_row_index"] for record in preview["records"]] == [5, 6]
    assert service.preview_rows(str(created["id"]), query="O-19")["total"] == 1
    assert service.preview_rows(str(created["id"]), store="SENWAYZON:US")["total"] == 20


def test_retained_product_history_is_not_used_as_current_input(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    with context.database.transaction() as connection:
        connection.execute(
            "UPDATE dataset_versions SET version = 2 WHERE id = 'version-products'"
        )
        connection.execute(
            "UPDATE datasets SET current_version = 2 WHERE id = 'dataset-products'"
        )
        connection.execute(
            """
            INSERT INTO dataset_versions (
                id, dataset_id, version, file_path, original_name, content_type,
                size_bytes, sha256, row_count, column_count, schema_json,
                quality_json, change_note, created_by, created_at
            ) SELECT 'retired-products', dataset_id, 1, 'retired-do-not-read.xlsx',
                     original_name, content_type, size_bytes, 'retired-sha256',
                     row_count, column_count, schema_json, quality_json,
                     change_note, created_by, created_at
              FROM dataset_versions WHERE id = 'version-products'
            """
        )
    add_audit(
        context.database,
        "dataset",
        "dataset-products",
        "import",
        "user-1",
        after={"version_id": "retired-products"},
    )

    assert [item["version_id"] for item in service.list_versions("products")] == [
        "version-products"
    ]
    current = service.get("dataset-products")
    assert [item["id"] for item in current["versions"]] == ["version-products"]
    assert current["audit"][0]["after"] == {"version_id": "retired-products"}
    assert service.version_file("dataset-products", 1)["version"] == 2
    assert (
        service.preview_rows("dataset-products", version=1)["records"]
        == (service.preview_rows("dataset-products")["records"])
    )
    assert service.product_scopes("retired-products") == service.product_scopes(
        "version-products"
    )
