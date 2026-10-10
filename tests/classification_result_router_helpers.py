from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Iterator
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_classification_result_openapi import _bind_result_standard
from test_classification_result_pool import _publish, _seed_result_context

from web_backend.classification_result_service import ClassificationResultService
from web_backend.classification_standard_service import ClassificationStandardService
from web_backend.routers.classification_results import (
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
        "version_id,page,page_size,order_id,listing,product_name,source_sku,matched_msku,product_sku,asin,problem,quality_status,comment_status,system_rerun_required",
    ),
    (
        "/{version_id}/record-groups",
        "list_record_groups",
        "record_groups",
        "version_id,page,page_size,order_id,listing,product_name,source_sku,matched_msku,product_sku,asin,problem,quality_status,comment_status,system_rerun_required",
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
