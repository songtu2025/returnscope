import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator
from unittest.mock import Mock, call

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from httpx2 import Response

from web_backend.analysis_service import AnalysisService
from web_backend.classification_result_service import ResultPublicationError
from web_backend.routers.tasks import create_task_router
from web_backend.task_service import (
    TaskPlanConflict,
    TaskResultPublishConflict,
    TaskRevisionConflict,
    TaskService,
)

ROUTES = [
    "GET|/api/tasks|list_tasks|200",
    "POST|/api/tasks/preflight|preflight_task|200",
    "POST|/api/tasks|create_task|201",
    "POST|/api/tasks/archive|archive_tasks|200",
    "POST|/api/tasks/{task_id}/replan/preflight|preflight_replan|200",
    "POST|/api/tasks/{task_id}/replan|replan_task|200",
    "POST|/api/tasks/{task_id}/segments/{segment_key:path}/retry|retry_task_segment|200",
    "POST|/api/tasks/{task_id}/segments/{segment_id}/retry-result-publish|retry_segment_result_publish|200",
    "PUT|/api/tasks/{task_id}/segments/order|reorder_task_segments|200",
    "PATCH|/api/tasks/{task_id}/parallelism|update_task_parallelism|200",
    "POST|/api/tasks/{task_id}/segments/{segment_key:path}/{action}|control_task_segment|200",
    "GET|/api/tasks/{task_id}/analysis|get_task_analysis|200",
    "GET|/api/tasks/{task_id}/analysis/download|download_filtered_analysis|200",
    "GET|/api/tasks/{task_id}|get_task|200",
    "PATCH|/api/tasks/{task_id}|rename_task|200",
    "POST|/api/tasks/{task_id}/cancel|cancel_task|200",
    "POST|/api/tasks/{task_id}/pause|pause_task|200",
    "POST|/api/tasks/{task_id}/retry|retry_task|201",
    "POST|/api/tasks/{task_id}/resume|resume_task|200",
    "GET|/api/tasks/{task_id}/events|stream_task_events|200",
    "GET|/api/tasks/{task_id}/download|download_result|200",
    "GET|/api/tasks/{task_id}/segments/{segment_key:path}/download|download_segment_result|200",
]
SERVICE_METHODS = {
    "preflight_task": "preflight",
    "create_task": "create",
    "archive_tasks": "set_archived",
    "preflight_replan": "replan_preflight",
    "replan_task": "replan",
    "retry_task_segment": "retry_segment",
    "retry_segment_result_publish": "retry_result_publish",
    "reorder_task_segments": "reorder_segments",
    "update_task_parallelism": "set_parallelism",
    "control_task_segment": "segment_action",
    "rename_task": "rename",
    "cancel_task": "cancel",
    "pause_task": "pause",
    "retry_task": "retry",
    "resume_task": "resume",
}
SEGMENT_KEY = "SEEKWAY:US/KP001/footwear"
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.fixture
def harness(tmp_path: Path) -> Iterator[SimpleNamespace]:
    result = tmp_path / "analysis.xlsx"
    result.write_bytes(b"synthetic-result")
    task = Mock(spec=TaskService)
    task.list.return_value = [{"id": "task-1", "created_by": "another-user"}]
    for method in SERVICE_METHODS.values():
        getattr(task, method).return_value = {"status": "queued"}
    task.set_archived.return_value = [{"id": "task-1", "archived": True}]
    task.get.return_value = {
        "id": "task-1",
        "created_by": "another-user",
        "status": "completed",
        "result_file_path": str(result),
        "result_version": 3,
        "segments": [{"segment_key": SEGMENT_KEY, "result_file_path": str(result)}],
    }
    task.events.return_value = []
    analysis = Mock(spec=AnalysisService)
    analysis.get.return_value = {"total": 1}
    analysis.export_filtered.return_value = (b"filtered-result", "filtered.xlsx")

    def current_user() -> dict[str, str]:
        return {"id": "user-1", "role": "user"}

    app = FastAPI()
    router = create_task_router(task, analysis, current_user)
    app.include_router(router)
    with TestClient(app) as client:
        yield SimpleNamespace(
            client=client,
            task=task,
            analysis=analysis,
            app=app,
            current_user=current_user,
            result=result,
            router=router,
        )


def _request(harness: SimpleNamespace, name: str) -> Response:
    contract = next(row for row in ROUTES if row.split("|")[2] == name)
    method, path, _, _ = contract.split("|")
    path = (
        path.replace("{task_id}", "task-1")
        .replace("{segment_id}", "segment-1")
        .replace("{segment_key:path}", SEGMENT_KEY)
        .replace("{action}", "resume")
    )
    # 使用所有请求模型均可接受的合成字段，避免读取真实任务或配置。
    body = {
        "dataset_version_id": "dataset-1",
        "product_version_id": "product-1",
        "expected_revision": 3,
        "title": "合成任务",
        "note": "合成操作",
        "reason": "合成原因",
        "plan_hash": "a" * 64,
        "unresolved_policy": "run_ready",
        "task_ids": ["task-1"],
        "archived": True,
        "segment_keys": [SEGMENT_KEY],
        "max_parallel_segments": 2,
    }
    return harness.client.request(method, path, json=body)


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
    # 固定拆分前的完整接口定义，覆盖参数、模型、操作标识和响应描述。
    schema = json.dumps(harness.app.openapi(), ensure_ascii=False, sort_keys=True)
    assert hashlib.sha256(schema.encode()).hexdigest() == (
        "1c12666cb00aa8a4a1291dd301d27c266b8a098741e711bd1430dc96a90da415"
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


@pytest.mark.parametrize(
    ("name", "error_type"),
    [
        ("create_task", TaskPlanConflict),
        ("replan_task", TaskPlanConflict),
        ("replan_task", TaskRevisionConflict),
        ("retry_task_segment", TaskRevisionConflict),
        ("retry_segment_result_publish", ResultPublicationError),
        ("retry_segment_result_publish", TaskResultPublishConflict),
        ("retry_segment_result_publish", TaskRevisionConflict),
        ("reorder_task_segments", TaskRevisionConflict),
        ("update_task_parallelism", TaskRevisionConflict),
        ("control_task_segment", TaskRevisionConflict),
        ("rename_task", TaskRevisionConflict),
        ("cancel_task", TaskRevisionConflict),
        ("pause_task", TaskRevisionConflict),
        ("resume_task", TaskRevisionConflict),
    ],
)
def test_task_conflicts_preserve_status_and_message(
    harness: SimpleNamespace, name: str, error_type: type[ValueError]
) -> None:
    getattr(harness.task, SERVICE_METHODS[name]).side_effect = error_type("合成冲突")
    response = _request(harness, name)
    assert response.status_code == 409
    assert response.json() == {"detail": "合成冲突"}


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
    ("name", "disposition", "content"),
    [
        (
            "download_filtered_analysis",
            'attachment; filename="filtered.xlsx"',
            b"filtered-result",
        ),
        (
            "download_result",
            'attachment; filename="task-1-analysis-v3.xlsx"',
            b"synthetic-result",
        ),
        (
            "download_segment_result",
            "attachment; filename*=utf-8''task-1-SEEKWAY%3AUS/KP001/footwear-analysis.xlsx",
            b"synthetic-result",
        ),
    ],
)
def test_downloads_preserve_content_and_headers(
    harness: SimpleNamespace, name: str, disposition: str, content: bytes
) -> None:
    response = _request(harness, name)
    assert response.status_code == 200
    assert response.content == content
    assert response.headers["content-type"] == XLSX_TYPE
    assert response.headers["content-disposition"] == disposition


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


@pytest.mark.parametrize("name", ["download_result", "download_segment_result"])
def test_download_rejects_missing_files(harness: SimpleNamespace, name: str) -> None:
    harness.result.unlink()
    response = _request(harness, name)
    message = "结果文件不存在" if name == "download_result" else "Listing 结果不存在"
    assert response.status_code == 404
    assert response.json() == {"detail": message}


@pytest.mark.parametrize(
    "status", ["completed", "failed", "cancelled", "blocked", "partial"]
)
@pytest.mark.parametrize(
    ("after", "last_id", "expected"), [(2, "5", 5), (5, "2", 5), (2, "invalid", 2)]
)
def test_event_stream_resumes_and_closes(
    harness: SimpleNamespace, status: str, after: int, last_id: str, expected: int
) -> None:
    harness.task.get.return_value["status"] = status
    event = {"id": 6, "message": "合成事件"}
    harness.task.events.return_value = [event]
    response = harness.client.get(
        f"/api/tasks/task-1/events?after={after}", headers={"Last-Event-ID": last_id}
    )
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
    assert response.text == (
        f"id: 6\nevent: task\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
        "event: close\ndata: {}\n\n"
    )
    harness.task.events.assert_called_once_with("task-1", expected)


def test_event_stream_keeps_alive_and_advances_cursor(
    harness: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    sleep = Mock()

    async def fake_sleep(delay: float) -> None:
        sleep(delay)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    harness.task.get.return_value["status"] = "running"
    harness.task.events.side_effect = [[{"id": 7}]] + [[]] * 59
    response = _request(harness, "stream_task_events")
    assert (
        response.text
        == 'id: 7\nevent: task\ndata: {"id": 7}\n\n' + ": keepalive\n\n" * 60
    )
    assert (
        harness.task.events.call_args_list
        == [call("task-1", 0)] + [call("task-1", 7)] * 59
    )
    assert sleep.call_args_list == [call(1)] * 60
