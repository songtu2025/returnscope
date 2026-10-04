from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_classification_result_pool import (
    _clone_publishable_segment,
    _publish,
    _seed_result_context,
)

from web_backend.classification_result_service import ClassificationResultService
from web_backend.classification_results.version_queries import version_list_filters


@pytest.fixture
def context(tmp_path: Path) -> SimpleNamespace:
    value = _seed_result_context(tmp_path)
    value.version = _publish(value)
    value.service = ClassificationResultService(value.database)
    return value


@pytest.mark.parametrize("query", ["%", "_", "\\", "  %_\\  "])
def test_search_treats_wildcards_as_literal(context, query: str) -> None:
    other = _publish(_clone_publishable_segment(context, "search"))
    with context.database.transaction() as connection:
        connection.execute(
            "UPDATE classification_result_records SET product_name = ? "
            "WHERE result_version_id = ?",
            ("合成%_\\产品", other["version_id"]),
        )
    result = context.service.list(q=query, page_size=1)
    assert result["total"] == 1
    assert [item["version_id"] for item in result["items"]] == [other["version_id"]]


def test_blank_search_and_out_of_range_page_keep_total(context) -> None:
    first = context.service.list(q=" \t ", page_size=1)
    empty = context.service.list(q=" \t ", page=2, page_size=1)
    assert first["total"] == empty["total"] == 1
    assert empty == {"items": [], "total": 1, "page": 2, "page_size": 1}


def test_filters_combine_before_pagination(context) -> None:
    _publish(_clone_publishable_segment(context, "other"))
    with context.database.transaction() as connection:
        connection.execute(
            "UPDATE classification_results SET listing = 'L2' WHERE id = ?",
            (context.version["result_id"],),
        )
    result = context.service.list(
        q="SOURCE-MSKU",
        store_site="SEEKWAY:US",
        listing="L2",
        quality_status=context.version["quality_status"],
        page_size=1,
    )
    assert result["total"] == 1
    assert result["items"] == [context.service.get(context.version["version_id"])]
    assert context.service.list(listing="不存在")["total"] == 0


def test_latest_unpublished_version_does_not_hide_published(context) -> None:
    with context.database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO classification_result_versions(
                id, result_id, source_segment_id, version_no, content_hash, quality_status,
                publish_status, unit_count, record_count, created_at
            ) VALUES ('unpublished', ?, 'segment-1', 2, 'synthetic', ?, 'publishing', 0, 0, ?)
            """,
            (
                context.version["result_id"],
                context.version["quality_status"],
                context.version["created_at"],
            ),
        )
    assert context.service.list()["items"] == [context.version]
    assert context.service.history(context.version["version_id"]) == [context.version]


@pytest.mark.parametrize(
    "arguments,message",
    [
        ({"page": 0}, "page 必须"),
        ({"page_size": 0}, "page_size 必须"),
        ({"page_size": 201}, "page_size 必须"),
        ({"quality_status": "invalid"}, "quality_status 不合法"),
        ({"page": 0, "quality_status": "invalid"}, "page 必须"),
    ],
)
def test_invalid_filters_preserve_validation_priority(
    context, arguments, message
) -> None:
    with pytest.raises(ValueError, match=message):
        context.service.list(**arguments)


def test_filter_builder_reuses_pattern_and_quality_validation() -> None:
    pattern = Mock(return_value="escaped")
    validate = Mock()
    where, params = version_list_filters(
        {"q": " 合成 ", "store_site": "US", "listing": "L1", "quality_status": "Q"},
        pattern,
        validate,
    )
    pattern.assert_called_once_with("合成")
    validate.assert_called_once_with("Q")
    assert "EXISTS" in where
    assert params == ["escaped"] * 4 + ["US", "L1", "Q"]


def test_list_uses_two_queries_in_one_connection(context, monkeypatch) -> None:
    statements = []
    connections = []
    connect = context.database.connect

    def traced_connection():
        connection = connect()
        connection.set_trace_callback(statements.append)
        connections.append(connection)
        return connection

    monkeypatch.setattr(context.database, "connect", traced_connection)
    result = context.service.list(q="SOURCE-MSKU", page_size=1)
    assert result["total"] == 1
    assert len(connections) == 1
    reads = [sql for sql in statements if sql.lstrip().upper().startswith("SELECT")]
    assert len(reads) == 2
    assert "COUNT(*)" in reads[0]
    assert "LIMIT 1 OFFSET 0" in reads[1]
