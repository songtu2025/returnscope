from copy import deepcopy
from datetime import date
from types import SimpleNamespace
from typing import Any
from unittest.mock import call

import pytest
from dataset_router_helpers import (
    CASES_BY_METHOD,
    ERROR_STATUSES,
    MYSQL_BODY,
    MYSQL_METHODS,
    ROUTE_CASES,
    synthetic_user,
)
from dataset_router_helpers import harness as harness
from fastapi import HTTPException
from router_contract_helpers import RouteCase

from web_backend.api_contracts.datasets import MySQLReturnImportRequest
from web_backend.dataset_service import DatasetRevisionConflict
from web_backend.mysql_return_service import MySQLSourceError


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
        ("import_staged_returns", {"inspection_id": ""}),
        ("update_product_row", {"row_index": -1}),
        ("update_product_row", {"expected_version": 0}),
        ("update_product_row", {"change_note": "x" * 501}),
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


@pytest.mark.parametrize(
    "path", ["/api/dataset-storage", "/api/dataset-storage/cleanup"]
)
def test_retired_storage_routes_are_unavailable(
    harness: SimpleNamespace, path: str
) -> None:
    response = harness.client.request(
        "GET" if path.endswith("storage") else "POST", path
    )
    assert response.status_code == 404
    assert harness.service.mock_calls == []


def test_generic_upload_rejects_feedback_without_saving_file(
    harness: SimpleNamespace,
) -> None:
    response = harness.client.post(
        "/api/datasets",
        data={"name": "合成源", "kind": "returns"},
        files={"file": ("synthetic.csv", b"synthetic", "text/csv")},
    )
    assert response.status_code == 400
    assert harness.service.mock_calls == []
    assert not (harness.settings.data_dir / "tmp").exists()


def test_version_upload_rejects_feedback_without_saving_file(
    harness: SimpleNamespace,
) -> None:
    harness.service.get.return_value = {"kind": "returns"}
    response = harness.client.put(
        "/api/datasets/source/content",
        data={"change_note": "合成变更", "expected_version": "1"},
        files={"file": ("synthetic.csv", b"synthetic", "text/csv")},
    )
    assert response.status_code == 400
    harness.service.add_version.assert_not_called()
    assert not (harness.settings.data_dir / "tmp").exists()
