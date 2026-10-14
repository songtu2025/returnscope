from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pandas as pd
import pytest
from test_classification_result_pool import _publish, _seed_result_context
from test_task_detail_queries import _add_segment

from web_backend.agent_runner import AgentRunner
from web_backend.classification_result_service import ResultPublicationError
from web_backend.datasets.current_products import sync_product_display


def test_publication_excel_parsing_does_not_block_other_writers(tmp_path, monkeypatch):
    seed = _seed_result_context(tmp_path)
    _add_segment(seed.database, seed.segment_id, "background", "running")
    parsing, release = Event(), Event()
    read_excel = pd.read_excel

    def parse(*args, **kwargs):
        parsing.set()
        assert release.wait(5)
        return read_excel(*args, **kwargs)

    def update_progress():
        with seed.database.transaction() as connection:
            connection.execute(
                "UPDATE task_segments SET progress_current=1 WHERE id=?",
                ("background",),
            )

    monkeypatch.setattr("web_backend.datasets.current_products.pd.read_excel", parse)
    with ThreadPoolExecutor(max_workers=2) as executor:
        publication = executor.submit(_publish, seed)
        try:
            assert parsing.wait(5)
            executor.submit(update_progress).result(timeout=2)
        finally:
            release.set()
            publication.result(timeout=5)
    with seed.database.connect() as connection:
        assert (
            connection.execute(
                "SELECT progress_current FROM task_segments WHERE id='background'"
            ).fetchone()[0]
            == 1
        )


def test_product_change_during_parsing_rolls_back_and_can_be_republished(
    tmp_path, monkeypatch
):
    seed = _seed_result_context(tmp_path)
    checkpoint = tmp_path / "saved-checkpoint.json"
    AgentRunner._write_checkpoint(checkpoint, seed.results)
    original_checkpoint = checkpoint.read_bytes()
    with seed.database.transaction() as connection:
        connection.execute(
            "UPDATE task_segments SET result_json_path=? WHERE id=?",
            (str(checkpoint), seed.segment_id),
        )
    read_excel = pd.read_excel

    def parse(*args, **kwargs):
        frame = read_excel(*args, **kwargs)
        updated = frame.copy()
        updated["产品名称"] = "更新后的商品"
        updated_path = tmp_path / "updated-products.xlsx"
        updated.to_excel(updated_path, sheet_name="产品信息汇总表", index=False)
        with seed.database.transaction(immediate=True) as connection:
            connection.execute(
                "UPDATE dataset_versions SET sha256='new-products-sha', file_path=? WHERE id='version-products'",
                (str(updated_path),),
            )
        return frame

    monkeypatch.setattr("web_backend.datasets.current_products.pd.read_excel", parse)
    with pytest.raises(ResultPublicationError, match="产品信息已更新"):
        _publish(seed)
    with seed.database.connect() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM classification_result_versions"
            ).fetchone()[0]
            == 0
        )
        segment = connection.execute(
            "SELECT * FROM task_segments WHERE id=?", (seed.segment_id,)
        ).fetchone()
        assert segment["result_publish_status"] == "failed"
        assert segment["result_version_id"] is None
        assert segment["result_json_path"] == str(checkpoint)
        assert checkpoint.read_bytes() == original_checkpoint
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM task_events WHERE event_type='segment_completed'"
            ).fetchone()[0]
            == 0
        )
    monkeypatch.setattr(
        "web_backend.datasets.current_products.pd.read_excel", read_excel
    )
    published = _publish(seed)
    assert published["publish_status"] == "published"
    with seed.database.connect() as connection:
        assert {
            row[0]
            for row in connection.execute(
                "SELECT product_name FROM classification_result_records"
            )
        } == {"更新后的商品"}
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM classification_result_versions"
            ).fetchone()[0]
            == 1
        )


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
