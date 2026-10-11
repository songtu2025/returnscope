from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_dashboard_router_contract import RouteCase

from web_backend.api_contracts.datasets import MySQLReturnImportRequest
from web_backend.dataset_service import DatasetService
from web_backend.mysql_return_service import MySQLReturnService
from web_backend.routers.datasets import create_dataset_router

MYSQL_BODY = {"mapping": {"comment": "feedback"}}


IMPORT_BODY = {"inspection_id": "inspection-1", "mode": "new"}


UPDATE_BODY = {
    "row_index": 0,
    "expected_version": 3,
    "changes": {"product_name": "合成商品"},
    "change_note": "验证修改",
}


COMPLETION_ITEM = {
    "msku": "SKU-1",
    "listing": "L1",
    "category_a": "眼镜",
    "category_b": "太阳镜",
}


COMPLETION_BODY = {
    "expected_version": 3,
    "items": [COMPLETION_ITEM],
    "change_note": "验证品类补全",
}


MYSQL_METHODS = {"schema", "preview", "import_returns"}


ROUTE_CASES = (
    RouteCase(
        service_method="schema",
        path="/api/mysql-return-imports/schema",
        kwargs={"refresh": False},
    ),
    RouteCase(
        service_method="preview",
        path="/api/mysql-return-imports/preview",
        method="POST",
        request={"json": MYSQL_BODY},
        args=(MySQLReturnImportRequest(**MYSQL_BODY),),
    ),
    RouteCase(
        service_method="import_returns",
        path="/api/mysql-return-imports",
        method="POST",
        request={"json": MYSQL_BODY},
        args=(MySQLReturnImportRequest(**MYSQL_BODY), "42"),
        status=201,
    ),
    RouteCase(service_method="list", path="/api/datasets", args=(None, None)),
    RouteCase(service_method="list_versions", path="/api/data-versions", args=(None,)),
    RouteCase(
        service_method="references",
        path="/api/data-versions/version-1/references",
        args=("version-1",),
        kwargs={"page": 1, "page_size": 50},
    ),
    RouteCase(
        service_method="product_scopes",
        path="/api/data-versions/version-1/scopes",
        args=("version-1",),
    ),
    RouteCase(
        service_method="import_staged_returns",
        path="/api/return-imports",
        method="POST",
        request={"json": IMPORT_BODY},
        kwargs={
            **IMPORT_BODY,
            "name": "",
            "change_note": "",
            "actor_id": "42",
        },
        status=201,
    ),
    RouteCase(
        service_method="get", path="/api/datasets/dataset-1", args=("dataset-1", None)
    ),
    RouteCase(
        service_method="preview_rows",
        path="/api/datasets/dataset-1/rows",
        kwargs={
            "dataset_id": "dataset-1",
            "offset": 0,
            "limit": 50,
            "query": "",
            "store": "",
            "category": "",
            "version": None,
        },
    ),
    RouteCase(
        service_method="update_product_row",
        path="/api/datasets/dataset-1/rows",
        method="PATCH",
        request={"json": UPDATE_BODY},
        kwargs={**UPDATE_BODY, "dataset_id": "dataset-1", "actor_id": "42"},
    ),
    RouteCase(
        service_method="complete_product_categories",
        path="/api/datasets/dataset-1/category-completion",
        method="POST",
        request={"json": COMPLETION_BODY},
        kwargs={
            **COMPLETION_BODY,
            "items": [{**COMPLETION_ITEM, "store": "", "product_name": ""}],
            "store": "",
            "dataset_id": "dataset-1",
            "actor_id": "42",
        },
    ),
)


CASES_BY_METHOD = {case.service_method: case for case in ROUTE_CASES}


ERROR_STATUSES = {
    "schema": (None, None, 503, None),
    "preview": (400, 400, 503, None),
    "import_returns": (400, 400, 503, None),
    "list": (None, None, None, None),
    "list_versions": (None, None, None, None),
    "references": (404, 404, 404, None),
    "product_scopes": (400, 400, 400, None),
    "import_staged_returns": (400, 400, 400, None),
    "get": (None, None, None, None),
    "preview_rows": (400, 400, 400, None),
    "update_product_row": (400, 409, 400, None),
    "complete_product_categories": (400, 409, 400, None),
}


def synthetic_user() -> dict[str, Any]:
    return {"id": 42, "is_admin": True}


@pytest.fixture
def harness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[SimpleNamespace]:
    service = Mock(spec=DatasetService)
    mysql = Mock(spec=MySQLReturnService)
    constructor = Mock(return_value=mysql)
    monkeypatch.setattr("web_backend.routers.datasets.MySQLReturnService", constructor)
    settings = SimpleNamespace(data_dir=tmp_path)
    app = FastAPI()
    app.include_router(create_dataset_router(service, settings, synthetic_user))
    constructor.assert_called_once_with(service, settings)
    with TestClient(app) as client:
        yield SimpleNamespace(
            client=client, service=service, mysql=mysql, settings=settings
        )
