import asyncio
import json
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest
from task_router_helpers import (
    XLSX_TYPE,
    _request,
)
from task_router_helpers import harness as harness


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
