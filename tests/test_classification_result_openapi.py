from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_classification_result_pool import _publish, _seed_result_context

from web_backend.classification_result_service import ClassificationResultService
from web_backend.classification_standard_service import ClassificationStandardService
from web_backend.routers.accounts import SESSION_COOKIE
from web_backend.routers.classification_results import (
    XLSX_MEDIA_TYPE,
    create_classification_result_router,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _bind_result_standard(
    standard_service: ClassificationStandardService,
    result_id: str,
    taxonomy_version: str,
) -> None:
    standard = next(
        item
        for item in standard_service.list()
        if item["taxonomy_version"] == taxonomy_version
    )
    with standard_service.database.transaction(immediate=True) as connection:
        connection.execute(
            """
            UPDATE classification_results SET standard_version_id = ?
            WHERE id = ?
            """,
            (standard["standard_version_id"], result_id),
        )


def test_response_models_preserve_classification_result_json(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)
    published = _publish(context)
    version_id = str(published["version_id"])
    result_id = str(published["result_id"])
    result_service = ClassificationResultService(context.database)
    standard_service = ClassificationStandardService(context.database)
    _bind_result_standard(
        standard_service,
        result_id,
        context.taxonomy.version,
    )

    app = FastAPI()

    def current_user() -> dict[str, str]:
        return {"id": "user-1"}

    app.include_router(
        create_classification_result_router(
            result_service,
            current_user,
            standard_service,
        )
    )
    client = TestClient(app)
    cases = (
        ("/api/classification-results", result_service.list()),
        (
            f"/api/classification-results/{version_id}",
            result_service.get(version_id),
        ),
        (
            f"/api/classification-results/{version_id}/versions",
            result_service.history(version_id),
        ),
        (
            f"/api/classification-results/{version_id}/taxonomy",
            standard_service.taxonomy_for_result_version(version_id),
        ),
        (
            f"/api/classification-results/{version_id}/summary",
            result_service.summary(version_id),
        ),
        (
            f"/api/classification-results/{version_id}/records",
            result_service.records(version_id),
        ),
        (
            f"/api/classification-results/{version_id}/drilldown?group_by=problem",
            result_service.drilldown(version_id, "problem"),
        ),
        (
            f"/api/classification-results/{version_id}/drilldown?group_by=category",
            result_service.drilldown(version_id, "category"),
        ),
    )

    for endpoint, expected in cases:
        response = client.get(endpoint)
        assert response.status_code == 200, response.text
        assert response.json() == expected


def test_schema_only_openapi_export_is_complete_and_deterministic(
    tmp_path: Path,
) -> None:
    command = [sys.executable, str(PROJECT_ROOT / "scripts/export_openapi.py")]
    first = subprocess.run(
        command,
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    second = subprocess.run(
        command,
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert first.stdout == second.stdout
    assert first.stderr == second.stderr == ""
    assert list(tmp_path.iterdir()) == []
    schema = json.loads(first.stdout)
    expected_paths = {
        "/api/classification-results",
        "/api/classification-results/{version_id}",
        "/api/classification-results/{version_id}/versions",
        "/api/classification-results/{version_id}/taxonomy",
        "/api/classification-results/{version_id}/summary",
        "/api/classification-results/{version_id}/records",
        "/api/classification-results/{version_id}/drilldown",
        "/api/classification-results/{version_id}/download",
    }
    assert set(schema["paths"]) == expected_paths

    operation_ids = []
    for path_item in schema["paths"].values():
        operation = path_item["get"]
        operation_ids.append(operation["operationId"])
        assert operation["responses"]["200"]["content"]
    assert len(operation_ids) == len(set(operation_ids))

    for path_item in schema["paths"].values():
        parameters = path_item["get"].get("parameters", [])
        assert any(
            parameter["name"] == SESSION_COOKIE
            and parameter["in"] == "cookie"
            and parameter["required"] is False
            for parameter in parameters
        )

    json_paths = expected_paths - {"/api/classification-results/{version_id}/download"}
    for path in json_paths:
        response_schema = schema["paths"][path]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]
        assert response_schema

    download_content = schema["paths"][
        "/api/classification-results/{version_id}/download"
    ]["get"]["responses"]["200"]["content"]
    assert XLSX_MEDIA_TYPE in download_content
    assert "application/json" not in download_content
