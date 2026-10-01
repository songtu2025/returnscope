from collections.abc import Iterator
from copy import deepcopy
from dataclasses import replace
from typing import Any
from unittest.mock import Mock, call

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from test_dashboard_router_contract import RouteCase

from web_backend.dashboard_service import DashboardConflict, DashboardNotFound
from web_backend.insight_report_service import (
    InsightReportConflict,
    InsightReportNotFound,
    InsightReportService,
)
from web_backend.routers.insight_reports import create_insight_report_router

GENERATE_BODY = {"model_id": "model-1", "reasoning_effort": "high"}
RESULTS_BODY = {
    **GENERATE_BODY,
    "result_version_ids": ["result-1"],
    "plan_hash": "a" * 64,
}
ROUTE_CASES = (
    RouteCase(
        service_method="create_from_results",
        path="/api/ai-insight-reports/from-results",
        method="POST",
        request={"json": RESULTS_BODY},
        kwargs={**RESULTS_BODY, "filters": {}, "actor_id": "42"},
        status=201,
    ),
    RouteCase(
        service_method="create_for_dashboard",
        path="/api/analysis-dashboards/dashboard-1/versions/version-1/ai-insight-reports",
        method="POST",
        request={"json": GENERATE_BODY},
        args=("dashboard-1", "version-1"),
        kwargs={**GENERATE_BODY, "actor_id": "42"},
        status=201,
    ),
    RouteCase(
        service_method="list",
        path="/api/analysis-dashboards/dashboard-1/ai-insight-reports",
        request={"params": {"version_id": "version-1"}},
        args=("dashboard-1", "version-1"),
    ),
    RouteCase(
        service_method="get",
        path="/api/ai-insight-reports/report-1",
        args=("report-1",),
    ),
    RouteCase(
        service_method="retry",
        path="/api/ai-insight-reports/report-1/retry",
        method="POST",
        args=("report-1", "42"),
    ),
    RouteCase(
        service_method="set_issue_decision",
        path="/api/ai-insight-reports/report-1/issues/issue-1/decision",
        method="PUT",
        request={"json": {"status": "verify"}},
        args=("report-1", "issue-1", "verify", "42"),
    ),
)
CASES_BY_METHOD = {case.service_method: case for case in ROUTE_CASES}
FILTERS = {"listing": ["L1", "L2"], "subject": "PRODUCT", "date_to": None}
FILTER_CASE = replace(
    CASES_BY_METHOD["create_from_results"],
    request={"json": {**RESULTS_BODY, "filters": FILTERS}},
    kwargs={**RESULTS_BODY, "filters": FILTERS, "actor_id": "42"},
)
ERROR_STATUSES = {
    "create_from_results": (409, 400, 409, 400, 400, None),
    "create_for_dashboard": (400, 404, 409, 400, 400, None),
    "list": (None, 404, None, None, None, None),
    "get": (None, None, None, 404, None, None),
    "retry": (None, None, 409, 404, None, None),
    "set_issue_decision": (400, 400, 409, 404, 400, None),
}
ERROR_TYPES = (
    DashboardConflict,
    DashboardNotFound,
    InsightReportConflict,
    InsightReportNotFound,
    ValueError,
    RuntimeError,
)


def synthetic_user() -> dict[str, Any]:
    return {"id": 42}


@pytest.fixture
def harness() -> Iterator[tuple[TestClient, Mock]]:
    service = Mock(spec=InsightReportService)
    app = FastAPI()
    app.include_router(create_insight_report_router(service, synthetic_user))
    with TestClient(app) as client:
        yield client, service


@pytest.mark.parametrize(
    "case", (*ROUTE_CASES, FILTER_CASE), ids=lambda case: case.service_method
)
def test_insight_report_routes_preserve_responses_and_service_arguments(
    harness: tuple[TestClient, Mock], case: RouteCase
) -> None:
    client, service = harness
    payload = {"id": "synthetic-report", "version_no": None, "status": "queued"}
    expected = [payload] if case.service_method == "list" else payload
    getattr(service, case.service_method).return_value = expected
    response = client.request(case.method, case.path, **case.request)
    assert response.status_code == case.status
    assert response.json() == expected
    assert service.mock_calls == [
        getattr(call, case.service_method)(*case.args, **case.kwargs)
    ]


@pytest.mark.parametrize("case", ROUTE_CASES, ids=lambda case: case.service_method)
def test_all_insight_report_routes_require_login_before_calling_service(
    harness: tuple[TestClient, Mock], case: RouteCase
) -> None:
    client, service = harness

    def reject_user() -> dict[str, Any]:
        raise HTTPException(status_code=401, detail="请先登录")

    client.app.dependency_overrides[synthetic_user] = reject_user
    response = client.request(case.method, case.path, **case.request)
    assert response.status_code == 401
    assert response.json() == {"detail": "请先登录"}
    assert service.mock_calls == []


@pytest.mark.parametrize(
    ("case", "error_type", "status"),
    [
        (case, error_type, status)
        for case in ROUTE_CASES
        for error_type, status in zip(
            ERROR_TYPES, ERROR_STATUSES[case.service_method], strict=True
        )
    ],
)
def test_insight_report_routes_keep_exception_subclasses_and_capture_order(
    harness: tuple[TestClient, Mock],
    case: RouteCase,
    error_type: type[Exception],
    status: int | None,
) -> None:
    client, service = harness
    error = error_type("合成报告异常")
    getattr(service, case.service_method).side_effect = error
    if status is None:
        with pytest.raises(error_type) as raised:
            client.request(case.method, case.path, **case.request)
        assert raised.value is error
    else:
        response = client.request(case.method, case.path, **case.request)
        assert response.status_code == status
        assert response.json() == {"detail": "合成报告异常"}
    assert service.mock_calls == [
        getattr(call, case.service_method)(*case.args, **case.kwargs)
    ]


@pytest.mark.parametrize("status", ("pending", "ignored", "watching", "verify"))
def test_issue_decision_forwards_each_supported_status(
    harness: tuple[TestClient, Mock], status: str
) -> None:
    client, service = harness
    case = CASES_BY_METHOD["set_issue_decision"]
    service.set_issue_decision.return_value = {"status": status}
    response = client.put(case.path, json={"status": status})
    assert response.status_code == 200
    assert response.json() == {"status": status}
    assert service.mock_calls == [
        call.set_issue_decision("report-1", "issue-1", status, "42")
    ]


@pytest.mark.parametrize(
    "service_method",
    ("create_from_results", "create_for_dashboard", "set_issue_decision"),
)
def test_unknown_body_fields_are_not_forwarded_to_service(
    harness: tuple[TestClient, Mock], service_method: str
) -> None:
    client, service = harness
    case = CASES_BY_METHOD[service_method]
    payload = {**case.request["json"], "actor_id": "untrusted", "extra": "ignored"}
    getattr(service, service_method).return_value = {"id": "synthetic-report"}
    response = client.request(case.method, case.path, json=payload)
    assert response.status_code == case.status
    assert service.mock_calls == [
        getattr(call, service_method)(*case.args, **case.kwargs)
    ]


@pytest.mark.parametrize(
    ("service_method", "field", "value"),
    [
        ("create_from_results", "result_version_ids", []),
        ("create_from_results", "result_version_ids", ["r"] * 201),
        ("create_from_results", "plan_hash", "a" * 63),
        ("create_from_results", "plan_hash", "a" * 65),
        ("create_from_results", "model_id", ""),
        ("create_from_results", "reasoning_effort", ""),
        ("create_from_results", "filters", {"listing": 42}),
        ("create_for_dashboard", "model_id", ""),
        ("create_for_dashboard", "model_id", "m" * 121),
        ("create_for_dashboard", "reasoning_effort", ""),
        ("create_for_dashboard", "reasoning_effort", "h" * 21),
        ("set_issue_decision", "status", "unsupported"),
        ("set_issue_decision", "status", None),
    ],
)
def test_invalid_report_body_fields_are_rejected_before_calling_service(
    harness: tuple[TestClient, Mock], service_method: str, field: str, value: Any
) -> None:
    client, service = harness
    case = CASES_BY_METHOD[service_method]
    payload = deepcopy(case.request["json"])
    payload[field] = value
    response = client.request(case.method, case.path, json=payload)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][:2] == ["body", field]
    assert service.mock_calls == []


@pytest.mark.parametrize(
    "service_method",
    ("create_from_results", "create_for_dashboard", "set_issue_decision"),
)
@pytest.mark.parametrize(
    "request_options", ({}, {"json": {}}), ids=("missing-body", "empty-body")
)
def test_missing_report_body_is_rejected_before_calling_service(
    harness: tuple[TestClient, Mock],
    service_method: str,
    request_options: dict[str, Any],
) -> None:
    client, service = harness
    case = CASES_BY_METHOD[service_method]
    response = client.request(case.method, case.path, **request_options)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][0] == "body"
    assert service.mock_calls == []


@pytest.mark.parametrize("params", ({}, {"version_id": ""}))
def test_report_list_requires_nonempty_version_id(
    harness: tuple[TestClient, Mock], params: dict[str, str]
) -> None:
    client, service = harness
    response = client.get(CASES_BY_METHOD["list"].path, params=params)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["query", "version_id"]
    assert service.mock_calls == []
