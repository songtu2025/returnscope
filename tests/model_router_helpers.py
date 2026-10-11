from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from router_contract_helpers import RouteCase

from web_backend.config_service import ConfigService
from web_backend.routers.models import create_model_router

MODEL_BODY = {"model_key": "synthetic-model"}


MODEL_DEFAULTS = {
    **MODEL_BODY,
    "display_name": "",
    "supported_efforts": ["low", "medium", "high"],
    "active": True,
}


UPDATE_BODY = {
    "display_name": "合成模型",
    "supported_efforts": ["medium"],
    "active": False,
}


CONFIG_BODY = {
    "name": "合成服务",
    "base_url": "https://example.invalid/v1",
    "primary_model": "synthetic-model",
    "change_note": "验证创建",
}


CONFIG_DEFAULTS = {
    **CONFIG_BODY,
    "connection_id": None,
    "provider": "responses-compatible",
    "api_key": "",
    "primary_effort": "medium",
    "cheap_model": None,
    "cheap_effort": "medium",
    "secondary_model": None,
    "secondary_effort": "high",
    "cheap_audit_percent": 5,
    "requests_per_minute": 60,
    "max_workers": 4,
    "timeout_seconds": 120,
    "models": None,
}


ROUTE_CASES = (
    RouteCase(service_method="list", path="/api/configs"),
    RouteCase(
        service_method="add_model",
        path="/api/connections/connection-1/models",
        method="POST",
        request={"json": MODEL_BODY},
        kwargs={**MODEL_DEFAULTS, "connection_id": "connection-1", "actor_id": "42"},
        status=201,
    ),
    RouteCase(
        service_method="sync_models_from_provider",
        path="/api/connections/connection-1/models/discover",
        method="POST",
        args=("connection-1", "42"),
    ),
    RouteCase(
        service_method="update_model",
        path="/api/models/model-1",
        method="PATCH",
        request={"json": UPDATE_BODY},
        kwargs={**UPDATE_BODY, "model_id": "model-1", "actor_id": "42"},
    ),
    RouteCase(
        service_method="validate_model",
        path="/api/models/model-1/validate",
        method="POST",
        args=("model-1", "42", None),
    ),
    RouteCase(
        service_method="start_model_validation",
        path="/api/models/model-1/validation-runs",
        method="POST",
        args=("model-1", "42", None),
        status=201,
    ),
    RouteCase(
        service_method="create_version",
        path="/api/configs",
        method="POST",
        request={"json": CONFIG_BODY},
        kwargs={**CONFIG_DEFAULTS, "actor_id": "42"},
        status=201,
    ),
    RouteCase(
        service_method="validate",
        path="/api/configs/version-1/validate",
        method="POST",
        args=("version-1", "42"),
    ),
    RouteCase(
        service_method="discard_draft",
        path="/api/configs/version-1",
        method="DELETE",
        args=("version-1", "42"),
    ),
    RouteCase(
        service_method="start_config_validation",
        path="/api/configs/version-1/validation-runs",
        method="POST",
        args=("version-1", "42"),
        status=201,
    ),
    RouteCase(
        service_method="latest_active_validation_run",
        path="/api/connections/connection-1/active-validation",
        args=("connection-1",),
    ),
    RouteCase(
        service_method="get_validation_run",
        path="/api/validation-runs/run-1",
        args=("run-1",),
    ),
    RouteCase(
        service_method="publish",
        path="/api/configs/version-1/publish",
        method="POST",
        args=("version-1", "42"),
    ),
)


CASES_BY_METHOD = {case.service_method: case for case in ROUTE_CASES}


READ_METHODS = {"list", "latest_active_validation_run", "get_validation_run"}


START_METHODS = {"start_model_validation", "start_config_validation"}


WRITE_CASES = tuple(
    case for case in ROUTE_CASES if case.service_method not in READ_METHODS
)


def synthetic_user() -> dict[str, Any]:
    return {"id": 42, "is_admin": True}


@pytest.fixture
def harness() -> Iterator[SimpleNamespace]:
    service = Mock(spec=ConfigService)
    executor = Mock(spec=ThreadPoolExecutor)
    app = FastAPI()
    app.include_router(create_model_router(service, executor, synthetic_user))
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, service=service, executor=executor)
