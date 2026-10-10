from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest
from classification_result_router_helpers import BASE_PATH, ROUTES, _path
from classification_result_router_helpers import harness as harness
from fastapi import FastAPI, HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from web_backend.classification_result_service import (
    ClassificationResultNotFound,
)
from web_backend.classification_standard_service import (
    ClassificationStandardNotFound,
)
from web_backend.routers.classification_results import (
    XLSX_MEDIA_TYPE,
    create_classification_result_router,
)


def test_result_router_preserves_registration_and_response_settings(
    harness: SimpleNamespace,
) -> None:
    routes = [route for route in harness.router.routes if isinstance(route, APIRoute)]
    correction = next(route for route in routes if route.methods == {"PATCH"})
    assert correction.path == BASE_PATH + "/{version_id}/records/{record_id}/semantics"
    assert correction.response_model is not None
    assert correction.response_model_exclude_unset
    assert correction.dependant.dependencies[0].call is harness.current_user
    routes = [route for route in routes if route.methods == {"GET"}]
    actual = [
        (
            route.path.removeprefix(BASE_PATH),
            route.name,
            ",".join(
                parameter["name"]
                for parameter in harness.app.openapi()["paths"][route.path]["get"].get(
                    "parameters", []
                )
            ),
        )
        for route in routes
    ]
    assert [
        (suffix, name, set(parameters.split(",")))
        for suffix, name, parameters in actual
    ] == [
        (suffix, name, set(parameters.split(",")))
        for suffix, name, _, parameters in ROUTES
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
