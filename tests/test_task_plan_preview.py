from pathlib import Path

import pandas as pd
import pytest
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.testclient import TestClient
from test_task_plan_selection import _client, _payload, _service

from web_backend.routers.task_planning_routes import register_task_collection_routes


def _preview(tmp_path: Path):
    service = _service(tmp_path)
    path = tmp_path / "returns.csv"
    frame = pd.read_csv(path)
    duplicate, other = frame.iloc[0].copy(), frame.iloc[0].copy()
    duplicate["customer-comments"] = "  鞋子太大  "
    other["customer-comments"] = "鞋子太小"
    pd.concat([frame, pd.DataFrame([duplicate, other])], ignore_index=True).to_csv(
        path, index=False, encoding="utf-8-sig"
    )
    creation = _payload(service)
    payload = {
        key: value
        for key, value in creation.items()
        if key not in {"title", "segment_order", "selected_segment_keys"}
    }
    payload["segment_key"] = creation["segment_order"][0]
    return service, _client(service), payload


def test_preview_reuses_actual_grouping_and_source_rows_without_creating_task(
    tmp_path: Path,
) -> None:
    service, client, payload = _preview(tmp_path)
    result = client.post(
        "/api/tasks/preflight/segment-data", json={**payload, "page_size": 1}
    ).json()
    assert (result["total"], result["group_total"], result["record_total"]) == (2, 2, 3)
    assert result["items"][0]["record_count"] == 2
    assert result["items"][0]["comment"] == "鞋子太大"
    page2 = client.post(
        "/api/tasks/preflight/segment-data", json={**payload, "page_size": 1, "page": 2}
    ).json()
    assert page2["items"][0]["group_no"] == 2
    records = client.post(
        "/api/tasks/preflight/segment-data",
        json={**payload, "view": "records", "group_no": 1},
    ).json()
    assert records["total"] == 2
    assert [row["source_row"] for row in records["items"]] == [2, 4]
    assert [row["comment"] for row in records["items"]] == ["鞋子太大", "  鞋子太大  "]
    assert all(row["sku"] == "SKU-1" for row in records["items"])
    assert all(
        set(row)
        == {
            "group_no",
            "title",
            "comment",
            "record_count",
            "source_row",
            "date",
            "sku",
            "product_name",
        }
        for row in records["items"]
    )
    assert service.list() == []


@pytest.mark.parametrize(
    "changes, status",
    [
        ({"plan_hash": "0" * 64}, 409),
        ({"segment_key": "missing"}, 400),
        ({"view": "records", "group_no": 99}, 400),
        ({"group_no": 1}, 400),
        ({"page": 0}, 422),
        ({"page_size": 51}, 422),
    ],
)
def test_preview_validates_plan_segment_scope_and_page_limits(
    tmp_path: Path, changes: dict, status: int
) -> None:
    _, client, payload = _preview(tmp_path)
    response = client.post(
        "/api/tasks/preflight/segment-data", json={**payload, **changes}
    )
    assert response.status_code == status


def test_preview_requires_login(tmp_path: Path) -> None:
    service, _, payload = _preview(tmp_path)

    def unauthorized():
        raise HTTPException(status_code=401, detail="请先登录")

    router = APIRouter()
    register_task_collection_routes(router, service, unauthorized)
    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).post("/api/tasks/preflight/segment-data", json=payload)
    assert response.status_code == 401
    assert service.list() == []
