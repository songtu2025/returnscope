from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator
from unittest.mock import Mock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from test_classification_result_openapi import _bind_result_standard
from test_classification_result_pool import _publish, _seed_result_context

from web_backend.classification_result_service import (
    ClassificationResultNotFound,
    ClassificationResultService,
)
from web_backend.classification_standard_service import (
    ClassificationStandardNotFound,
    ClassificationStandardService,
)
from web_backend.routers.classification_results import (
    XLSX_MEDIA_TYPE,
    create_classification_result_router,
)

ROUTES = [
    ("", "list_results", "list", "page,page_size,q,store_site,listing,quality_status"),
    ("/{version_id}", "get_result", "get", "version_id"),
    ("/{version_id}/versions", "get_result_versions", "history", "version_id"),
    (
        "/{version_id}/taxonomy",
        "get_result_taxonomy",
        "taxonomy_for_result_version",
        "version_id",
    ),
    ("/{version_id}/summary", "get_summary", "summary", "version_id"),
    (
        "/{version_id}/records",
        "list_records",
        "records",
        "version_id,page,page_size,order_id,listing,product_name,source_sku,matched_msku,product_sku,asin,problem,quality_status,comment_status",
    ),
    (
        "/{version_id}/record-groups",
        "list_record_groups",
        "record_groups",
        "version_id,page,page_size,order_id,listing,product_name,source_sku,matched_msku,product_sku,asin,problem,quality_status,comment_status",
    ),
    (
        "/{version_id}/drilldown",
        "get_drilldown",
        "drilldown",
        "version_id,group_by,page,page_size,problem,product_name,product_sku,order_id",
    ),
    ("/{version_id}/download", "download_result", "download", "version_id"),
]
BASE_PATH = "/api/classification-results"


@pytest.fixture
def harness(tmp_path: Path) -> Iterator[SimpleNamespace]:
    # 复用现有合成结果，避免另造业务数据和响应模型。
    context = _seed_result_context(tmp_path)
    published = _publish(context)
    service = ClassificationResultService(context.database)
    standards = ClassificationStandardService(context.database)
    _bind_result_standard(
        standards, str(published["result_id"]), context.taxonomy.version
    )
    result_mock = Mock(spec=ClassificationResultService, wraps=service)
    result_mock.database = context.database
    standard_mock = Mock(spec=ClassificationStandardService, wraps=standards)

    def current_user() -> dict[str, str]:
        return {"id": "another-user", "role": "user"}

    router = create_classification_result_router(
        result_mock, current_user, standard_mock
    )
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        yield SimpleNamespace(
            client=client,
            app=app,
            router=router,
            current_user=current_user,
            service=service,
            standards=standards,
            result_mock=result_mock,
            standard_mock=standard_mock,
            version_id=str(published["version_id"]),
        )


def _path(harness: SimpleNamespace, suffix: str) -> str:
    return BASE_PATH + suffix.replace("{version_id}", harness.version_id)


def test_result_router_preserves_registration_and_response_settings(
    harness: SimpleNamespace,
) -> None:
    routes = [route for route in harness.router.routes if isinstance(route, APIRoute)]
    actual = [
        (
            route.path.removeprefix(BASE_PATH),
            route.name,
            ",".join(inspect.signature(route.endpoint).parameters),
        )
        for route in routes
    ]
    assert actual == [
        (suffix, name, parameters) for suffix, name, _, parameters in ROUTES
    ]
    assert all(route.methods == {"GET"} for route in routes)
    assert all((route.status_code or 200) == 200 for route in routes)
    assert all(
        route.dependant.dependencies[0].call is harness.current_user for route in routes
    )
    assert all(not inspect.iscoroutinefunction(route.endpoint) for route in routes)
    assert all(
        route.response_model is not None and route.response_model_exclude_unset
        for route in routes[:-1]
    )
    assert routes[-1].responses == {200: {"content": {XLSX_MEDIA_TYPE: {}}}}


@pytest.mark.parametrize(("suffix", "name", "method", "parameters"), ROUTES)
def test_all_result_routes_require_login(
    harness: SimpleNamespace,
    suffix: str,
    name: str,
    method: str,
    parameters: str,
) -> None:
    def deny_user() -> dict[str, str]:
        raise HTTPException(status_code=401, detail="请先登录")

    harness.app.dependency_overrides[harness.current_user] = deny_user
    response = harness.client.get(
        _path(harness, suffix), params={"group_by": "problem"}
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "请先登录"}
    assert not harness.result_mock.mock_calls
    assert not harness.standard_mock.mock_calls


@pytest.mark.parametrize(("suffix", "name", "method", "parameters"), ROUTES[:-1])
def test_ordinary_user_reads_preserve_complete_service_json(
    harness: SimpleNamespace,
    suffix: str,
    name: str,
    method: str,
    parameters: str,
) -> None:
    if method == "list":
        expected = harness.service.list()
    elif method == "taxonomy_for_result_version":
        expected = harness.standards.taxonomy_for_result_version(harness.version_id)
    elif method == "drilldown":
        expected = harness.service.drilldown(harness.version_id, "problem")
    else:
        expected = getattr(harness.service, method)(harness.version_id)
    response = harness.client.get(
        _path(harness, suffix), params={"group_by": "problem"}
    )
    assert response.status_code == 200, response.text
    assert response.json() == expected


@pytest.mark.parametrize(
    ("suffix", "method"),
    [
        ("", "list"),
        ("/{version_id}/records", "records"),
        ("/{version_id}/record-groups", "record_groups"),
        ("/{version_id}/drilldown", "drilldown"),
    ],
)
def test_invalid_service_queries_keep_bad_request_response(
    harness: SimpleNamespace,
    suffix: str,
    method: str,
) -> None:
    getattr(harness.result_mock, method).side_effect = ValueError("合成筛选错误")
    response = harness.client.get(
        _path(harness, suffix), params={"group_by": "problem"}
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "合成筛选错误"}


@pytest.mark.parametrize(("suffix", "name", "method", "parameters"), ROUTES[1:])
def test_missing_results_and_taxonomy_keep_not_found_response(
    harness: SimpleNamespace,
    suffix: str,
    name: str,
    method: str,
    parameters: str,
) -> None:
    if method == "taxonomy_for_result_version":
        harness.standard_mock.taxonomy_for_result_version.side_effect = (
            ClassificationStandardNotFound("合成标准不存在")
        )
        message = "合成标准不存在"
    else:
        getattr(harness.result_mock, method).side_effect = ClassificationResultNotFound(
            "合成结果不存在"
        )
        message = "合成结果不存在"
    response = harness.client.get(
        _path(harness, suffix), params={"group_by": "problem"}
    )
    assert response.status_code == 404
    assert response.json() == {"detail": message}


@pytest.mark.parametrize(
    ("suffix", "method"),
    [
        ("/{version_id}/records", "records"),
        ("/{version_id}/record-groups", "record_groups"),
    ],
)
def test_record_filters_are_forwarded_without_loss(
    harness: SimpleNamespace,
    suffix: str,
    method: str,
) -> None:
    filters = {
        "page": 2,
        "page_size": 10,
        "order_id": "ORDER-OTHER",
        "listing": "L1",
        "product_name": "权威",
        "source_sku": "SOURCE-MSKU-1",
        "matched_msku": "SOURCE-MSKU-1",
        "product_sku": "PRODUCT-SKU-1",
        "asin": "ASIN-1",
        "problem": "FIT_TOO_SMALL_U1",
        "quality_status": "ready",
        "comment_status": "NEGATIVE",
    }
    response = harness.client.get(_path(harness, suffix), params=filters)
    assert response.status_code == 200, response.text
    getattr(harness.result_mock, method).assert_called_once_with(
        harness.version_id, **filters
    )
    assert response.json() == getattr(harness.service, method)(
        harness.version_id, **filters
    )


def test_result_list_filters_are_forwarded_without_loss(
    harness: SimpleNamespace,
) -> None:
    filters = {
        "page": 2,
        "page_size": 10,
        "q": "权威",
        "store_site": "SEEKWAY:US",
        "listing": "L1",
        "quality_status": "ready",
    }
    response = harness.client.get(BASE_PATH, params=filters)
    assert response.status_code == 200, response.text
    harness.result_mock.list.assert_called_once_with(**filters)
    assert response.json() == harness.service.list(**filters)


def test_drilldown_filters_are_forwarded_without_loss(harness: SimpleNamespace) -> None:
    filters = {
        "page": 2,
        "page_size": 10,
        "problem": "FIT_TOO_SMALL_U1",
        "product_name": "权威",
        "product_sku": "PRODUCT-SKU-1",
        "order_id": "ORDER-OTHER",
    }
    response = harness.client.get(
        _path(harness, "/{version_id}/drilldown"),
        params={"group_by": "category", **filters},
    )
    assert response.status_code == 200, response.text
    harness.result_mock.drilldown.assert_called_once_with(
        harness.version_id, "category", **filters
    )
    assert response.json() == harness.service.drilldown(
        harness.version_id, "category", **filters
    )


@pytest.mark.parametrize(
    "suffix",
    [
        "",
        "/{version_id}/records",
        "/{version_id}/record-groups",
        "/{version_id}/drilldown",
    ],
)
@pytest.mark.parametrize("invalid", [{"page": 0}, {"page_size": 201}])
def test_pagination_bounds_are_validated_before_service_calls(
    harness: SimpleNamespace,
    suffix: str,
    invalid: dict[str, int],
) -> None:
    response = harness.client.get(
        _path(harness, suffix), params={"group_by": "problem", **invalid}
    )
    assert response.status_code == 422
    assert not harness.result_mock.mock_calls


def test_drilldown_still_requires_group_by(harness: SimpleNamespace) -> None:
    response = harness.client.get(_path(harness, "/{version_id}/drilldown"))
    assert response.status_code == 422
    assert not harness.result_mock.mock_calls


def test_response_preserves_extra_fields_null_and_unset_distinction(
    harness: SimpleNamespace,
) -> None:
    payload = harness.service.records(harness.version_id)
    payload["extension"] = {"合成字段": True}
    payload["items"][0]["extension"] = None
    # 缺失字段不能被响应模型补成默认值，显式空值仍须保留。
    payload["items"][0].pop("source_origin_id", None)
    harness.result_mock.records.return_value = payload
    response = harness.client.get(_path(harness, "/{version_id}/records"))
    assert response.status_code == 200
    assert response.json() == payload


def test_download_keeps_ordinary_access_bytes_and_headers(
    harness: SimpleNamespace,
) -> None:
    harness.result_mock.download.return_value = (
        b"synthetic-export",
        "analysis-v1.xlsx",
    )
    response = harness.client.get(_path(harness, "/{version_id}/download"))
    assert response.status_code == 200
    assert response.content == b"synthetic-export"
    assert response.headers["content-type"] == XLSX_MEDIA_TYPE
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="analysis-v1.xlsx"'
    )
    harness.result_mock.download.assert_called_once_with(harness.version_id)


@pytest.mark.parametrize("mode", ["omitted", "none", "injected"])
def test_standard_service_injection_and_default_remain_compatible(
    harness: SimpleNamespace,
    mode: str,
) -> None:
    arguments = (harness.service, harness.current_user)
    if mode == "omitted":
        router = create_classification_result_router(*arguments)
    else:
        router = create_classification_result_router(
            *arguments, None if mode == "none" else harness.standard_mock
        )
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        response = client.get(_path(harness, "/{version_id}/taxonomy"))
    assert response.status_code == 200, response.text
    assert response.json() == harness.standards.taxonomy_for_result_version(
        harness.version_id
    )
    assert harness.standard_mock.taxonomy_for_result_version.call_count == (
        1 if mode == "injected" else 0
    )


@pytest.mark.parametrize(
    "suffix", ["/{version_id}/records", "/{version_id}/record-groups"]
)
def test_semantic_filter_validation_is_enforced_by_api(harness, suffix) -> None:
    response = harness.client.get(
        _path(harness, suffix), params={"comment_status": "INVALID"}
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "comment_status 不合法"}
