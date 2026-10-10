from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_classification_result_pool import _publish, _seed_result_context

from web_backend.classification_result_service import ClassificationResultService
from web_backend.common import json_text, json_value


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


@pytest.mark.parametrize(
    "semantic_status", ["POSITIVE", "NEGATIVE", "MIXED", "CONFLICT", "NO_CONFIRMED"]
)
@pytest.mark.parametrize(
    "quality", ["ready", "review_required", "unusable", "excluded"]
)
@pytest.mark.parametrize("rerun", [True, False])
def test_result_filters_match_display_status_and_preserve_group_counts(
    context, semantic_status, quality, rerun
) -> None:
    version_id = context.version["version_id"]
    with context.database.transaction() as connection:
        row = connection.execute(
            "SELECT classification_json FROM classification_units"
        ).fetchone()
        payload = json_value(row[0], {})
        payload["comment_summary"] = {
            "status": semantic_status,
            "fact_ids": ["synthetic-fact"],
        }
        connection.execute(
            "UPDATE classification_units SET classification_json = ?, quality_status = ?, system_rerun_required = ?",
            (json_text(payload), quality, int(rerun)),
        )
        connection.execute(
            "UPDATE classification_result_records SET quality_status = ?", (quality,)
        )
    filters = {
        "quality_status": quality,
        "comment_status": semantic_status,
        "system_rerun_required": str(rerun).lower(),
    }
    first = context.service.record_groups(version_id, page_size=1, **filters)
    assert (first["total"], first["source_total"]) == (2, 3)
    assert first["items"][0]["member_count"] == 2
    assert first["items"][0]["record"]["comment_summary_status"] == semantic_status
    assert first["items"][0]["record"]["system_rerun_required"] is rerun
    second = context.service.record_groups(version_id, page=2, page_size=1, **filters)
    assert second["items"][0]["members"][0]["source_row"] == 4
    records = context.service.records(version_id, page_size=1, **filters)
    assert records["total"] == 3
    assert records["items"][0]["comment_summary_status"] == semantic_status
    assert records["items"][0]["system_rerun_required"] is rerun
    opposite = context.service.record_groups(
        version_id, system_rerun_required=str(not rerun).lower()
    )
    assert opposite["total"] == opposite["source_total"] == 0
    mismatched = "unusable" if quality != "unusable" else "ready"
    empty = context.service.record_groups(
        version_id, **{**filters, "quality_status": mismatched}
    )
    assert (empty["total"], empty["source_total"], empty["items"]) == (0, 0, [])


def test_legacy_semantics_use_existing_projection_before_pagination(context) -> None:
    version_id = context.version["version_id"]
    with context.database.transaction() as connection:
        connection.execute(
            "UPDATE classification_units SET classification_json = "
            "json_remove(classification_json, '$.comment_summary')"
        )
    result = context.service.record_groups(
        version_id, comment_status="NEGATIVE", order_id="ORDER-OTHER", page_size=1
    )
    assert (result["total"], result["source_total"]) == (1, 1)
    assert result["items"][0]["record"]["comment_summary_status"] == "NEGATIVE"
    assert result["items"][0]["members"][0]["source_row"] == 4
    empty = context.service.record_groups(version_id, comment_status="POSITIVE")
    assert empty["items"] == []


def test_semantic_filter_calculates_duplicate_units_once_per_request(
    context, monkeypatch
) -> None:
    from web_backend.classification_results import record_filters

    calculate = Mock(wraps=record_filters.classification_comment_status)
    monkeypatch.setattr(record_filters, "classification_comment_status", calculate)
    result = context.service.record_groups(
        context.version["version_id"], comment_status="NEGATIVE"
    )
    assert result["total"] == 2
    assert calculate.call_count == 1


@pytest.mark.parametrize("method", ["records", "record_groups"])
def test_invalid_semantic_filter_is_rejected(context, method) -> None:
    with pytest.raises(ValueError, match="comment_status 不合法"):
        getattr(context.service, method)(
            context.version["version_id"], comment_status="UNKNOWN"
        )


def test_rerun_filter_selects_unit_members_before_group_pagination(context) -> None:
    version_id = context.version["version_id"]
    with context.database.transaction() as connection:
        # 隔离测试中增加另一个分类单元，验证不会按结果质量猜测重跑范围。
        unit = dict(connection.execute("SELECT * FROM classification_units").fetchone())
        unit.update(
            id="synthetic-retry-unit",
            classification_key="synthetic-retry",
            system_rerun_required=1,
        )
        columns = ", ".join(unit)
        placeholders = ", ".join("?" for _ in unit)
        connection.execute(
            f"INSERT INTO classification_units ({columns}) VALUES ({placeholders})",
            tuple(unit.values()),
        )
        connection.execute(
            "UPDATE classification_result_records SET classification_key = 'synthetic-retry' WHERE order_id = 'ORDER-OTHER'"
        )
    retry = context.service.record_groups(
        version_id, system_rerun_required="true", page_size=1
    )
    assert (retry["total"], retry["source_total"]) == (1, 1)
    assert retry["items"][0]["record"]["order_id"] == "ORDER-OTHER"
    assert retry["items"][0]["record"]["system_rerun_required"] is True
    keep = context.service.record_groups(
        version_id, system_rerun_required="false", page_size=1
    )
    assert (keep["total"], keep["source_total"]) == (1, 2)
    assert keep["items"][0]["member_count"] == 2
    assert keep["items"][0]["record"]["system_rerun_required"] is False
    empty = context.service.record_groups(
        version_id, system_rerun_required="true", page=2, page_size=1
    )
    assert empty["items"] == [] and empty["total"] == 1
