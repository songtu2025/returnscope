from collections.abc import Iterator
from dataclasses import replace
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from test_dashboard_router_contract import RouteCase

from web_backend.data_quality_service import DataQualityService
from web_backend.operations_service import AuditLogService, WorkbenchService
from web_backend.routers import operations

VERSION_PARAMS = {
    "returns_version_id": "returns-1",
    "products_version_id": "products-1",
}
ISSUE_DEFAULTS = {"issue_type": None, "q": None, "page": 1, "page_size": 50}
AUDIT_DEFAULTS = {
    "actor_id": None,
    "entity_type": None,
    "entity_id": None,
    "action": None,
    "date_from": None,
    "date_to": None,
    "page": 1,
    "page_size": 50,
}
ROUTE_CASES = (
    RouteCase(service_method="summary", path="/api/workbench/summary", args=(5,)),
    RouteCase(service_method="list_import_rules", path="/api/import-rules"),
    RouteCase(
        service_method="preflight",
        path="/api/data-quality/preflight",
        request={"params": VERSION_PARAMS},
        args=("returns-1", "products-1"),
    ),
    RouteCase(
        service_method="issues",
        path="/api/data-quality/issues",
        request={"params": VERSION_PARAMS},
        args=("returns-1", "products-1"),
        kwargs=ISSUE_DEFAULTS,
    ),
    RouteCase(service_method="list", path="/api/audit-logs", kwargs=AUDIT_DEFAULTS),
)
ISSUE_FILTERS = {
    "issue_type": "missing_product",
    "q": " 查询 ",
    "page": 3,
    "page_size": 200,
}
AUDIT_FILTERS = {
    "actor_id": "another-user",
    "entity_type": "task",
    "entity_id": "task-1",
    "action": "pause",
    "date_from": "2026-09-01",
    "date_to": "2026-09-30T23:59:59+08:00",
    "page": 2,
    "page_size": 200,
}
CUSTOM_CASES = (
    replace(ROUTE_CASES[0], request={"params": {"limit": 20}}, args=(20,)),
    replace(
        ROUTE_CASES[3],
        request={"params": {**VERSION_PARAMS, **ISSUE_FILTERS}},
        kwargs=ISSUE_FILTERS,
    ),
    replace(ROUTE_CASES[4], request={"params": AUDIT_FILTERS}, kwargs=AUDIT_FILTERS),
)


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch) -> Iterator[SimpleNamespace]:
    workbench = Mock(spec=WorkbenchService)
    quality = Mock(spec=DataQualityService)
    audit = Mock(spec=AuditLogService)
    import_rules = Mock()
    methods = {
        "summary": workbench.summary,
        "list_import_rules": import_rules,
        "preflight": quality.preflight,
        "issues": quality.issues,
        "list": audit.list,
    }
    result = {"items": [{"id": "synthetic", "name": "合成结果"}], "total": 1}
    for method in methods.values():
        method.return_value = result
    monkeypatch.setattr(operations, "list_import_rules", import_rules)
    auth = {"logged_in": True, "user": {"id": "42", "is_admin": True}}

    def current_user() -> dict[str, Any]:
        if not auth["logged_in"]:
            raise HTTPException(status_code=401, detail="请先登录")
        return auth["user"]

    router = operations.create_operations_router(
        workbench, quality, audit, current_user
    )
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        yield SimpleNamespace(
            app=app,
            router=router,
            client=client,
            methods=methods,
            result=result,
            auth=auth,
        )


@pytest.mark.parametrize(
    "case", ROUTE_CASES + CUSTOM_CASES, ids=lambda case: case.service_method
)
def test_query_defaults_filters_and_results_are_preserved(
    harness, case: RouteCase
) -> None:
    response = harness.client.get(case.path, **case.request)
    assert response.status_code == 200
    assert response.json() == harness.result
    harness.methods[case.service_method].assert_called_once_with(
        *case.args, **case.kwargs
    )
    for name, method in harness.methods.items():
        if name != case.service_method:
            method.assert_not_called()


@pytest.mark.parametrize("case", ROUTE_CASES, ids=lambda case: case.service_method)
def test_all_routes_require_login_before_service_calls(
    harness, case: RouteCase
) -> None:
    harness.auth["logged_in"] = False
    response = harness.client.get(case.path, **case.request)
    assert response.status_code == 401
    assert response.json() == {"detail": "请先登录"}
    for method in harness.methods.values():
        method.assert_not_called()


@pytest.mark.parametrize("case", ROUTE_CASES[:-1], ids=lambda case: case.service_method)
def test_member_can_read_workbench_rules_and_quality(harness, case: RouteCase) -> None:
    harness.auth["user"]["is_admin"] = False
    response = harness.client.get(case.path, **case.request)
    assert response.status_code == 200
    assert response.json() == harness.result
    harness.methods[case.service_method].assert_called_once_with(
        *case.args, **case.kwargs
    )


@pytest.mark.parametrize("admin_value", [False, None, 0, "missing"])
def test_audit_requires_admin_before_querying_service(harness, admin_value) -> None:
    harness.auth["user"] = {"id": "42"}
    if admin_value != "missing":
        harness.auth["user"]["is_admin"] = admin_value
    response = harness.client.get("/api/audit-logs", params=AUDIT_FILTERS)
    assert response.status_code == 403
    assert response.json() == {"detail": "仅系统管理员可查看审计日志"}
    harness.methods["list"].assert_not_called()


@pytest.mark.parametrize("case", ROUTE_CASES[2:], ids=lambda case: case.service_method)
def test_quality_and_audit_value_errors_become_bad_requests(
    harness, case: RouteCase
) -> None:
    harness.methods[case.service_method].side_effect = ValueError("合成业务校验错误")
    response = harness.client.get(case.path, **case.request)
    assert response.status_code == 400
    assert response.json() == {"detail": "合成业务校验错误"}
    harness.methods[case.service_method].assert_called_once_with(
        *case.args, **case.kwargs
    )


@pytest.mark.parametrize("case", ROUTE_CASES, ids=lambda case: case.service_method)
def test_unexpected_service_errors_are_not_hidden(harness, case: RouteCase) -> None:
    error = RuntimeError("合成内部错误")
    harness.methods[case.service_method].side_effect = error
    with pytest.raises(RuntimeError) as caught:
        harness.client.get(case.path, **case.request)
    assert caught.value is error


@pytest.mark.parametrize("case", ROUTE_CASES[:2], ids=lambda case: case.service_method)
def test_workbench_and_rules_keep_unmapped_value_errors(
    harness, case: RouteCase
) -> None:
    error = ValueError("合成内部校验错误")
    harness.methods[case.service_method].side_effect = error
    with pytest.raises(ValueError) as caught:
        harness.client.get(case.path, **case.request)
    assert caught.value is error


@pytest.mark.parametrize(
    "path,params",
    [
        ("/api/workbench/summary", {"limit": 0}),
        ("/api/workbench/summary", {"limit": 21}),
        ("/api/workbench/summary", {"limit": "invalid"}),
        ("/api/data-quality/preflight", {"returns_version_id": "returns-1"}),
        ("/api/data-quality/preflight", {"products_version_id": "products-1"}),
        ("/api/data-quality/preflight", {**VERSION_PARAMS, "returns_version_id": ""}),
        ("/api/data-quality/preflight", {**VERSION_PARAMS, "products_version_id": ""}),
        ("/api/data-quality/issues", {}),
        ("/api/data-quality/issues", {**VERSION_PARAMS, "returns_version_id": ""}),
        ("/api/data-quality/issues", {**VERSION_PARAMS, "products_version_id": ""}),
        ("/api/data-quality/issues", {**VERSION_PARAMS, "page": 0}),
        ("/api/data-quality/issues", {**VERSION_PARAMS, "page": "invalid"}),
        ("/api/data-quality/issues", {**VERSION_PARAMS, "page_size": 0}),
        ("/api/data-quality/issues", {**VERSION_PARAMS, "page_size": 201}),
        ("/api/data-quality/issues", {**VERSION_PARAMS, "q": "a" * 101}),
        ("/api/audit-logs", {"page": 0}),
        ("/api/audit-logs", {"page_size": 0}),
        ("/api/audit-logs", {"page_size": 201}),
    ],
)
def test_invalid_queries_are_rejected_before_service_calls(
    harness, path, params
) -> None:
    response = harness.client.get(path, params=params)
    assert response.status_code == 422
    for method in harness.methods.values():
        method.assert_not_called()
