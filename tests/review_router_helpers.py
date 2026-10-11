from collections.abc import Iterator
from dataclasses import replace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from router_contract_helpers import RouteCase

from web_backend.database import Database
from web_backend.review_service import (
    ReviewService,
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
