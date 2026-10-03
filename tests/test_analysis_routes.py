from collections.abc import Iterator
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest
from analysis_api_helpers import (
    SYNTHETIC_EMAIL,
    SYNTHETIC_PASSWORD,
    analysis_app,
)
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(analysis_app(tmp_path)) as result:
        yield result


def _login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": SYNTHETIC_EMAIL, "password": SYNTHETIC_PASSWORD},
    )
    assert response.status_code == 200


@pytest.mark.parametrize("suffix", ["", "/download"])
def test_analysis_requires_authentication(client: TestClient, suffix: str) -> None:
    response = client.get(f"/api/tasks/task-1/analysis{suffix}")
    assert response.status_code == 401


@pytest.mark.parametrize(
    "view", ["all", "overview", "diagnosis", "products", "quality", "details"]
)
def test_analysis_views_keep_the_same_record_scope(
    client: TestClient, view: str
) -> None:
    _login(client)
    response = client.get("/api/tasks/task-1/analysis", params={"view": view})
    assert response.status_code == 200
    payload = response.json()
    assert payload["scope"] == {"total_records": 3, "filtered_records": 3}
    assert payload["view"] == view
    assert payload["overview"]["metrics"]["total_records"] == 3
    if view == "all":
        assert {"diagnosis", "products", "quality", "details"} <= payload.keys()
    elif view != "overview":
        assert view in payload


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        ({"start_date": "2026-08-02"}, 2),
        ({"listing": "missing"}, 0),
        ({"listing": "L1", "problem_code": "FIT_TOO_SMALL_U1"}, 3),
    ],
)
def test_analysis_details_and_export_share_the_filtered_scope(
    client: TestClient, filters: dict[str, str], expected: int
) -> None:
    _login(client)
    response = client.get(
        "/api/tasks/task-1/analysis", params={**filters, "view": "details"}
    )
    assert response.status_code == 200
    assert response.json()["scope"]["filtered_records"] == expected
    exported = client.get("/api/tasks/task-1/analysis/download", params=filters)
    assert exported.status_code == 200
    workbook = pd.read_excel(BytesIO(exported.content), sheet_name=None)
    assert set(workbook) == {"筛选明细", "语义层级"}
    assert len(workbook["筛选明细"]) == expected
    assert {"return_date", "has_text"}.isdisjoint(workbook["筛选明细"].columns)
    assert "attachment" in exported.headers["content-disposition"]
    assert workbook["语义层级"]["重复记录数"].sum() == expected


@pytest.mark.parametrize("suffix", ["", "/download"])
def test_analysis_reports_a_missing_task(client: TestClient, suffix: str) -> None:
    _login(client)
    response = client.get(f"/api/tasks/missing/analysis{suffix}")
    assert response.status_code == 404
    assert response.json()["detail"] == "任务不存在"


@pytest.mark.parametrize("suffix", ["", "/download"])
def test_analysis_reports_an_unavailable_result(
    client: TestClient, suffix: str
) -> None:
    _login(client)
    with client.app.state.database.transaction() as connection:
        connection.execute("UPDATE tasks SET status='running' WHERE id='task-1'")
    response = client.get(f"/api/tasks/task-1/analysis{suffix}")
    assert response.status_code == 409
    assert response.json()["detail"] == "该 Listing 尚未生成可分析结果"
