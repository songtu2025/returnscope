from collections.abc import Iterator
from copy import deepcopy
from dataclasses import dataclass, field, replace
from typing import Any
from unittest.mock import Mock, call

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from web_backend.dashboard_insights import InsightOptions
from web_backend.dashboard_service import (
    DashboardConflict,
    DashboardNotFound,
    DashboardService,
)
from web_backend.routers.dashboards import create_dashboard_router

BASE_PATH = "/api/analysis-dashboards"
VERSION_PATH = f"{BASE_PATH}/dashboard-1/versions/version-1"
PLAN_BODY = {"result_version_ids": ["result-1"]}
CREATE_BODY = {
    **PLAN_BODY,
    "name": "接口回归看板",
    "plan_hash": "a" * 64,
    "reason": "验证创建",
}
VERSION_BODY = {
    **PLAN_BODY,
    "expected_revision": 3,
    "plan_hash": "b" * 64,
    "reason": "验证版本",
}
INSIGHT_DEFAULTS = {
    "problem": None,
    "subject": None,
    "label_group": None,
    "listing": None,
    "product_name": None,
    "product_sku": None,
    "date_from": None,
    "date_to": None,
}
RECORD_DEFAULTS = {
    "problem": None,
    "listing": None,
    "product_name": None,
    "product_sku": None,
    "order_id": None,
    "quality_status": None,
}
INSIGHT_FILTERS = {
    "problem": "FIT_TOO_SMALL_U1",
    "subject": "PRODUCT",
    "label_group": "合成问题组",
    "listing": "SK001",
    "product_name": "合成水鞋",
    "product_sku": "SKU-1",
    "date_from": "2026-09-01",
    "date_to": "2026-09-30",
}
RECORD_FILTERS = {
    "problem": "FIT_TOO_SMALL_U1",
    "listing": "SK001",
    "product_name": "合成水鞋",
    "product_sku": "SKU-1",
    "order_id": "synthetic-order",
    "quality_status": "ready",
}


@dataclass(frozen=True, kw_only=True)
class RouteCase:
    service_method: str
    path: str
    method: str = "GET"
    request: dict[str, Any] = field(default_factory=dict)
    args: tuple[Any, ...] = ()
    kwargs: dict[str, Any] = field(default_factory=dict)
    status: int = 200


ROUTE_CASES = (
    RouteCase(
        service_method="preflight",
        path="/api/dashboard-plans/preflight",
        method="POST",
        request={"json": PLAN_BODY},
        args=(["result-1"], {}),
    ),
    RouteCase(
        service_method="create",
        path=BASE_PATH,
        method="POST",
        request={"json": CREATE_BODY},
        kwargs={**CREATE_BODY, "description": "", "filters": {}, "actor_id": "42"},
        status=201,
    ),
    RouteCase(
        service_method="create_version",
        path=f"{BASE_PATH}/dashboard-1/versions",
        method="POST",
        request={"json": VERSION_BODY},
        args=("dashboard-1",),
        kwargs={**VERSION_BODY, "filters": {}, "actor_id": "42"},
        status=201,
    ),
    RouteCase(
        service_method="list",
        path=BASE_PATH,
        kwargs={"page": 1, "page_size": 50, "q": None, "status": None},
    ),
    RouteCase(
        service_method="get",
        path=f"{BASE_PATH}/dashboard-1",
        args=("dashboard-1", None),
    ),
    RouteCase(
        service_method="versions",
        path=f"{BASE_PATH}/dashboard-1/versions",
        args=("dashboard-1",),
    ),
    RouteCase(
        service_method="summary",
        path=f"{VERSION_PATH}/summary",
        args=("dashboard-1", "version-1"),
    ),
    RouteCase(
        service_method="sources",
        path=f"{VERSION_PATH}/sources",
        args=("dashboard-1", "version-1"),
    ),
    RouteCase(
        service_method="insights",
        path=f"{VERSION_PATH}/insights",
        args=("dashboard-1", "version-1"),
        kwargs={**INSIGHT_DEFAULTS, "part": "full"},
    ),
    RouteCase(
        service_method="evidence_page",
        path=f"{VERSION_PATH}/evidence",
        request={"params": {"problem": "FIT_TOO_SMALL_U1"}},
        args=("dashboard-1", "version-1", InsightOptions(problem="FIT_TOO_SMALL_U1")),
        kwargs={"page": 1},
    ),
    RouteCase(
        service_method="drilldown",
        path=f"{VERSION_PATH}/drilldown",
        request={"params": {"group_by": "listing"}},
        args=("dashboard-1", "version-1", "listing"),
        kwargs={**RECORD_DEFAULTS, "page": 1, "page_size": 50},
    ),
    RouteCase(
        service_method="records",
        path=f"{VERSION_PATH}/records",
        args=("dashboard-1", "version-1"),
        kwargs={**RECORD_DEFAULTS, "page": 1, "page_size": 50},
    ),
)
CASES_BY_METHOD = {case.service_method: case for case in ROUTE_CASES}
HANDLED_ERRORS = {
    "preflight": {ValueError: 400, DashboardNotFound: 400, DashboardConflict: 400},
    "create": {DashboardConflict: 409, DashboardNotFound: 400, ValueError: 400},
    "create_version": {DashboardNotFound: 404, DashboardConflict: 409, ValueError: 400},
    "list": {ValueError: 400, DashboardNotFound: 400, DashboardConflict: 400},
    "get": {DashboardNotFound: 404},
    "versions": {DashboardNotFound: 404},
    "summary": {DashboardNotFound: 404},
    "sources": {DashboardNotFound: 404},
    "insights": {DashboardNotFound: 404, DashboardConflict: 400, ValueError: 400},
    "evidence_page": {DashboardNotFound: 404, DashboardConflict: 400, ValueError: 400},
    "drilldown": {DashboardNotFound: 404, DashboardConflict: 400, ValueError: 400},
    "records": {DashboardNotFound: 404, DashboardConflict: 400, ValueError: 400},
}


@pytest.fixture
def harness() -> Iterator[tuple[TestClient, Mock]]:
    service = Mock(spec=DashboardService)
    app = FastAPI()
    app.include_router(create_dashboard_router(service, lambda: {"id": 42}))
    with TestClient(app) as client:
        yield client, service


@pytest.mark.parametrize("case", ROUTE_CASES, ids=lambda case: case.service_method)
def test_dashboard_routes_preserve_success_and_default_arguments(
    harness: tuple[TestClient, Mock],
    case: RouteCase,
) -> None:
    client, service = harness
    payload = {"id": "synthetic-response", "nested": {"records": 3}}
    expected = [payload] if case.service_method in {"versions", "sources"} else payload
    getattr(service, case.service_method).return_value = expected

    response = client.request(case.method, case.path, **case.request)

    assert response.status_code == case.status
    assert response.json() == expected
    assert service.mock_calls == [
        getattr(call, case.service_method)(*case.args, **case.kwargs)
    ]


@pytest.mark.parametrize("case", ROUTE_CASES, ids=lambda case: case.service_method)
def test_every_dashboard_route_requires_login_before_calling_service(
    case: RouteCase,
) -> None:
    service = Mock(spec=DashboardService)
    app = FastAPI()

    def reject_user() -> dict[str, Any]:
        raise HTTPException(status_code=401, detail="请先登录")

    app.include_router(create_dashboard_router(service, reject_user))
    with TestClient(app) as client:
        response = client.request(case.method, case.path, **case.request)

    assert response.status_code == 401
    assert response.json() == {"detail": "请先登录"}
    assert service.mock_calls == []


@pytest.mark.parametrize(
    "case,error_type,expected_status",
    [
        pytest.param(
            case,
            error_type,
            HANDLED_ERRORS[case.service_method].get(error_type),
            id=f"{case.service_method}-{error_type.__name__}",
        )
        for case in ROUTE_CASES
        for error_type in (
            ValueError,
            DashboardNotFound,
            DashboardConflict,
            RuntimeError,
        )
    ],
)
def test_dashboard_routes_keep_individual_error_mapping(
    harness: tuple[TestClient, Mock],
    case: RouteCase,
    error_type: type[Exception],
    expected_status: int | None,
) -> None:
    client, service = harness
    error = error_type("合成服务异常")
    getattr(service, case.service_method).side_effect = error

    if expected_status is None:
        with pytest.raises(error_type) as raised:
            client.request(case.method, case.path, **case.request)
        assert raised.value is error
    else:
        response = client.request(case.method, case.path, **case.request)
        assert response.status_code == expected_status
        assert response.json() == {"detail": "合成服务异常"}
    assert service.mock_calls == [
        getattr(call, case.service_method)(*case.args, **case.kwargs)
    ]


@pytest.mark.parametrize(
    "case",
    [
        replace(
            CASES_BY_METHOD["list"],
            request={
                "params": {
                    "page": "2",
                    "page_size": "7",
                    "q": "合成",
                    "status": "archived",
                }
            },
            kwargs={"page": 2, "page_size": 7, "q": "合成", "status": "archived"},
        ),
        replace(
            CASES_BY_METHOD["get"],
            request={"params": {"version_id": "version-2"}},
            args=("dashboard-1", "version-2"),
        ),
        replace(
            CASES_BY_METHOD["insights"],
            request={"params": {**INSIGHT_FILTERS, "part": "reason"}},
            kwargs={**INSIGHT_FILTERS, "part": "reason"},
        ),
        replace(
            CASES_BY_METHOD["evidence_page"],
            request={"params": {**INSIGHT_FILTERS, "page": "3"}},
            args=("dashboard-1", "version-1", InsightOptions(**INSIGHT_FILTERS)),
            kwargs={"page": 3},
        ),
        replace(
            CASES_BY_METHOD["drilldown"],
            request={
                "params": {
                    **RECORD_FILTERS,
                    "group_by": "product_sku",
                    "page": "3",
                    "page_size": "7",
                }
            },
            args=("dashboard-1", "version-1", "product_sku"),
            kwargs={**RECORD_FILTERS, "page": 3, "page_size": 7},
        ),
        replace(
            CASES_BY_METHOD["records"],
            request={"params": {**RECORD_FILTERS, "page": "2", "page_size": "7"}},
            kwargs={**RECORD_FILTERS, "page": 2, "page_size": 7},
        ),
    ],
    ids=lambda case: case.service_method,
)
def test_dashboard_routes_forward_explicit_filters_and_pagination(
    harness: tuple[TestClient, Mock],
    case: RouteCase,
) -> None:
    client, service = harness
    getattr(service, case.service_method).return_value = {"total": 0, "items": []}

    response = client.request(case.method, case.path, **case.request)

    assert response.status_code == case.status
    assert service.mock_calls == [
        getattr(call, case.service_method)(*case.args, **case.kwargs)
    ]


@pytest.mark.parametrize(
    "service_method,request_override,location",
    [
        (
            "preflight",
            {"json": {"result_version_ids": []}},
            ["body", "result_version_ids"],
        ),
        ("create", {"json": {**CREATE_BODY, "name": ""}}, ["body", "name"]),
        ("create", {"json": {**CREATE_BODY, "reason": ""}}, ["body", "reason"]),
        (
            "create",
            {"json": {**CREATE_BODY, "plan_hash": "short"}},
            ["body", "plan_hash"],
        ),
        (
            "create_version",
            {"json": {**VERSION_BODY, "expected_revision": 0}},
            ["body", "expected_revision"],
        ),
        ("list", {"params": {"page": "0"}}, ["query", "page"]),
        ("list", {"params": {"page_size": "201"}}, ["query", "page_size"]),
        ("insights", {"params": {"part": "invalid"}}, ["query", "part"]),
        ("evidence_page", {"params": {}}, ["query", "problem"]),
        (
            "evidence_page",
            {"params": {"problem": "FIT_TOO_SMALL_U1", "page": "0"}},
            ["query", "page"],
        ),
        ("drilldown", {"params": {}}, ["query", "group_by"]),
        (
            "drilldown",
            {"params": {"group_by": "listing", "page_size": "201"}},
            ["query", "page_size"],
        ),
        ("records", {"params": {"page": "not-a-number"}}, ["query", "page"]),
        ("records", {"params": {"page": "0"}}, ["query", "page"]),
        ("records", {"params": {"page_size": "201"}}, ["query", "page_size"]),
    ],
)
def test_dashboard_routes_reject_invalid_input_without_calling_service(
    harness: tuple[TestClient, Mock],
    service_method: str,
    request_override: dict[str, Any],
    location: list[str],
) -> None:
    client, service = harness
    case = CASES_BY_METHOD[service_method]
    request = deepcopy(case.request)
    request.update(request_override)

    response = client.request(case.method, case.path, **request)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == location
    assert service.mock_calls == []
