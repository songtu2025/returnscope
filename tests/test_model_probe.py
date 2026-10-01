from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from test_validation_run_service import _build_harness, _create_run

from web_backend import model_probe
from web_backend.model_probe import ModelProbe, ModelValidationError


@pytest.fixture
def probe_config() -> dict[str, Any]:
    return {
        "base_url": "https://probe.example.test/v1///",
        "api_key": "test-api-key",
        "timeout_seconds": "37",
    }


@pytest.fixture
def probe_io(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {
        "body": json.dumps(
            {
                "model": "returned-model",
                "output": [{"content": [{"type": "output_text", "text": "OK"}]}],
            }
        ).encode("utf-8"),
        "status": 200,
        "requests": [],
        "events": [],
        "clock_calls": [],
    }

    def open_response(request: urllib.request.Request, timeout: int) -> BytesIO:
        state["requests"].append((request, timeout))
        if "error" in state:
            raise state["error"]
        response: Any = BytesIO(state["body"])
        if "status" in state:
            response.status = state["status"]
        state["response"] = response
        return response

    def clock() -> float:
        value = 10 + len(state["clock_calls"]) * 0.125
        state["clock_calls"].append(value)
        return value

    monkeypatch.setattr(urllib.request, "urlopen", open_response)
    monkeypatch.setattr(model_probe, "time", SimpleNamespace(monotonic=clock))
    return state


@pytest.mark.parametrize("status", [200, "202", None])
@pytest.mark.parametrize("with_callback", [False, True])
def test_success_keeps_request_result_and_stage_order(
    probe_config: dict[str, Any],
    probe_io: dict[str, Any],
    status: int | str | None,
    with_callback: bool,
) -> None:
    if status is None:
        probe_io.pop("status")
    else:
        probe_io["status"] = status
    before = deepcopy(probe_config)

    def callback(stage: str, message: str, data: dict[str, Any]) -> None:
        probe_io["events"].append((stage, message, data))

    actual = ModelProbe.test(
        probe_config, "requested-model", "high", callback if with_callback else None
    )
    expected_status = int(status) if status is not None else 200
    assert actual == {
        "http_status": expected_status,
        "duration_ms": 125,
        "response_model": "returned-model",
        "output_chars": 2,
    }
    request, timeout = probe_io["requests"][0]
    assert request.full_url == "https://probe.example.test/v1/responses"
    assert request.get_method() == "POST"
    assert request.get_header("Authorization") == "Bearer test-api-key"
    assert request.get_header("Content-type") == "application/json"
    assert json.loads(request.data) == {
        "model": "requested-model",
        "input": "仅返回 OK",
        "reasoning": {"effort": "high"},
    }
    assert timeout == 37
    assert probe_io["events"] == (
        [
            ("requesting", "正在发送测试请求并等待模型响应", {}),
            (
                "checking",
                f"已收到 HTTP {expected_status}，正在检查响应结构",
                {"http_status": expected_status},
            ),
        ]
        if with_callback
        else []
    )
    assert probe_io["response"].closed
    assert probe_config == before


@pytest.mark.parametrize("response_model", [None, "", 123])
def test_response_reuses_text_extraction_and_model_fallback(
    probe_config: dict[str, Any],
    probe_io: dict[str, Any],
    response_model: Any,
) -> None:
    probe_io["body"] = json.dumps(
        {
            "model": response_model,
            "output": [
                {
                    "content": [
                        {"type": "output_text", "text": "  OK"},
                        {"type": "refusal", "text": "忽略"},
                    ]
                },
                {"content": [{"type": "output_text", "text": "好  "}]},
            ],
        }
    ).encode("utf-8")
    actual = ModelProbe.test(probe_config, "requested-model", "low")
    assert actual["output_chars"] == 3
    assert actual["response_model"] == (
        str(response_model) if response_model else "requested-model"
    )


@pytest.mark.parametrize(
    "case",
    [
        (401, "authentication", "请检查 API 密钥是否正确且具备模型访问权限"),
        (403, "authentication", "请检查 API 密钥是否正确且具备模型访问权限"),
        (404, "model_not_found", "请检查 Base URL 和模型 ID 是否正确"),
        (429, "rate_limited", "请检查配额或稍后重新验证"),
        (500, "http_error", "请检查接入地址和上游服务状态"),
        (418, "http_error", "请检查接入地址和上游服务状态"),
    ],
)
@pytest.mark.parametrize(
    "body", [b"upstream failure", b"\xff" + "错".encode("utf-8") * 320]
)
def test_http_error_keeps_classification_truncated_body_and_cause(
    probe_config: dict[str, Any],
    probe_io: dict[str, Any],
    case: tuple[int, str, str],
    body: bytes,
) -> None:
    code, category, suggestion = case
    error = urllib.error.HTTPError(
        "https://probe.example.test", code, "模拟错误", {}, BytesIO(body)
    )
    probe_io["error"] = error
    with pytest.raises(ModelValidationError) as captured:
        ModelProbe.test(
            probe_config,
            "requested-model",
            "low",
            lambda stage, message, data: probe_io["events"].append(stage),
        )
    actual = captured.value
    assert (
        str(actual)
        == f"requested-model 测试失败：HTTP {code} {body.decode('utf-8', errors='replace')[:300]}"
    )
    assert (actual.category, actual.suggestion, actual.http_status) == (
        category,
        suggestion,
        code,
    )
    assert actual.__cause__ is error
    assert probe_io["events"] == ["requesting"]
    assert len(probe_io["clock_calls"]) == 1


@pytest.mark.parametrize(
    "case",
    [
        (
            urllib.error.URLError(TimeoutError("模拟超时")),
            "timeout",
            "requested-model 请求超时",
            "请检查网络、上游模型状态或适当增加请求超时时间",
        ),
        (
            urllib.error.URLError(socket.timeout("模拟超时")),
            "timeout",
            "requested-model 请求超时",
            "请检查网络、上游模型状态或适当增加请求超时时间",
        ),
        (
            TimeoutError("模拟超时"),
            "timeout",
            "requested-model 请求超时",
            "请检查网络、上游模型状态或适当增加请求超时时间",
        ),
        (
            socket.timeout("模拟超时"),
            "timeout",
            "requested-model 请求超时",
            "请检查网络、上游模型状态或适当增加请求超时时间",
        ),
        (
            urllib.error.URLError("模拟连接失败"),
            "connection",
            "requested-model 连接失败：模拟连接失败",
            "请检查 Base URL、网络连接和上游服务状态",
        ),
    ],
)
def test_network_failure_keeps_timeout_distinction_and_cause(
    probe_config: dict[str, Any],
    probe_io: dict[str, Any],
    case: tuple[Exception, str, str, str],
) -> None:
    error, category, message, suggestion = case
    probe_io["error"] = error
    with pytest.raises(ModelValidationError) as captured:
        ModelProbe.test(probe_config, "requested-model", "low")
    actual = captured.value
    assert str(actual) == message
    assert (actual.category, actual.suggestion, actual.http_status) == (
        category,
        suggestion,
        None,
    )
    assert actual.__cause__ is error


@pytest.mark.parametrize("body", [b"", b"not-json", b"{", b"<html>"])
def test_invalid_json_keeps_response_error_and_checking_stage(
    probe_config: dict[str, Any],
    probe_io: dict[str, Any],
    body: bytes,
) -> None:
    probe_io["body"] = body
    with pytest.raises(ModelValidationError) as captured:
        ModelProbe.test(
            probe_config,
            "requested-model",
            "low",
            lambda stage, message, data: probe_io["events"].append(stage),
        )
    actual = captured.value
    assert str(actual) == "requested-model 返回的内容不是有效 JSON"
    assert (actual.category, actual.suggestion, actual.http_status) == (
        "response_format",
        "请确认接口兼容 Responses API 响应格式",
        200,
    )
    assert isinstance(actual.__cause__, json.JSONDecodeError)
    assert probe_io["events"] == ["requesting", "checking"]
    assert len(probe_io["clock_calls"]) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"output": []},
        {"output": [{"content": [{"type": "output_text", "text": "  "}]}]},
        {"output": [{"content": [{"type": "output_text", "text": ""}]}]},
        {"output": [{"content": [{"type": "refusal", "text": "拒绝"}]}]},
    ],
)
def test_empty_response_keeps_model_error_without_exception_cause(
    probe_config: dict[str, Any],
    probe_io: dict[str, Any],
    payload: dict[str, Any],
) -> None:
    probe_io["body"] = json.dumps(payload).encode("utf-8")
    with pytest.raises(ModelValidationError) as captured:
        ModelProbe.test(probe_config, "requested-model", "low")
    actual = captured.value
    assert str(actual) == "requested-model 返回内容为空"
    assert (actual.category, actual.suggestion, actual.http_status) == (
        "empty_response",
        "请确认模型能够返回 output_text 内容",
        200,
    )
    assert actual.__cause__ is None


@pytest.mark.parametrize(
    ("payload", "exception"),
    [
        (None, AttributeError),
        ([], AttributeError),
        ({"output": None}, TypeError),
        ({"output": [None]}, AttributeError),
    ],
)
def test_unexpected_json_structure_keeps_original_exception(
    probe_config: dict[str, Any],
    probe_io: dict[str, Any],
    payload: Any,
    exception: type[Exception],
) -> None:
    probe_io["body"] = json.dumps(payload).encode("utf-8")
    with pytest.raises(exception):
        ModelProbe.test(probe_config, "requested-model", "low")


def test_invalid_utf8_still_propagates_before_checking_stage(
    probe_config: dict[str, Any],
    probe_io: dict[str, Any],
) -> None:
    probe_io["body"] = b"\xff"
    with pytest.raises(UnicodeDecodeError):
        ModelProbe.test(
            probe_config,
            "requested-model",
            "low",
            lambda stage, message, data: probe_io["events"].append(stage),
        )
    assert probe_io["events"] == ["requesting"]


@pytest.mark.parametrize("failing_stage", ["requesting", "checking"])
def test_callback_failures_propagate_without_changing_request_order(
    probe_config: dict[str, Any],
    probe_io: dict[str, Any],
    failing_stage: str,
) -> None:
    error = RuntimeError("模拟回调失败")

    def callback(stage: str, message: str, data: dict[str, Any]) -> None:
        probe_io["events"].append(stage)
        if stage == failing_stage:
            raise error

    with pytest.raises(RuntimeError) as captured:
        ModelProbe.test(probe_config, "requested-model", "low", callback)
    assert captured.value is error
    assert probe_io["events"] == (
        ["requesting"] if failing_stage == "requesting" else ["requesting", "checking"]
    )
    assert len(probe_io["requests"]) == (0 if failing_stage == "requesting" else 1)


@pytest.mark.parametrize("scenario", ["passed", "authentication", "response_format"])
def test_real_probe_updates_validation_run_and_skips_after_failure(
    tmp_path: Path,
    probe_io: dict[str, Any],
    scenario: str,
) -> None:
    harness = _build_harness(tmp_path)
    harness.service.model_probe = ModelProbe()
    if scenario == "authentication":
        probe_io["error"] = urllib.error.HTTPError(
            "https://probe.example.test", 401, "模拟错误", {}, BytesIO(b"denied")
        )
    elif scenario == "response_format":
        probe_io["body"] = b"not-json"
    run = _create_run(harness, "config", 3)
    harness.service.run_validation(str(run["id"]))
    actual = harness.service.get_validation_run(str(run["id"]))
    assert actual is not None
    events = harness.service.validation_events(str(run["id"]))
    if scenario == "passed":
        assert actual["status"] == "passed"
        assert [item["status"] for item in actual["items"]] == ["passed"] * 3
        assert [
            event["stage"] for event in events if event["event_type"] == "stage"
        ] == ["requesting", "checking"] * 3
        assert len(probe_io["requests"]) == 3
        assert len(harness.catalog.validation_updates) == 3
        return
    assert actual["status"] == "failed"
    assert actual["error_category"] == scenario
    assert actual["completed_count"] == 1
    assert [item["status"] for item in actual["items"]] == [
        "failed",
        "skipped",
        "skipped",
    ]
    failed = actual["items"][0]
    assert failed["error_category"] == scenario
    assert failed["http_status"] == (401 if scenario == "authentication" else 200)
    assert len(probe_io["requests"]) == 1
    assert harness.catalog.validation_updates[0][1] == "failed"
    assert [event["stage"] for event in events if event["event_type"] == "stage"] == (
        ["requesting"] if scenario == "authentication" else ["requesting", "checking"]
    )
    failure_event = next(
        event for event in events if event["event_type"] == "model_failed"
    )
    assert failure_event["data"]["error_category"] == scenario
    assert failure_event["data"]["http_status"] == failed["http_status"]
