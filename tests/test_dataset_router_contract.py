from collections.abc import Iterator
from copy import deepcopy
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, call

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from test_dashboard_router_contract import RouteCase

from web_backend.api_contracts.datasets import MySQLReturnImportRequest
from web_backend.dataset_service import DatasetRevisionConflict, DatasetService
from web_backend.mysql_return_service import MySQLReturnService, MySQLSourceError
from web_backend.routers.datasets import create_dataset_router

MYSQL_BODY = {"mapping": {"comment": "feedback"}}
IMPORT_BODY = {"inspection_id": "inspection-1", "mode": "new"}
UPDATE_BODY = {
    "row_index": 0,
    "expected_version": 3,
    "changes": {"product_name": "合成商品"},
    "change_note": "验证修改",
}
COMPLETION_ITEM = {
    "msku": "SKU-1",
    "listing": "L1",
    "category_a": "眼镜",
    "category_b": "太阳镜",
}
COMPLETION_BODY = {
    "expected_version": 3,
    "items": [COMPLETION_ITEM],
    "change_note": "验证品类补全",
}
MYSQL_METHODS = {"schema", "preview", "import_returns"}
ROUTE_CASES = (
    RouteCase(
        service_method="schema",
        path="/api/mysql-return-imports/schema",
        kwargs={"refresh": False},
    ),
    RouteCase(
        service_method="preview",
        path="/api/mysql-return-imports/preview",
        method="POST",
        request={"json": MYSQL_BODY},
        args=(MySQLReturnImportRequest(**MYSQL_BODY),),
    ),
    RouteCase(
        service_method="import_returns",
        path="/api/mysql-return-imports",
        method="POST",
        request={"json": MYSQL_BODY},
        args=(MySQLReturnImportRequest(**MYSQL_BODY), "42"),
        status=201,
    ),
    RouteCase(service_method="list", path="/api/datasets", args=(None, None)),
    RouteCase(service_method="list_versions", path="/api/data-versions", args=(None,)),
    RouteCase(
        service_method="references",
        path="/api/data-versions/version-1/references",
        args=("version-1",),
        kwargs={"page": 1, "page_size": 50},
    ),
    RouteCase(
        service_method="product_scopes",
        path="/api/data-versions/version-1/scopes",
        args=("version-1",),
    ),
    RouteCase(
        service_method="storage_summary",
        path="/api/dataset-storage",
        request={"params": {"dataset_ids": "dataset-1,dataset-2"}},
        kwargs={
            "dataset_ids": ["dataset-1", "dataset-2"],
            "retention_days": 30,
            "retain_latest": 2,
        },
    ),
    RouteCase(
        service_method="cleanup_storage",
        path="/api/dataset-storage/cleanup",
        method="POST",
        request={"json": {"dataset_ids": ["dataset-1"]}},
        kwargs={
            "dataset_ids": ["dataset-1"],
            "retention_days": 30,
            "retain_latest": 2,
            "actor_id": "42",
        },
    ),
    RouteCase(
        service_method="import_staged_returns",
        path="/api/return-imports",
        method="POST",
        request={"json": IMPORT_BODY},
        kwargs={
            **IMPORT_BODY,
            "dataset_id": "",
            "name": "",
            "change_note": "",
            "actor_id": "42",
        },
        status=201,
    ),
    RouteCase(
        service_method="get", path="/api/datasets/dataset-1", args=("dataset-1", None)
    ),
    RouteCase(
        service_method="preview_rows",
        path="/api/datasets/dataset-1/rows",
        kwargs={
            "dataset_id": "dataset-1",
            "offset": 0,
            "limit": 50,
            "query": "",
            "store": "",
            "category": "",
            "version": None,
        },
    ),
    RouteCase(
        service_method="update_product_row",
        path="/api/datasets/dataset-1/rows",
        method="PATCH",
        request={"json": UPDATE_BODY},
        kwargs={**UPDATE_BODY, "dataset_id": "dataset-1", "actor_id": "42"},
    ),
    RouteCase(
        service_method="complete_product_categories",
        path="/api/datasets/dataset-1/category-completion",
        method="POST",
        request={"json": COMPLETION_BODY},
        kwargs={
            **COMPLETION_BODY,
            "items": [{**COMPLETION_ITEM, "store": "", "product_name": ""}],
            "store": "",
            "dataset_id": "dataset-1",
            "actor_id": "42",
        },
    ),
)
CASES_BY_METHOD = {case.service_method: case for case in ROUTE_CASES}
ERROR_STATUSES = {
    "schema": (None, None, 503, None),
    "preview": (400, 400, 503, None),
    "import_returns": (400, 400, 503, None),
    "list": (None, None, None, None),
    "list_versions": (None, None, None, None),
    "references": (404, 404, 404, None),
    "product_scopes": (400, 400, 400, None),
    "storage_summary": (400, 400, 400, None),
    "cleanup_storage": (400, 400, 400, None),
    "import_staged_returns": (400, 400, 400, None),
    "get": (None, None, None, None),
    "preview_rows": (400, 400, 400, None),
    "update_product_row": (400, 409, 400, None),
    "complete_product_categories": (400, 409, 400, None),
}


def synthetic_user() -> dict[str, Any]:
    return {"id": 42, "is_admin": True}


@pytest.fixture
def harness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[SimpleNamespace]:
    service = Mock(spec=DatasetService)
    mysql = Mock(spec=MySQLReturnService)
    constructor = Mock(return_value=mysql)
    monkeypatch.setattr("web_backend.routers.datasets.MySQLReturnService", constructor)
    settings = SimpleNamespace(data_dir=tmp_path)
    app = FastAPI()
    app.include_router(create_dataset_router(service, settings, synthetic_user))
    constructor.assert_called_once_with(service, settings)
    with TestClient(app) as client:
        yield SimpleNamespace(
            client=client, service=service, mysql=mysql, settings=settings
        )


@pytest.mark.parametrize("case", ROUTE_CASES, ids=lambda case: case.service_method)
def test_dataset_routes_preserve_responses_and_default_arguments(
    harness: SimpleNamespace, case: RouteCase
) -> None:
    target = harness.mysql if case.service_method in MYSQL_METHODS else harness.service
    payload = {"id": "synthetic-dataset", "version": 3}
    expected = (
        [payload]
        if case.service_method in {"list", "list_versions", "product_scopes"}
        else payload
    )
    getattr(target, case.service_method).return_value = expected
    response = harness.client.request(case.method, case.path, **case.request)
    assert response.status_code == case.status
    assert response.json() == expected
    assert target.mock_calls == [
        getattr(call, case.service_method)(*case.args, **case.kwargs)
    ]
    other = harness.service if target is harness.mysql else harness.mysql
    assert other.mock_calls == []


@pytest.mark.parametrize("case", ROUTE_CASES, ids=lambda case: case.service_method)
def test_dataset_routes_require_login_before_calling_services(
    harness: SimpleNamespace, case: RouteCase
) -> None:
    def reject_user() -> dict[str, Any]:
        raise HTTPException(status_code=401, detail="请先登录")

    harness.client.app.dependency_overrides[synthetic_user] = reject_user
    response = harness.client.request(case.method, case.path, **case.request)
    assert response.status_code == 401
    assert response.json() == {"detail": "请先登录"}
    assert harness.service.mock_calls == harness.mysql.mock_calls == []


@pytest.mark.parametrize(
    ("case", "error_type", "status"),
    [
        (case, error_type, status)
        for case in ROUTE_CASES
        for error_type, status in zip(
            (ValueError, DatasetRevisionConflict, MySQLSourceError, RuntimeError),
            ERROR_STATUSES[case.service_method],
            strict=True,
        )
    ],
)
def test_dataset_routes_preserve_exception_mapping(
    harness: SimpleNamespace,
    case: RouteCase,
    error_type: type[Exception],
    status: int | None,
) -> None:
    target = harness.mysql if case.service_method in MYSQL_METHODS else harness.service
    error = error_type("合成数据集异常")
    getattr(target, case.service_method).side_effect = error
    if status is None:
        with pytest.raises(error_type) as raised:
            harness.client.request(case.method, case.path, **case.request)
        assert raised.value is error
    else:
        response = harness.client.request(case.method, case.path, **case.request)
        assert response.status_code == status
        assert response.json() == {"detail": "合成数据集异常"}
    assert target.mock_calls == [
        getattr(call, case.service_method)(*case.args, **case.kwargs)
    ]


@pytest.mark.parametrize("user", ({"id": 42}, {"id": 42, "is_admin": False}))
def test_storage_cleanup_requires_admin_before_any_write(
    harness: SimpleNamespace, user: dict[str, Any]
) -> None:
    harness.client.app.dependency_overrides[synthetic_user] = lambda: user
    case = CASES_BY_METHOD["cleanup_storage"]
    response = harness.client.post(case.path, **case.request)
    assert response.status_code == 403
    assert response.json() == {"detail": "仅系统管理员可清理快照存储"}
    assert harness.service.mock_calls == harness.mysql.mock_calls == []


@pytest.mark.parametrize(
    ("include", "expected"),
    [
        (None, None),
        ("", set()),
        ("versions", {"versions"}),
        (" versions, audit,versions, ", {"versions", "audit"}),
        ("imports,audit,versions", {"imports", "audit", "versions"}),
    ],
)
def test_dataset_include_is_parsed_without_changing_supported_fields(
    harness: SimpleNamespace, include: str | None, expected: set[str] | None
) -> None:
    harness.service.get.return_value = {}
    response = harness.client.get(
        CASES_BY_METHOD["get"].path,
        params={} if include is None else {"include": include},
    )
    assert response.status_code == 200
    assert response.json() == {}
    assert harness.service.mock_calls == [call.get("dataset-1", expected)]


def test_missing_dataset_returns_404(harness: SimpleNamespace) -> None:
    harness.service.get.return_value = None
    response = harness.client.get(CASES_BY_METHOD["get"].path)
    assert response.status_code == 404
    assert response.json() == {"detail": "数据集不存在"}


@pytest.mark.parametrize(
    ("service_method", "params", "args", "kwargs"),
    [
        ("schema", {"refresh": "true"}, (), {"refresh": True}),
        (
            "list",
            {"kind": "returns", "usage_scope": "shared"},
            ("returns", "shared"),
            {},
        ),
        ("list_versions", {"kind": "products"}, ("products",), {}),
        (
            "references",
            {"page": 3, "page_size": 200},
            ("version-1",),
            {"page": 3, "page_size": 200},
        ),
        (
            "storage_summary",
            {
                "dataset_ids": "dataset-1, dataset-2,",
                "retention_days": 7,
                "retain_latest": 1,
            },
            (),
            {
                "dataset_ids": ["dataset-1", " dataset-2", ""],
                "retention_days": 7,
                "retain_latest": 1,
            },
        ),
        (
            "preview_rows",
            {
                "offset": 5,
                "limit": 100,
                "q": "合成",
                "store": "S1",
                "category": "眼镜",
                "version": 2,
            },
            (),
            {
                "dataset_id": "dataset-1",
                "offset": 5,
                "limit": 100,
                "query": "合成",
                "store": "S1",
                "category": "眼镜",
                "version": 2,
            },
        ),
    ],
)
def test_dataset_query_filters_are_forwarded(
    harness: SimpleNamespace,
    service_method: str,
    params: dict[str, Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> None:
    case = CASES_BY_METHOD[service_method]
    target = harness.mysql if service_method in MYSQL_METHODS else harness.service
    getattr(target, service_method).return_value = (
        [] if service_method in {"list", "list_versions"} else {}
    )
    response = harness.client.get(case.path, params=params)
    assert response.status_code == 200
    assert target.mock_calls == [getattr(call, service_method)(*args, **kwargs)]


def test_mysql_payload_keeps_dates_and_optional_filters(
    harness: SimpleNamespace,
) -> None:
    payload = {
        **MYSQL_BODY,
        "date_from": "2026-10-01",
        "date_to": "2026-10-02",
        "store": "S1",
        "sku": "SKU-1",
        "default_store": "S2",
    }
    harness.mysql.preview.return_value = {}
    response = harness.client.post(CASES_BY_METHOD["preview"].path, json=payload)
    assert response.status_code == 200
    forwarded = harness.mysql.preview.call_args.args[0]
    assert forwarded == MySQLReturnImportRequest(**payload)
    assert forwarded.date_from == date(2026, 10, 1)
    assert forwarded.date_to == date(2026, 10, 2)


@pytest.mark.parametrize(
    ("service_method", "override", "status"),
    [
        ("schema", {"refresh": "invalid"}, 422),
        ("references", {"page": 0}, 422),
        ("references", {"page_size": 201}, 422),
        ("storage_summary", {"dataset_ids": ""}, 422),
        ("storage_summary", {"retention_days": 6}, 422),
        ("storage_summary", {"retention_days": 3651}, 422),
        ("storage_summary", {"retain_latest": 0}, 422),
        ("storage_summary", {"retain_latest": 51}, 422),
        ("get", {"include": "unsupported"}, 400),
        ("get", {"include": "x" * 101}, 422),
        ("preview_rows", {"offset": -1}, 422),
        ("preview_rows", {"limit": 101}, 422),
        ("preview_rows", {"q": "x" * 101}, 422),
        ("preview_rows", {"category": "x" * 201}, 422),
        ("preview_rows", {"version": 0}, 422),
    ],
)
def test_invalid_dataset_queries_do_not_call_services(
    harness: SimpleNamespace, service_method: str, override: dict[str, Any], status: int
) -> None:
    case = CASES_BY_METHOD[service_method]
    params = {**case.request.get("params", {}), **override}
    response = harness.client.get(case.path, params=params)
    assert response.status_code == status
    assert harness.service.mock_calls == harness.mysql.mock_calls == []


@pytest.mark.parametrize(
    ("service_method", "override"),
    [
        ("preview", {"mapping": {str(i): "column" for i in range(11)}}),
        ("import_returns", {"date_from": "invalid"}),
        ("cleanup_storage", {"dataset_ids": []}),
        ("cleanup_storage", {"retention_days": 6}),
        ("import_staged_returns", {"inspection_id": ""}),
        ("update_product_row", {"row_index": -1}),
        ("update_product_row", {"expected_version": 0}),
        ("update_product_row", {"change_note": ""}),
        ("complete_product_categories", {"items": []}),
        ("complete_product_categories", {"expected_version": 0}),
    ],
)
def test_invalid_dataset_bodies_do_not_call_services(
    harness: SimpleNamespace, service_method: str, override: dict[str, Any]
) -> None:
    case = CASES_BY_METHOD[service_method]
    payload = deepcopy(case.request["json"])
    payload.update(override)
    response = harness.client.request(case.method, case.path, json=payload)
    assert response.status_code == 422
    assert harness.service.mock_calls == harness.mysql.mock_calls == []
