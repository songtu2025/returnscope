from collections.abc import Iterator
from copy import deepcopy
from dataclasses import replace
from typing import Any
from unittest.mock import Mock, call

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from test_dashboard_router_contract import RouteCase

from web_backend.database import Database
from web_backend.review_service import (
    ReviewBatchConflict,
    ReviewService,
    RevisionConflict,
)
from web_backend.routers.reviews import create_review_router

RECORD_BODY = {"expected_revision": 5, "reason": "验证单条复核"}
BULK_BODY = {
    "records": [{"id": "review-1", "expected_revision": 5}],
    "action": "confirm",
    "reason": "验证批量复核",
}
ASSESSMENT_DEFAULTS = {
    "label_correctness": None,
    "evidence_completeness": None,
    "review_routing": None,
}
RECORD_DEFAULTS = {
    "batch_id": "batch-1",
    "review_id": "review-1",
    "expected_revision": 5,
    "actor_id": "42",
    "label_code": None,
    "note": "验证单条复核",
    "action": "confirm",
    "review_assessment": ASSESSMENT_DEFAULTS,
    "semantic_item_reviews": None,
    "added_semantic_items": None,
    "coverage_status": None,
}
ROUTE_CASES = (
    RouteCase(service_method="list", path="/api/reviews", args=(None, None)),
    RouteCase(service_method="get", path="/api/reviews/review-1", args=("review-1",)),
    RouteCase(
        service_method="resolve",
        path="/api/reviews/review-1",
        method="PATCH",
        request={"json": {"expected_revision": 5, "note": "验证处理"}},
        kwargs={
            "review_id": "review-1",
            "actor_id": "42",
            "expected_revision": 5,
            "label_code": None,
            "note": "验证处理",
        },
    ),
    RouteCase(
        service_method="create_batch",
        path="/api/classification-results/version-1/review-batches",
        method="POST",
        request={"json": {"reason": "验证创建"}},
        args=("version-1", "42", "验证创建"),
        status=201,
    ),
    RouteCase(
        service_method="list_batches",
        path="/api/review-batches",
        kwargs={
            "page": 1,
            "page_size": 50,
            "status": None,
            "base_result_version_id": None,
            "q": None,
        },
    ),
    RouteCase(
        service_method="get_batch",
        path="/api/review-batches/batch-1",
        args=("batch-1",),
    ),
    RouteCase(
        service_method="batch_records",
        path="/api/review-batches/batch-1/records",
        args=("batch-1",),
        kwargs={
            "page": 1,
            "page_size": 50,
            "workflow_status": None,
            "q": None,
            "listing": None,
            "product_name": None,
            "product_sku": None,
            "order_id": None,
        },
    ),
    RouteCase(
        service_method="update_batch_record",
        path="/api/review-batches/batch-1/records/review-1",
        method="PATCH",
        request={"json": RECORD_BODY},
        kwargs=RECORD_DEFAULTS,
    ),
    RouteCase(
        service_method="update_batch_records",
        path="/api/review-batches/batch-1/records",
        method="PATCH",
        request={"json": BULK_BODY},
        kwargs={
            "batch_id": "batch-1",
            "records": BULK_BODY["records"],
            "actor_id": "42",
            "action": "confirm",
            "label_code": None,
            "note": "验证批量复核",
            "review_assessment": ASSESSMENT_DEFAULTS,
        },
    ),
    RouteCase(
        service_method="publish_batch",
        path="/api/review-batches/batch-1/publish",
        method="POST",
        request={"json": {"expected_revision": 5, "reason": "验证发布"}},
        kwargs={
            "batch_id": "batch-1",
            "expected_revision": 5,
            "actor_id": "42",
            "reason": "验证发布",
        },
    ),
)
CASES_BY_METHOD = {case.service_method: case for case in ROUTE_CASES}
FILTER_CASES = (
    replace(
        CASES_BY_METHOD["list"],
        request={"params": {"workflow_status": "pending", "task_id": "task-1"}},
        args=("pending", "task-1"),
    ),
    replace(
        CASES_BY_METHOD["list_batches"],
        request={
            "params": {
                "page": "2",
                "page_size": "7",
                "status": "draft",
                "base_result_version_id": "version-2",
                "q": "合成",
            }
        },
        kwargs={
            "page": 2,
            "page_size": 7,
            "status": "draft",
            "base_result_version_id": "version-2",
            "q": "合成",
        },
    ),
    replace(
        CASES_BY_METHOD["batch_records"],
        request={
            "params": {
                "page": "3",
                "page_size": "7",
                "workflow_status": "pending",
                "q": "合成",
                "listing": "SK001",
                "product_name": "合成水鞋",
                "product_sku": "SKU-1",
                "order_id": "synthetic-order",
            }
        },
        kwargs={
            "page": 3,
            "page_size": 7,
            "workflow_status": "pending",
            "q": "合成",
            "listing": "SK001",
            "product_name": "合成水鞋",
            "product_sku": "SKU-1",
            "order_id": "synthetic-order",
        },
    ),
)
ERROR_STATUSES = {
    "list": (None, None, None, None),
    "get": (None, None, None, None),
    "resolve": (400, 409, 400, None),
    "create_batch": (400, 400, 409, None),
    "list_batches": (400, 400, 400, None),
    "get_batch": (404, 404, 404, None),
    "batch_records": (404, 404, 404, None),
    "update_batch_record": (400, 409, 409, None),
    "update_batch_records": (400, 409, 409, None),
    "publish_batch": (400, 409, 409, None),
}


def synthetic_user() -> dict[str, int]:
    return {"id": 42}


@pytest.fixture
def harness(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, Mock, Mock, Mock]]:
    service = Mock(spec=ReviewService)
    service.standard_service = Mock()
    database = Mock(spec=Database)
    audit = Mock(return_value=[{"action": "synthetic-review"}])
    monkeypatch.setattr("web_backend.routers.reviews.list_audit", audit)
    app = FastAPI()
    app.include_router(create_review_router(service, database, synthetic_user))
    with TestClient(app) as client:
        yield client, service, database, audit


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
    "semantic_input,semantic_expected",
    [
        (None, None),
        ([], []),
        (
            [
                {
                    "semantic_item_id": " item-1 ",
                    "action": "no_tag_needed",
                    "label_code": None,
                    "note": None,
                }
            ],
            [{"semantic_item_id": "item-1", "action": "no_tag_needed"}],
        ),
    ],
)
@pytest.mark.parametrize(
    "added_input,added_expected",
    [
        (None, None),
        ([], []),
        (
            [
                {
                    "item_id": None,
                    "evidence_text": " 合成证据 ",
                    "opinion": " 合成观点 ",
                    "label_code": " FIT_TOO_SMALL_U1 ",
                    "note": None,
                }
            ],
            [
                {
                    "evidence_text": "合成证据",
                    "opinion": "合成观点",
                    "label_code": "FIT_TOO_SMALL_U1",
                }
            ],
        ),
    ],
)
def test_single_record_preserves_optional_semantic_details_and_assessment(
    harness: tuple[TestClient, Mock, Mock, Mock],
    semantic_input: Any,
    semantic_expected: Any,
    added_input: Any,
    added_expected: Any,
) -> None:
    client, service, _, _ = harness
    service.update_batch_record.return_value = {"revision": 6}
    assessment = {
        "label_correctness": "partial",
        "evidence_completeness": "missing",
        "review_routing": "correct",
    }
    body = {
        **RECORD_BODY,
        **assessment,
        "action": "modify",
        "label_code": "FIT_TOO_SMALL_U1",
        "semantic_item_reviews": semantic_input,
        "added_semantic_items": added_input,
        "coverage_status": "has_omission",
    }
    before = deepcopy(body)
    response = client.patch(CASES_BY_METHOD["update_batch_record"].path, json=body)
    assert response.status_code == 200
    service.update_batch_record.assert_called_once_with(
        **{
            **RECORD_DEFAULTS,
            "action": "modify",
            "label_code": "FIT_TOO_SMALL_U1",
            "review_assessment": assessment,
            "semantic_item_reviews": semantic_expected,
            "added_semantic_items": added_expected,
            "coverage_status": "has_omission",
        }
    )
    assert body == before


@pytest.mark.parametrize("action", ["confirm", "modify", "exclude"])
def test_bulk_records_preserve_revisions_action_and_assessment(
    harness: tuple[TestClient, Mock, Mock, Mock],
    action: str,
) -> None:
    client, service, _, _ = harness
    service.update_batch_records.return_value = {"revision": 6}
    records = [
        {"id": "review-1", "expected_revision": 5},
        {"id": "review-2", "expected_revision": 8},
    ]
    assessment = {
        "label_correctness": "correct",
        "evidence_completeness": "complete",
        "review_routing": "should_manual_review",
    }
    body = {
        **BULK_BODY,
        **assessment,
        "records": records,
        "action": action,
        "label_code": "FIT_TOO_SMALL_U1",
    }
    response = client.patch(CASES_BY_METHOD["update_batch_records"].path, json=body)
    assert response.status_code == 200
    service.update_batch_records.assert_called_once_with(
        batch_id="batch-1",
        records=records,
        actor_id="42",
        action=action,
        label_code="FIT_TOO_SMALL_U1",
        note="验证批量复核",
        review_assessment=assessment,
    )


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
        ("create_batch", {"json": {"reason": ""}}, ["body", "reason"]),
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
            {"json": {"expected_revision": 5, "reason": ""}},
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
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == location
    assert service.mock_calls == database.mock_calls == audit.mock_calls == []
