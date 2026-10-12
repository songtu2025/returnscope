from dataclasses import replace
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, call

import pytest
from fastapi import HTTPException
from model_router_helpers import (
    CASES_BY_METHOD,
    MODEL_BODY,
    READ_METHODS,
    ROUTE_CASES,
    START_METHODS,
    UPDATE_BODY,
    WRITE_CASES,
    synthetic_user,
)
from model_router_helpers import harness as harness
from router_contract_helpers import RouteCase


@pytest.mark.parametrize("case", ROUTE_CASES, ids=lambda case: case.service_method)
def test_model_routes_preserve_responses_defaults_and_background_submission(
    harness: SimpleNamespace, case: RouteCase
) -> None:
    payload = {"id": "synthetic-run", "status": "queued", "version": None}
    expected = [payload] if case.service_method == "list" else payload
    getattr(harness.service, case.service_method).return_value = expected
    response = harness.client.request(case.method, case.path, **case.request)
    assert response.status_code == case.status
    assert response.json() == expected
    assert harness.service.mock_calls == [
        getattr(call, case.service_method)(*case.args, **case.kwargs)
    ]
    if case.service_method in START_METHODS:
        assert harness.executor.mock_calls == [
            call.submit(harness.service.run_validation, "synthetic-run")
        ]
    else:
        assert harness.executor.mock_calls == []


@pytest.mark.parametrize("case", ROUTE_CASES, ids=lambda case: case.service_method)
def test_model_routes_require_login_before_service_or_executor_calls(
    harness: SimpleNamespace, case: RouteCase
) -> None:
    def reject_user() -> dict[str, Any]:
        raise HTTPException(status_code=401, detail="请先登录")

    harness.client.app.dependency_overrides[synthetic_user] = reject_user
    response = harness.client.request(case.method, case.path, **case.request)
    assert response.status_code == 401
    assert response.json() == {"detail": "请先登录"}
    assert harness.service.mock_calls == harness.executor.mock_calls == []


@pytest.mark.parametrize("case", WRITE_CASES, ids=lambda case: case.service_method)
@pytest.mark.parametrize("user", ({"id": 42}, {"id": 42, "is_admin": False}))
def test_model_maintenance_requires_admin_before_any_operation(
    harness: SimpleNamespace, case: RouteCase, user: dict[str, Any]
) -> None:
    harness.client.app.dependency_overrides[synthetic_user] = lambda: user
    response = harness.client.request(case.method, case.path, **case.request)
    assert response.status_code == 403
    assert response.json() == {"detail": "仅系统管理员可维护模型服务"}
    assert harness.service.mock_calls == harness.executor.mock_calls == []


@pytest.mark.parametrize(
    "case",
    [case for case in ROUTE_CASES if case.service_method in READ_METHODS],
    ids=lambda case: case.service_method,
)
def test_ordinary_users_can_read_model_configuration_and_validation(
    harness: SimpleNamespace, case: RouteCase
) -> None:
    harness.client.app.dependency_overrides[synthetic_user] = lambda: {
        "id": "ordinary-user"
    }
    getattr(harness.service, case.service_method).return_value = (
        [] if case.service_method == "list" else {}
    )
    assert harness.client.get(case.path).status_code == 200
    assert harness.service.mock_calls == [
        getattr(call, case.service_method)(*case.args)
    ]
    assert harness.executor.mock_calls == []


@pytest.mark.parametrize("case", ROUTE_CASES, ids=lambda case: case.service_method)
@pytest.mark.parametrize("error_type", (ValueError, RuntimeError))
def test_model_routes_preserve_error_mapping_without_submitting_failed_creation(
    harness: SimpleNamespace, case: RouteCase, error_type: type[Exception]
) -> None:
    error = error_type("合成模型异常")
    getattr(harness.service, case.service_method).side_effect = error
    if error_type is ValueError and case.service_method not in READ_METHODS:
        response = harness.client.request(case.method, case.path, **case.request)
        assert response.status_code == 400
        assert response.json() == {"detail": "合成模型异常"}
    else:
        with pytest.raises(error_type) as raised:
            harness.client.request(case.method, case.path, **case.request)
        assert raised.value is error
    assert harness.service.mock_calls == [
        getattr(call, case.service_method)(*case.args, **case.kwargs)
    ]
    assert harness.executor.mock_calls == []


@pytest.mark.parametrize("service_method", ("validate_model", "start_model_validation"))
@pytest.mark.parametrize(
    ("body", "effort"),
    [(None, None), ({}, None), ({"effort": None}, None), ({"effort": "high"}, "high")],
)
def test_optional_validation_body_preserves_effort_fallback(
    harness: SimpleNamespace,
    service_method: str,
    body: dict[str, Any] | None,
    effort: str | None,
) -> None:
    case = CASES_BY_METHOD[service_method]
    getattr(harness.service, service_method).return_value = {"id": "synthetic-run"}
    response = harness.client.post(case.path, json=body)
    assert response.status_code == case.status
    assert harness.service.mock_calls == [
        getattr(call, service_method)("model-1", "42", effort)
    ]
    assert harness.executor.submit.call_count == int(service_method in START_METHODS)


@pytest.mark.parametrize("service_method", sorted(START_METHODS))
def test_validation_run_is_created_before_one_executor_submission(
    harness: SimpleNamespace, service_method: str
) -> None:
    trace = Mock()
    trace.attach_mock(harness.service, "service")
    trace.attach_mock(harness.executor, "executor")
    case = CASES_BY_METHOD[service_method]
    getattr(harness.service, service_method).return_value = {"id": "synthetic-run"}
    response = harness.client.post(case.path)
    assert response.status_code == 201
    assert trace.mock_calls == [
        getattr(call.service, service_method)(*case.args),
        call.executor.submit(harness.service.run_validation, "synthetic-run"),
    ]


@pytest.mark.parametrize("service_method", sorted(START_METHODS))
def test_executor_failure_is_propagated_without_retrying_creation(
    harness: SimpleNamespace, service_method: str
) -> None:
    case = CASES_BY_METHOD[service_method]
    getattr(harness.service, service_method).return_value = {"id": "synthetic-run"}
    error = RuntimeError("合成执行器异常")
    harness.executor.submit.side_effect = error
    with pytest.raises(RuntimeError) as raised:
        harness.client.post(case.path)
    assert raised.value is error
    assert harness.service.mock_calls == [getattr(call, service_method)(*case.args)]
    assert harness.executor.mock_calls == [
        call.submit(harness.service.run_validation, "synthetic-run")
    ]


@pytest.mark.parametrize(
    ("service_method", "expected_status"),
    [("get_validation_run", 404), ("latest_active_validation_run", 200)],
)
def test_missing_validation_run_keeps_each_read_contract(
    harness: SimpleNamespace, service_method: str, expected_status: int
) -> None:
    getattr(harness.service, service_method).return_value = None
    case = CASES_BY_METHOD[service_method]
    response = harness.client.get(case.path)
    assert response.status_code == expected_status
    assert response.json() == (
        {"detail": "验证记录不存在"} if expected_status == 404 else None
    )


@pytest.mark.parametrize(
    ("service_method", "field", "value"),
    [
        ("add_model", "model_key", ""),
        ("add_model", "model_key", "m" * 121),
        ("add_model", "supported_efforts", []),
        ("add_model", "supported_efforts", ["low"] * 4),
        ("update_model", "display_name", ""),
        ("update_model", "display_name", "m" * 81),
        ("create_version", "base_url", ""),
        ("create_version", "primary_model", ""),
        ("create_version", "change_note", "x" * 501),
        ("create_version", "cheap_audit_percent", -1),
        ("create_version", "cheap_audit_percent", 101),
        ("create_version", "requests_per_minute", 0),
        ("create_version", "requests_per_minute", 10001),
        ("create_version", "max_workers", 0),
        ("create_version", "max_workers", 17),
        ("create_version", "timeout_seconds", 4),
        ("create_version", "timeout_seconds", 601),
        ("validate_model", "effort", []),
        ("start_model_validation", "effort", []),
    ],
)
def test_invalid_model_requests_do_not_call_service_or_executor(
    harness: SimpleNamespace, service_method: str, field: str, value: Any
) -> None:
    case = CASES_BY_METHOD[service_method]
    payload = {**case.request.get("json", {}), field: value}
    response = harness.client.request(case.method, case.path, json=payload)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][:2] == ["body", field]
    assert harness.service.mock_calls == harness.executor.mock_calls == []


@pytest.mark.parametrize(
    "service_method", ("add_model", "update_model", "create_version")
)
def test_unknown_fields_cannot_override_actor(
    harness: SimpleNamespace, service_method: str
) -> None:
    case = CASES_BY_METHOD[service_method]
    payload = {**case.request["json"], "actor_id": "untrusted", "extra": "ignored"}
    getattr(harness.service, service_method).return_value = {}
    response = harness.client.request(case.method, case.path, json=payload)
    assert response.status_code == case.status
    assert harness.service.mock_calls == [
        getattr(call, service_method)(*case.args, **case.kwargs)
    ]


def test_model_creation_forwards_explicit_definition(harness: SimpleNamespace) -> None:
    payload = {**MODEL_BODY, **UPDATE_BODY}
    case = replace(
        CASES_BY_METHOD["add_model"],
        request={"json": payload},
        kwargs={**payload, "connection_id": "connection-1", "actor_id": "42"},
    )
    harness.service.add_model.return_value = {}
    response = harness.client.post(case.path, **case.request)
    assert response.status_code == 201
    assert harness.service.mock_calls == [call.add_model(**case.kwargs)]


@pytest.mark.parametrize("note", (None, "", " "))
def test_config_create_accepts_omitted_or_blank_change_note(
    harness: SimpleNamespace, note: str | None
) -> None:
    case = CASES_BY_METHOD["create_version"]
    payload = {**case.request["json"]}
    payload.pop("change_note")
    if note is not None:
        payload["change_note"] = note
    harness.service.create_version.return_value = {}
    assert harness.client.post(case.path, json=payload).status_code == case.status
    assert harness.service.create_version.call_args.kwargs["change_note"] == (
        note or ""
    )
