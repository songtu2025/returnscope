from pathlib import Path
from types import SimpleNamespace

import pytest
from test_dataset_preview import _write_products
from test_manual_correction import _items, _record
from test_result_version_reviews import _publish_review_required

from web_backend.classification_result_publication import ResultPublicationConflict
from web_backend.classification_result_service import ClassificationResultService
from web_backend.classification_results.effective_content import load_content
from web_backend.classification_results.manual_correction import correct_group
from web_backend.classification_results.semantic_history import (
    SemanticRestore,
    correction_history,
)
from web_backend.common import json_value
from web_backend.dataset_files import DatasetRevisionConflict
from web_backend.dataset_service import DatasetService
from web_backend.datasets.product_restore import restore_product_edit


def test_semantic_restore_keeps_other_groups_and_refuses_stale_version(tmp_path: Path):
    context, version = _publish_review_required(tmp_path)
    service = ClassificationResultService(context.database)
    record = _record(context, version)
    changed = correct_group(service, version["version_id"], record, _items(), "user-2")
    with context.database.connect() as connection:
        row = connection.execute(
            "SELECT after_json FROM audit_logs WHERE action='manual_correction'"
        ).fetchone()
        history = correction_history(
            connection,
            version["result_id"],
            json_value(row["after_json"], {})["source_rows"],
        )
    restored = correct_group(
        service,
        changed["version_id"],
        _record(context, changed),
        SemanticRestore(history[0]["id"]),
        "user-2",
    )
    with context.database.connect() as connection:
        content = load_content(connection, restored["version_id"])
        target_key = next(
            row["classification_key"]
            for row in content["records"]
            if row["order_id"] == "ORDER-DUP"
        )
        target = next(
            unit["classification"]
            for unit in content["units"]
            if unit["classification_key"] == target_key
        )
    assert target["primary_label_codes"] == history[0]["before"]["primary_label_codes"]
    assert target["human_review_assessment"]["resolved"]
    with pytest.raises(ResultPublicationConflict):
        correct_group(
            service,
            changed["version_id"],
            _record(context, changed),
            SemanticRestore(history[0]["id"]),
            "user-2",
        )


def test_product_restore_uses_current_revision_and_records_new_edit(tmp_path: Path):
    context, _ = _publish_review_required(tmp_path)
    service = DatasetService(context.database, SimpleNamespace(data_dir=tmp_path))
    path = tmp_path / "products.xlsx"
    _write_products(path)
    product = service.create(
        name="产品信息",
        kind="products",
        description="",
        source_path=path,
        original_name=path.name,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        change_note="合成导入",
        actor_id="user-1",
    )
    changed = service.update_product_row(
        product["id"],
        0,
        product["current_version"],
        {"产品名称": "修改后的产品"},
        "合成修改",
        "user-1",
    )
    with context.database.connect() as connection:
        audit = connection.execute(
            "SELECT id FROM audit_logs WHERE entity_id=? AND action='dimension_row_update'",
            (product["id"],),
        ).fetchone()[0]
    restored = restore_product_edit(
        service, product["id"], audit, changed["current_version"], "user-1"
    )
    assert restored["current_version"] == changed["current_version"] + 1
    assert service.preview_rows(product["id"])["records"][0]["产品名称"] == "测试商品"
    with pytest.raises(DatasetRevisionConflict):
        restore_product_edit(
            service, product["id"], audit, changed["current_version"], "user-1"
        )
