from collections.abc import Iterator
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from router_contract_helpers import RouteCase

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
