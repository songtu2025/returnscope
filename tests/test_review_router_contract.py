from copy import deepcopy
from typing import Any
from unittest.mock import Mock, call

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from review_router_helpers import (
    BULK_BODY,
    CASES_BY_METHOD,
    ERROR_STATUSES,
    FILTER_CASES,
    RECORD_BODY,
    ROUTE_CASES,
    synthetic_user,
)
from review_router_helpers import harness as harness
from router_contract_helpers import RouteCase

from web_backend.review_contracts import LEGACY_REVIEW_BATCH_MESSAGE
from web_backend.review_service import (
    ReviewBatchConflict,
    RevisionConflict,
)

RETIRED_METHODS = {
    "create_batch",
    "update_batch_record",
    "update_batch_records",
    "publish_batch",
}


@pytest.mark.parametrize(
    "case", (*ROUTE_CASES, *FILTER_CASES), ids=lambda case: case.service_method
)
def test_review_routes_preserve_responses_and_service_arguments(
    harness: tuple[TestClient, Mock, Mock, Mock],
    case: RouteCase,
) -> None:
    client, service, _, audit = harness
    payload = {"id": "synthetic-response", "revision": 6}
    expected = [payload] if case.service_method == "list" else payload
    getattr(service, case.service_method).return_value = expected
    response = client.request(case.method, case.path, **case.request)
    if case.service_method in RETIRED_METHODS:
        assert response.status_code == 410
        assert response.json() == {"detail": LEGACY_REVIEW_BATCH_MESSAGE}
        assert service.mock_calls == audit.mock_calls == []
        return
    assert response.status_code == case.status
    assert response.json() == expected
    assert service.mock_calls == [
        getattr(call, case.service_method)(*case.args, **case.kwargs)
    ]
    assert audit.mock_calls == []


@pytest.mark.parametrize(
    "case",
    (
        *ROUTE_CASES,
        RouteCase(service_method="taxonomy", path="/api/taxonomy"),
        RouteCase(service_method="audit", path="/api/audit/review/review-1"),
    ),
    ids=lambda case: case.service_method,
)
def test_all_review_routes_require_login_before_reading_or_writing(
    harness: tuple[TestClient, Mock, Mock, Mock],
    case: RouteCase,
) -> None:
    client, service, database, audit = harness

    def reject_user() -> dict[str, Any]:
        raise HTTPException(status_code=401, detail="请先登录")

    client.app.dependency_overrides[synthetic_user] = reject_user
    response = client.request(case.method, case.path, **case.request)
    assert response.status_code == 401
    assert response.json() == {"detail": "请先登录"}
    assert service.mock_calls == database.mock_calls == audit.mock_calls == []


@pytest.mark.parametrize(
    "case,error_type,status",
    [
        pytest.param(
            case, error_type, status, id=f"{case.service_method}-{error_type.__name__}"
        )
        for case in ROUTE_CASES
        if case.service_method not in RETIRED_METHODS
        for error_type, status in zip(
            (ValueError, RevisionConflict, ReviewBatchConflict, RuntimeError),
            ERROR_STATUSES[case.service_method],
            strict=True,
        )
    ],
)
def test_review_routes_preserve_exception_subclasses_and_capture_order(
    harness: tuple[TestClient, Mock, Mock, Mock],
    case: RouteCase,
    error_type: type[Exception],
    status: int | None,
) -> None:
    client, service, _, _ = harness
    error = error_type("合成复核异常")
    getattr(service, case.service_method).side_effect = error
    if status is None:
        with pytest.raises(error_type) as raised:
            client.request(case.method, case.path, **case.request)
        assert raised.value is error
    else:
        response = client.request(case.method, case.path, **case.request)
        assert response.status_code == status
        assert response.json() == {"detail": "合成复核异常"}
    assert service.mock_calls == [
        getattr(call, case.service_method)(*case.args, **case.kwargs)
    ]


@pytest.mark.parametrize(
    "item,status,expected",
    [
        (None, 404, {"detail": "复核记录不存在"}),
        ({}, 200, {}),
    ],
)
def test_get_review_only_treats_none_as_missing(
    harness: tuple[TestClient, Mock, Mock, Mock],
    item: Any,
    status: int,
    expected: dict[str, Any],
) -> None:
    client, service, _, _ = harness
    service.get.return_value = item
    response = client.get("/api/reviews/review-1")
    assert response.status_code == status
    assert response.json() == expected
    service.get.assert_called_once_with("review-1")


def test_taxonomy_uses_current_standard_and_json_serialization(
    harness: tuple[TestClient, Mock, Mock, Mock],
) -> None:
    client, service, database, audit = harness
    service.standard_service.combined_taxonomy.return_value.model_dump.return_value = {
        "categories": [],
        "version": "synthetic",
    }
    response = client.get("/api/taxonomy")
    assert response.status_code == 200
    assert response.json() == {"categories": [], "version": "synthetic"}
    assert service.standard_service.mock_calls == [
        call.combined_taxonomy(),
        call.combined_taxonomy().model_dump(mode="json"),
    ]
    assert database.mock_calls == audit.mock_calls == []


def test_entity_audit_keeps_database_and_entity_arguments(
    harness: tuple[TestClient, Mock, Mock, Mock],
) -> None:
    client, service, database, audit = harness
    response = client.get("/api/audit/review/review-1")
    assert response.status_code == 200
    assert response.json() == [{"action": "synthetic-review"}]
    audit.assert_called_once_with(database, "review", "review-1")
    assert service.mock_calls == database.mock_calls == []


@pytest.mark.parametrize("path", ["/api/taxonomy", "/api/audit/review/review-1"])
def test_auxiliary_routes_do_not_hide_unexpected_failures(
    harness: tuple[TestClient, Mock, Mock, Mock],
    path: str,
) -> None:
    client, service, _, audit = harness
    error = RuntimeError("合成辅助查询失败")
    service.standard_service.combined_taxonomy.side_effect = error
    audit.side_effect = error
    with pytest.raises(RuntimeError) as raised:
        client.get(path)
    assert raised.value is error


@pytest.mark.parametrize(
    "service_method,override,location",
    [
        (
            "resolve",
            {"json": {"expected_revision": 0, "note": "合成"}},
            ["body", "expected_revision"],
        ),
        ("resolve", {"json": {"expected_revision": 5, "note": ""}}, ["body", "note"]),
        ("create_batch", {"json": {"reason": "x" * 501}}, ["body", "reason"]),
        ("list_batches", {"params": {"page": "0"}}, ["query", "page"]),
        ("list_batches", {"params": {"page_size": "201"}}, ["query", "page_size"]),
        ("batch_records", {"params": {"page": "0"}}, ["query", "page"]),
        ("batch_records", {"params": {"page_size": "201"}}, ["query", "page_size"]),
        (
            "update_batch_record",
            {"json": {**RECORD_BODY, "action": "invalid"}},
            ["body", "action"],
        ),
        (
            "update_batch_record",
            {
                "json": {
                    **RECORD_BODY,
                    "semantic_item_reviews": [
                        {"semantic_item_id": "item-1", "action": "change_label"}
                    ],
                }
            },
            ["body", "semantic_item_reviews", 0],
        ),
        (
            "update_batch_record",
            {
                "json": {
                    **RECORD_BODY,
                    "added_semantic_items": [
                        {
                            "evidence_text": "",
                            "opinion": "合成观点",
                            "label_code": "FIT_TOO_SMALL_U1",
                        }
                    ],
                }
            },
            ["body", "added_semantic_items", 0, "evidence_text"],
        ),
        (
            "update_batch_records",
            {"json": {**BULK_BODY, "records": []}},
            ["body", "records"],
        ),
        (
            "update_batch_records",
            {
                "json": {
                    **BULK_BODY,
                    "records": [{"id": "review-1", "expected_revision": 0}],
                }
            },
            ["body", "records", 0, "expected_revision"],
        ),
        (
            "publish_batch",
            {"json": {"expected_revision": 0, "reason": "合成"}},
            ["body", "expected_revision"],
        ),
        (
            "publish_batch",
            {"json": {"expected_revision": 5, "reason": "x" * 501}},
            ["body", "reason"],
        ),
    ],
)
def test_invalid_review_requests_do_not_reach_service_or_database(
    harness: tuple[TestClient, Mock, Mock, Mock],
    service_method: str,
    override: dict[str, Any],
    location: list[Any],
) -> None:
    client, service, database, audit = harness
    case = CASES_BY_METHOD[service_method]
    request = deepcopy(case.request)
    request.update(override)
    response = client.request(case.method, case.path, **request)
    if service_method in RETIRED_METHODS:
        assert response.status_code == 410
        assert response.json() == {"detail": LEGACY_REVIEW_BATCH_MESSAGE}
    else:
        assert response.status_code == 422
        assert response.json()["detail"][0]["loc"] == location
    assert service.mock_calls == database.mock_calls == audit.mock_calls == []
