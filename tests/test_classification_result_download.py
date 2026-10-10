from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from test_classification_result_openapi import _bind_result_standard
from test_classification_result_pool import _publish, _seed_result_context
from test_manual_correction import _items, _record
from test_result_version_reviews import _publish_review_required

from web_backend.classification_result_service import ClassificationResultService
from web_backend.classification_results.manual_correction import correct_group
from web_backend.classification_results.result_export import semantic_export_rows
from web_backend.classification_standard_service import ClassificationStandardService
from web_backend.routers.task_download_routes import register_task_download_routes
from web_backend.task_service import TaskService

RESULT_COLUMNS = [
    "source_record_id",
    "source_row",
    "return_date",
    "order_id",
    "store_site",
    "listing",
    "product_name",
    "source_sku",
    "matched_msku",
    "product_sku",
    "asin",
    "category_a",
    "category_b",
    "reason",
    "comment",
    "product_match_status",
    "quality_status",
    "processing_status",
    "semantic_disposition",
    "problem_labels",
    "classification_json",
]


@pytest.fixture
def context(tmp_path: Path) -> SimpleNamespace:
    value = _seed_result_context(tmp_path)
    value.version = _publish(value)
    _bind_result_standard(
        ClassificationStandardService(value.database),
        value.version["result_id"],
        value.taxonomy.version,
    )
    value.service = ClassificationResultService(value.database)
    return value


def test_workbook_keeps_source_rows_fields_json_and_semantic_paths(context) -> None:
    version_id = context.version["version_id"]
    content, filename = context.service.download(version_id)
    book = load_workbook(BytesIO(content))
    assert filename == "classification-L1-v1.xlsx"
    assert book.sheetnames == ["分类结果", "语义层级"]
    results = list(book["分类结果"].values)
    assert list(results[0]) == RESULT_COLUMNS
    assert [row[1] for row in results[1:]] == [2, 3, 4]
    records = context.service.records(version_id)["items"]
    for row, record in zip(results[1:], records, strict=True):
        exported = dict(zip(RESULT_COLUMNS, row, strict=True))
        assert json.loads(exported["classification_json"]) == record["classification"]
        assert exported["product_name"] == "产品表权威名称"
        assert exported["comment"] == record["comment"]
        assert exported["problem_labels"] == " | ".join(record["problem_labels"])
    semantics = list(book["语义层级"].values)
    for row, record in zip(semantics[1:], records, strict=True):
        exported = dict(zip(semantics[0], row, strict=True))
        fact = record["atomic_facts"][0]
        assert exported["完整路径"] == " → ".join(fact["label_path"])
        assert exported["label_code"] == fact["label_code"]
        assert exported["source_row"] == record["source_row"]
    book.close()


def test_empty_workbook_keeps_empty_sheets_and_fallback_filename(context) -> None:
    with context.database.transaction() as connection:
        connection.execute("DELETE FROM classification_result_records")
        connection.execute("UPDATE classification_results SET listing = NULL")
    content, filename = context.service.download(context.version["version_id"])
    assert filename == f"classification-{context.version['result_id']}-v1.xlsx"
    book = load_workbook(BytesIO(content))
    assert book.sheetnames == ["分类结果", "语义层级"]
    assert all(list(book[name].values) == [] for name in book.sheetnames)
    book.close()


def test_semantic_rows_keep_dynamic_column_order_and_optional_values() -> None:
    condition = {"surface": "湿地"}
    item = {
        "source_record_id": "合成来源",
        "source_row": 2,
        "atomic_facts": [
            {"label_code": "A", "label_path": ["一级"], "condition": condition},
            {
                "label_code": "B",
                "label_path": ["一级", "二级", "三级"],
                "certainty": "UNCERTAIN",
                "fact_text_zh": "合成事实",
                "evidence": "原文",
            },
        ],
    }
    rows = semantic_export_rows(item, {"standard_version_id": "合成标准"})
    assert [row["label_code"] for row in rows] == ["A", "B"]
    assert rows[0]["条件"] is condition
    assert rows[0]["确定性"] == "AFFIRMED"
    assert rows[0]["因果归属"] == rows[0]["证据来源"] == "UNKNOWN"
    assert rows[0]["中文事实"] == ""
    assert rows[1]["完整路径"] == "一级 → 二级 → 三级"
    assert rows[1]["确定性"] == "UNCERTAIN"
    assert list(rows[1])[-5:] == [
        "第1级标签",
        "第2级标签",
        "第3级标签",
        "证据原文",
        "标准版本",
    ]
    assert semantic_export_rows({**item, "atomic_facts": []}, {}) == []


def test_download_keeps_three_reads_without_member_queries(
    context, monkeypatch
) -> None:
    statements = []
    connect = context.database.connect

    def traced_connection():
        connection = connect()
        connection.set_trace_callback(statements.append)
        return connection

    monkeypatch.setattr(context.database, "connect", traced_connection)
    content, _ = context.service.download(context.version["version_id"])
    assert content.startswith(b"PK")
    reads = [sql for sql in statements if sql.lstrip().upper().startswith("SELECT")]
    assert len(reads) == 3


def test_task_downloads_use_current_manual_result_instead_of_checkpoint(tmp_path: Path):
    context, version = _publish_review_required(tmp_path)
    service = ClassificationResultService(context.database)
    correct_group(
        service, version["version_id"], _record(context, version), _items(), "user-2"
    )
    tasks = TaskService(context.database)
    segment = tasks.get(context.task_id)["segments"][0]
    router = APIRouter()
    register_task_download_routes(router, tasks, lambda: {"id": "user-1"})
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    paths = [
        f"/api/tasks/{context.task_id}/download",
        f"/api/tasks/{context.task_id}/segments/{segment['segment_key']}/download",
    ]
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200
        book = load_workbook(BytesIO(response.content))
        values = list(book["分类结果"].values)
        records = [dict(zip(values[0], row, strict=True)) for row in values[1:]]
        for record in records:
            classification = json.loads(record["classification_json"])
            if record["order_id"] == "ORDER-DUP":
                assert classification["semantic_units"][0]["opinion"] == "整体尺寸偏小"
                assert record["quality_status"] == "ready"
            else:
                assert record["quality_status"] == "review_required"
        book.close()
