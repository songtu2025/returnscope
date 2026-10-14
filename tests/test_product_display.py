from pathlib import Path

import pandas as pd
import pytest
from test_classification_result_pool import _publish, _seed_result_context

from web_backend.datasets.current_products import sync_product_display


@pytest.mark.parametrize("use_alias", [False, True])
def test_product_sync_updates_only_referenced_identities(
    tmp_path: Path, monkeypatch, use_alias
):
    seed = _seed_result_context(tmp_path)
    _publish(seed)
    current_msku = "NEW-MSKU" if use_alias else "SOURCE-MSKU-1"
    frame = pd.DataFrame(
        [
            {
                "店铺/站点": "SEEKWAY:US",
                "MSKU": f"UNRELATED-{index}",
                "产品名称": "无关联商品",
                "SKU": "SKU",
                "ASIN": "ASIN",
            }
            for index in range(1000)
        ]
        + [
            {
                "店铺/站点": "SEEKWAY:US",
                "MSKU": current_msku,
                "产品名称": "最新商品",
                "SKU": "NEW-SKU",
                "ASIN": "NEW-ASIN",
            }
        ]
    )
    monkeypatch.setattr(
        "web_backend.datasets.current_products.pd.read_excel", lambda *a, **k: frame
    )
    with seed.database.transaction(immediate=True) as connection:
        if use_alias:
            connection.execute(
                "INSERT INTO product_identity_aliases VALUES ('dataset-products','SEEKWAY:US','SOURCE-MSKU-1','SEEKWAY:US','NEW-MSKU')"
            )
        before = dict(
            connection.execute(
                "SELECT * FROM classification_result_records LIMIT 1"
            ).fetchone()
        )
        statements = []
        connection.set_trace_callback(statements.append)
        sync_product_display(connection, "dataset-products")
        writes = [
            sql
            for sql in statements
            if sql.startswith("UPDATE classification_result_records")
        ]
        assert len(writes) == 1
        records = connection.execute(
            "SELECT * FROM classification_result_records"
        ).fetchall()
        assert len(records) == 3
        for row in records:
            assert (row["product_name"], row["product_sku"], row["asin"]) == (
                "最新商品",
                "NEW-SKU",
                "NEW-ASIN",
            )
            for name in [
                "listing",
                "category_a",
                "category_b",
                "matched_msku",
                "result_version_id",
            ]:
                assert row[name] == before[name]


def test_product_sync_keeps_ambiguous_fields_and_other_datasets(
    tmp_path: Path, monkeypatch
):
    seed = _seed_result_context(tmp_path)
    _publish(seed)
    with seed.database.connect() as connection:
        before = dict(
            connection.execute(
                "SELECT * FROM classification_result_records LIMIT 1"
            ).fetchone()
        )
    frame = pd.DataFrame(
        [
            {
                "店铺/站点": "SEEKWAY:US",
                "MSKU": "SOURCE-MSKU-1",
                "产品名称": name,
                "SKU": "CONFIRMED-SKU",
            }
            for name in ["歧义名称一", "歧义名称二"]
        ]
    )
    monkeypatch.setattr(
        "web_backend.datasets.current_products.pd.read_excel", lambda *a, **k: frame
    )
    with seed.database.transaction(immediate=True) as connection:
        sync_product_display(connection, "dataset-returns")
        assert (
            dict(
                connection.execute(
                    "SELECT * FROM classification_result_records LIMIT 1"
                ).fetchone()
            )
            == before
        )
        sync_product_display(connection, "dataset-products")
        for row in connection.execute("SELECT * FROM classification_result_records"):
            assert row["product_name"] == before["product_name"]
            assert row["product_sku"] == "CONFIRMED-SKU"
            assert row["asin"] == before["asin"]
