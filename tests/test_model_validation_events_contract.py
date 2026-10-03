import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, call

import pytest
from fastapi import HTTPException
from test_model_router_contract import harness as harness
from test_model_router_contract import synthetic_user

EVENT_PATH = "/api/validation-runs/run-1/events"


@pytest.mark.parametrize("status", ("passed", "failed"))
@pytest.mark.parametrize(
    ("after", "last_id", "expected"),
    [
        (2, "5", 5),
        (5, "2", 5),
        (2, "invalid", 2),
        (2, "-1", 2),
        (0, "", 0),
        (0, None, 0),
    ],
)
def test_validation_events_resume_and_close_with_unchanged_wire_format(
    harness: SimpleNamespace,
    status: str,
    after: int,
    last_id: str | None,
    expected: int,
) -> None:
    harness.service.get_validation_run.return_value = {"status": status}
    event = {"id": "6", "stage": "checking", "message": "合成验证事件"}
    harness.service.validation_events.return_value = [event]
    response = harness.client.get(
        EVENT_PATH,
        params={"after": after},
        headers={} if last_id is None else {"Last-Event-ID": last_id},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
    assert (
        response.text
        == f"id: 6\nevent: validation\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
        + "event: close\ndata: {}\n\n"
    )
    assert harness.service.mock_calls == [
        call.get_validation_run("run-1"),
        call.validation_events("run-1", expected),
        call.get_validation_run("run-1"),
    ]
    assert harness.executor.mock_calls == []


def test_validation_events_advance_cursor_and_keep_alive_before_completion(
    harness: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    sleep = AsyncMock()
    monkeypatch.setattr(
        "web_backend.routers.model_validation_routes.asyncio.sleep", sleep
    )
    first = {"id": 7, "message": "合成首条事件"}
    second = {"id": 8, "message": "合成末条事件"}
    harness.service.get_validation_run.side_effect = [
        {"status": "queued"},
        {"status": "running"},
        {"status": "passed"},
    ]
    harness.service.validation_events.side_effect = [[first], [second]]
    response = harness.client.get(EVENT_PATH)
    assert response.status_code == 200
    assert response.text == (
        f"id: 7\nevent: validation\ndata: {json.dumps(first, ensure_ascii=False)}\n\n"
        ": keepalive\n\n"
        f"id: 8\nevent: validation\ndata: {json.dumps(second, ensure_ascii=False)}\n\n"
        "event: close\ndata: {}\n\n"
    )
    assert harness.service.mock_calls == [
        call.get_validation_run("run-1"),
        call.validation_events("run-1", 0),
        call.get_validation_run("run-1"),
        call.validation_events("run-1", 7),
        call.get_validation_run("run-1"),
    ]
    sleep.assert_awaited_once_with(0.5)


@pytest.mark.parametrize("run", ({"status": "running"}, {"status": "queued"}, None))
def test_validation_events_keep_existing_poll_limit_without_false_close(
    harness: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    run: dict[str, str] | None,
) -> None:
    sleep = AsyncMock()
    monkeypatch.setattr(
        "web_backend.routers.model_validation_routes.asyncio.sleep", sleep
    )
    harness.service.get_validation_run.side_effect = [{"status": "running"}] + [
        run
    ] * 900
    harness.service.validation_events.return_value = []
    response = harness.client.get(EVENT_PATH)
    assert response.status_code == 200
    assert response.text == ": keepalive\n\n" * 900
    assert harness.service.validation_events.call_args_list == [call("run-1", 0)] * 900
    assert harness.service.get_validation_run.call_args_list == [call("run-1")] * 901
    assert sleep.await_args_list == [call(0.5)] * 900


def test_validation_events_require_login_before_reading_run(
    harness: SimpleNamespace,
) -> None:
    def reject_user() -> dict[str, Any]:
        raise HTTPException(status_code=401, detail="请先登录")

    harness.client.app.dependency_overrides[synthetic_user] = reject_user
    response = harness.client.get(EVENT_PATH)
    assert response.status_code == 401
    assert response.json() == {"detail": "请先登录"}
    assert harness.service.mock_calls == harness.executor.mock_calls == []


def test_ordinary_user_can_read_validation_events(harness: SimpleNamespace) -> None:
    harness.client.app.dependency_overrides[synthetic_user] = lambda: {
        "id": "ordinary-user"
    }
    harness.service.get_validation_run.return_value = {"status": "passed"}
    harness.service.validation_events.return_value = []
    response = harness.client.get(EVENT_PATH)
    assert response.status_code == 200
    assert response.text == "event: close\ndata: {}\n\n"
    assert harness.executor.mock_calls == []


def test_missing_validation_run_is_rejected_before_opening_stream(
    harness: SimpleNamespace,
) -> None:
    harness.service.get_validation_run.return_value = None
    response = harness.client.get(EVENT_PATH)
    assert response.status_code == 404
    assert response.json() == {"detail": "验证记录不存在"}
    assert harness.service.mock_calls == [call.get_validation_run("run-1")]


@pytest.mark.parametrize("after", (-1, "invalid"))
def test_invalid_resume_query_does_not_call_service(
    harness: SimpleNamespace, after: int | str
) -> None:
    response = harness.client.get(EVENT_PATH, params={"after": after})
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["query", "after"]
    assert harness.service.mock_calls == []


@pytest.mark.parametrize("service_method", ("get_validation_run", "validation_events"))
def test_unexpected_validation_stream_errors_are_not_swallowed(
    harness: SimpleNamespace, service_method: str
) -> None:
    harness.service.get_validation_run.return_value = {"status": "passed"}
    error = RuntimeError("合成事件流异常")
    getattr(harness.service, service_method).side_effect = error
    with pytest.raises(RuntimeError) as raised:
        harness.client.get(EVENT_PATH)
    assert raised.value is error
