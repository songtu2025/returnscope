from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_classification_result_pool import _publish, _seed_result_context

from web_backend.classification_result_service import ClassificationResultService


@pytest.fixture
def context(tmp_path: Path) -> SimpleNamespace:
    value = _seed_result_context(tmp_path)
    value.version = _publish(value)
    value.service = ClassificationResultService(value.database)
    return value


@pytest.mark.parametrize("order_id", [None, "", "  "])
def test_missing_order_ids_keep_source_records_separate(context, order_id) -> None:
    with context.database.transaction() as connection:
        connection.execute(
            "UPDATE classification_result_records SET order_id = ?",
            (order_id,),
        )
    result = context.service.record_groups(context.version["version_id"])
    assert result["total"] == result["source_total"] == 3
    assert [group["member_count"] for group in result["items"]] == [1, 1, 1]
    assert [group["members"][0]["source_row"] for group in result["items"]] == [2, 3, 4]


def test_group_filter_runs_before_pagination_and_keeps_empty_page_totals(
    context,
) -> None:
    version_id = context.version["version_id"]
    filtered = context.service.record_groups(
        version_id, order_id="ORDER-OTHER", page_size=1
    )
    assert filtered["total"] == filtered["source_total"] == 1
    assert filtered["items"][0]["members"][0]["source_row"] == 4
    empty = context.service.record_groups(version_id, page=3, page_size=1)
    assert empty == {
        "items": [],
        "total": 2,
        "source_total": 3,
        "page": 3,
        "page_size": 1,
    }
    missing = context.service.record_groups(version_id, order_id="不存在")
    assert missing["items"] == []
    assert missing["total"] == missing["source_total"] == 0


def test_members_keep_evidence_and_sort_tied_source_rows_by_record_id(context) -> None:
    with context.database.transaction() as connection:
        connection.execute(
            "UPDATE classification_result_records SET source_origin_id = '合成来源A', "
            "comment = '原文A', reason = '原因A', id = 'synthetic-b' WHERE source_row = 2"
        )
        connection.execute(
            "UPDATE classification_result_records SET source_origin_id = '合成来源B', "
            "comment = '原文B', reason = '原因B', id = 'synthetic-a', "
            "source_row = 2 WHERE source_row = 3"
        )
    group = context.service.record_groups(
        context.version["version_id"], order_id="ORDER-DUP"
    )["items"][0]
    members = group["members"]
    assert group["member_count"] == len(members) == 2
    assert [item["source_record_id"] for item in members] == [
        "version-returns:3",
        "version-returns:2",
    ]
    assert [item["source_row"] for item in members] == [2, 2]
    assert {
        (item["source_origin_id"], item["comment"], item["reason"]) for item in members
    } == {
        ("合成来源A", "原文A", "原因A"),
        ("合成来源B", "原文B", "原因B"),
    }


@pytest.mark.parametrize(
    "filters,queries", [({}, 4), ({"problem": "FIT_TOO_SMALL_U1"}, 5)]
)
def test_group_queries_are_constant_and_enrichment_runs_once_per_group(
    context, monkeypatch, filters, queries
) -> None:
    statements = []
    connections = []
    connect = context.database.connect

    def traced_connection():
        connection = connect()
        connection.set_trace_callback(statements.append)
        connections.append(connection)
        return connection

    enrich = Mock(wraps=context.service._enrich_record)
    monkeypatch.setattr(context.service, "_enrich_record", enrich)
    monkeypatch.setattr(context.database, "connect", traced_connection)
    result = context.service.record_groups(context.version["version_id"], **filters)
    assert result["total"] == 2
    assert result["source_total"] == 3
    assert enrich.call_count == 2
    assert len(connections) == (4 if filters else 3)
    reads = [
        sql for sql in statements if sql.lstrip().upper().startswith(("SELECT", "WITH"))
    ]
    assert len(reads) == queries
    assert len([sql for sql in reads if sql.lstrip().startswith("WITH filtered")]) == 2
