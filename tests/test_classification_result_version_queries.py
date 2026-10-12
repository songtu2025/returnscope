from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_classification_result_pool import (
    _clone_publishable_segment,
    _publish,
    _seed_result_context,
)
from test_manual_correction import _items, _record
from test_result_version_reviews import _publish_review_required

from web_backend.classification_result_service import ClassificationResultService
from web_backend.classification_results.manual_correction import correct_group
from web_backend.classification_results.version_queries import version_list_filters
from web_backend.routers.classification_results import (
    create_classification_result_router,
)


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


def test_record_status_filter_ignores_overall_version_quality(context) -> None:
    version_id = context.version["version_id"]
    with context.database.transaction() as connection:
        connection.execute(
            "UPDATE classification_result_versions SET quality_status = 'unusable' "
            "WHERE id = ?",
            (version_id,),
        )
        connection.execute(
            "UPDATE classification_result_records SET quality_status = 'review_required' "
            "WHERE result_version_id = ? AND order_id = 'ORDER-OTHER'",
            (version_id,),
        )
    for status in ("ready", "review_required"):
        result = context.service.list(quality_status=status)
        assert result["total"] == 1
        assert result["items"][0]["version_id"] == version_id
    assert context.service.list(quality_status="unusable")["total"] == 0


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


def test_manual_history_counts_only_current_correction_and_scopes_audit(tmp_path: Path):
    context, version = _publish_review_required(tmp_path)
    service = ClassificationResultService(context.database)
    first = correct_group(
        service, version["version_id"], _record(context, version), _items(), "user-2"
    )
    second = correct_group(
        service,
        first["version_id"],
        _record(context, first),
        [{**_items()[0], "opinion": "尺码偏小"}],
        "user-1",
    )
    assert second["changed_unit_count"] == 1
    assert len(service.history(second["version_id"])) == 3
    from web_backend.common import insert_audit

    with context.database.transaction() as connection:
        insert_audit(
            connection,
            actor_id="user-1",
            action="manual_correction",
            entity_type="classification_result",
            entity_id="other-result",
            before={},
            after={"version_id": second["version_id"], "reason": "其他结果"},
        )
    assert (
        service.history(second["version_id"])[0]["manual_change"]["reason"]
        == "人工修正语义"
    )


def test_manual_history_and_actor_metadata(tmp_path: Path):
    context, version = _publish_review_required(tmp_path)
    service = ClassificationResultService(context.database)
    corrected = correct_group(
        service, version["version_id"], _record(context, version), _items(), "user-2"
    )
    history = service.history(corrected["version_id"])
    assert history[0]["changed_unit_count"] == 1
    assert history[0]["manual_change"]["reason"] == "人工修正语义"
    assert (
        history[0]["manual_change"]["before"]["classification"]["semantic_units"]
        != history[0]["manual_change"]["after"]["classification"]["semantic_units"]
    )
    assert "manual_change" not in history[1]
    groups = service.record_groups(corrected["version_id"])["items"]
    assessment = groups[0]["record"]["classification"]["human_review_assessment"]
    assert assessment["resolved"]
    assert assessment["assessed_by_name"] == "用户二"


def test_manual_history_and_actor_api_contract(tmp_path: Path):
    context, version = _publish_review_required(tmp_path)
    service = ClassificationResultService(context.database)
    corrected = correct_group(
        service, version["version_id"], _record(context, version), _items(), "user-2"
    )
    app = FastAPI()
    app.include_router(
        create_classification_result_router(service, lambda: {"id": "user-2"})
    )
    client = TestClient(app)
    url = f"/api/classification-results/{corrected['version_id']}"
    history = client.get(f"{url}/versions")
    assert history.status_code == 200
    assert history.json()[0]["manual_change"]["reason"] == "人工修正语义"
    assert history.json()[0]["manual_change"]["after"]["atomic_facts"]
    groups = client.get(f"{url}/record-groups")
    assert groups.status_code == 200
    assessment = groups.json()["items"][0]["record"]["classification"][
        "human_review_assessment"
    ]
    assert assessment["resolved"] and assessment["assessed_by_name"] == "用户二"


def test_feedback_search_uses_current_results_and_requires_login(
    tmp_path: Path,
) -> None:
    context, version = _publish_review_required(tmp_path)
    service = ClassificationResultService(context.database)
    current = correct_group(
        service, version["version_id"], _record(context, version), _items(), "user-2"
    )
    results = service.search_record_groups("small")
    assert results["items"]
    assert all(
        group["record"]["result_version_id"] == current["version_id"]
        for group in results["items"]
    )
    assert service.search_record_groups("%_")["total"] == 0
    app = FastAPI()
    app.include_router(
        create_classification_result_router(service, lambda: {"id": "user-1"})
    )
    response = TestClient(app).get(
        "/api/classification-results/search", params={"q": "small"}
    )
    assert response.status_code == 200
    assert (
        response.json()["items"][0]["record"]["result_version_id"]
        == current["version_id"]
    )

    from fastapi import HTTPException

    def require_login():
        raise HTTPException(status_code=401, detail="请登录")

    protected_app = FastAPI()
    protected_app.include_router(
        create_classification_result_router(service, require_login)
    )
    anonymous = TestClient(protected_app)
    assert (
        anonymous.get(
            "/api/classification-results/search", params={"q": "small"}
        ).status_code
        == 401
    )
    assert (
        anonymous.get(
            "/api/classification-results/search", params={"q": "small", "limit": 51}
        ).status_code
        != 200
    )
    assert (
        TestClient(app)
        .get("/api/classification-results/search", params={"q": "small", "limit": 51})
        .status_code
        == 422
    )
