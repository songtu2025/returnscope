import hashlib
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute
from task_router_helpers import (
    CONFLICT_CASES,
    ROUTES,
    SEGMENT_KEY,
    SERVICE_METHODS,
    _request,
)
from task_router_helpers import harness as harness

from web_backend.classification_result_service import ResultPublicationError
from web_backend.task_service import (
    TaskPlanConflict,
    TaskResultPublishConflict,
    TaskRevisionConflict,
)


def test_task_router_registration_and_openapi_contract(
    harness: SimpleNamespace,
) -> None:
    routes = [route for route in harness.router.routes if isinstance(route, APIRoute)]
    actual = [
        f"{next(iter(route.methods))}|{route.path}|{route.name}|{route.status_code or 200}"
        for route in routes
    ]
    assert actual == ROUTES
    assert all(
        route.dependant.dependencies[0].call is harness.current_user for route in routes
    )
    # 固定当前完整接口定义，包含回收站分页及确认操作原因可选的契约。
    contract = harness.app.openapi()
    recycle = contract["paths"]["/api/tasks/recycle"]["get"]
    parameters = {item["name"]: item["schema"] for item in recycle["parameters"]}
    assert parameters["page_size"]["maximum"] == 100
    assert parameters["page"]["minimum"] == 1
    rename = contract["components"]["schemas"]["TaskRenameRequest"]
    assert "note" not in rename["required"]
    assert rename["properties"]["note"]["default"] == ""
    assert (
        "410" in contract["paths"]["/api/tasks/{task_id}/download"]["get"]["responses"]
    )
    schema = json.dumps(contract, ensure_ascii=False, sort_keys=True)
    assert hashlib.sha256(schema.encode()).hexdigest() == (
        "f7d4496b3d893b36a0ac173e01d92fdfc769b7af29cd34262286c11c48632e9a"
    )


@pytest.mark.parametrize("contract", ROUTES)
def test_every_task_route_requires_authentication(
    harness: SimpleNamespace, contract: str
) -> None:
    def deny_user() -> dict[str, str]:
        raise HTTPException(status_code=401, detail="请先登录")

    harness.app.dependency_overrides[harness.current_user] = deny_user
    response = _request(harness, contract.split("|")[2])
    assert response.status_code == 401
    assert response.json() == {"detail": "请先登录"}
    assert not harness.task.mock_calls
    assert not harness.analysis.mock_calls


@pytest.mark.parametrize("contract", ROUTES)
def test_task_routes_remain_available_to_ordinary_users(
    harness: SimpleNamespace, contract: str
) -> None:
    response = _request(harness, contract.split("|")[2])
    assert response.status_code == int(contract.split("|")[3]), response.text


@pytest.mark.parametrize("name", SERVICE_METHODS)
def test_task_service_value_errors_remain_bad_requests(
    harness: SimpleNamespace, name: str
) -> None:
    getattr(harness.task, SERVICE_METHODS[name]).side_effect = ValueError("合成错误")
    response = _request(harness, name)
    assert response.status_code == 400
    assert response.json() == {"detail": "合成错误"}


@pytest.mark.parametrize("name", SERVICE_METHODS)
@pytest.mark.parametrize(
    "error_type",
    [
        TaskPlanConflict,
        TaskRevisionConflict,
        TaskResultPublishConflict,
        ResultPublicationError,
    ],
)
def test_task_conflicts_preserve_status_and_message(
    harness: SimpleNamespace, name: str, error_type: type[Exception]
) -> None:
    error = error_type("合成冲突")
    service_method = getattr(harness.task, SERVICE_METHODS[name])
    service_method.side_effect = error
    mapped = (name, error_type) in CONFLICT_CASES
    if mapped or isinstance(error, ValueError):
        response = _request(harness, name)
        assert response.status_code == (409 if mapped else 400)
        assert response.json() == {"detail": "合成冲突"}
    else:
        with pytest.raises(error_type) as raised:
            _request(harness, name)
        assert raised.value is error
    service_method.assert_called_once()


@pytest.mark.parametrize(
    "name", [*SERVICE_METHODS, "get_task_analysis", "download_filtered_analysis"]
)
def test_unexpected_route_errors_are_propagated_once(
    harness: SimpleNamespace, name: str
) -> None:
    service = harness.task if name in SERVICE_METHODS else harness.analysis
    method = SERVICE_METHODS.get(
        name, "get" if name == "get_task_analysis" else "export_filtered"
    )
    service_method = getattr(service, method)
    error = RuntimeError("合成意外异常")
    service_method.side_effect = error
    with pytest.raises(RuntimeError) as raised:
        _request(harness, name)
    assert raised.value is error
    service_method.assert_called_once()


def test_segment_specific_routes_precede_dynamic_actions(
    harness: SimpleNamespace,
) -> None:
    _request(harness, "retry_task_segment")
    _request(harness, "retry_segment_result_publish")
    _request(harness, "control_task_segment")
    harness.task.retry_segment.assert_called_once_with(
        task_id="task-1",
        segment_key=SEGMENT_KEY,
        actor_id="user-1",
        expected_revision=3,
        reason="合成原因",
    )
    harness.task.retry_result_publish.assert_called_once_with(
        task_id="task-1",
        segment_id="segment-1",
        actor_id="user-1",
        expected_revision=3,
        reason="合成原因",
    )
    harness.task.segment_action.assert_called_once_with(
        task_id="task-1",
        segment_key=SEGMENT_KEY,
        action="resume",
        actor_id="user-1",
        expected_revision=3,
        note="合成操作",
    )


@pytest.mark.parametrize("method", ["get", "export_filtered"])
@pytest.mark.parametrize(
    ("message", "status"), [("任务不存在", 404), ("尚未完成", 409)]
)
def test_analysis_errors_preserve_status(
    harness: SimpleNamespace, method: str, message: str, status: int
) -> None:
    getattr(harness.analysis, method).side_effect = ValueError(message)
    name = "get_task_analysis" if method == "get" else "download_filtered_analysis"
    response = _request(harness, name)
    assert response.status_code == status
    assert response.json() == {"detail": message}


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("get_task", "任务不存在"),
        ("stream_task_events", "任务不存在"),
        ("download_result", "结果文件尚未生成"),
        ("download_segment_result", "任务不存在"),
    ],
)
def test_missing_task_responses(
    harness: SimpleNamespace, name: str, message: str
) -> None:
    harness.task.get.return_value = None
    response = _request(harness, name)
    assert response.status_code == 404
    assert response.json() == {"detail": message}


def test_rename_endpoint_accepts_name_without_reason(harness: SimpleNamespace) -> None:
    response = harness.client.patch(
        "/api/tasks/task-1", json={"title": "同名任务", "expected_revision": 3}
    )
    assert response.status_code == 200
    assert harness.task.rename.call_args.kwargs["task_id"] == "task-1"
    assert harness.task.rename.call_args.kwargs["title"] == "同名任务"
    assert harness.task.rename.call_args.kwargs["note"] == ""
    assert harness.task.rename.call_args.kwargs["expected_revision"] == 3


@pytest.mark.parametrize("name", ["download_result", "download_segment_result"])
def test_current_download_requires_background_export_and_legacy_file_stays_available(
    harness: SimpleNamespace, name: str
) -> None:
    legacy = _request(harness, name)
    assert legacy.status_code == 200
    assert legacy.content == b"synthetic-result"
    assert "attachment" in legacy.headers["Content-Disposition"]
    harness.task.get.return_value["segments"][0]["result_version_id"] = "result-current"
    response = _request(harness, name)
    assert response.status_code == 410
    assert "后台生成" in response.json()["detail"]
