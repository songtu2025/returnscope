from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.testclient import TestClient
from test_task_plan_selection import _client, _payload, _service

from web_backend.dataset_service import DatasetService
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
    service, client, payload = _preview(tmp_path)
    assert (
        client.post("/api/tasks/preflight/segment-data", json=payload).status_code
        == 200
    )

    def unauthorized():
        raise HTTPException(status_code=401, detail="请先登录")

    router = APIRouter()
    register_task_collection_routes(router, service, unauthorized)
    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).post("/api/tasks/preflight/segment-data", json=payload)
    assert response.status_code == 401
    assert service.list() == []


def test_preview_pages_share_preparation_but_creation_revalidates(
    tmp_path, monkeypatch
):
    service, client, payload = _preview(tmp_path)
    prepare = Mock(wraps=service.plan_service.prepare)
    monkeypatch.setattr(service.plan_service, "prepare", prepare)
    url = "/api/tasks/preflight/segment-data"
    first = client.post(url, json={**payload, "page_size": 1}).json()
    second = client.post(url, json={**payload, "page_size": 1, "page": 2}).json()
    records = client.post(
        url, json={**payload, "view": "records", "group_no": 1}
    ).json()
    assert first["items"][0]["group_no"] == 1
    assert second["items"][0]["group_no"] == 2
    assert records["total"] == 2
    assert prepare.call_count == 1
    assert service.list() == []
    creation = {key: value for key, value in payload.items() if key != "segment_key"}
    assert client.post("/api/tasks", json=creation).status_code == 201
    assert prepare.call_count == 2


@pytest.mark.parametrize(
    "change", ["source", "version", "product", "model", "standard", "claims", "scope"]
)
def test_preview_cache_rechecks_input_identity(tmp_path, monkeypatch, change):
    from return_semantics.claims import ClaimsEntry

    service, client, payload = _preview(tmp_path)
    plan = service.plan_service
    claims = tmp_path / "synthetic-claims.json"
    claims.write_text('{"version":"v1","claims":[]}', encoding="utf-8")
    monkeypatch.setattr(
        plan.claims_resolver,
        "entries",
        (
            *plan.claims_resolver.entries,
            ClaimsEntry("UNRELATED", "L0", "none", claims, "v1"),
        ),
    )
    prepare = Mock(wraps=plan.prepare)
    monkeypatch.setattr(plan, "prepare", prepare)
    url = "/api/tasks/preflight/segment-data"
    assert client.post(url, json=payload).status_code == 200
    if change == "source":
        path = tmp_path / "returns.csv"
        path.write_bytes(path.read_bytes() + b"\n")
    elif change == "claims":
        claims.write_text('{"version":"v2","claims":[]}', encoding="utf-8")
    elif change == "scope":
        payload["store"] = "SEEKWAY:US"
    elif change == "product":
        products = pd.read_excel(tmp_path / "products.xlsx", dtype=str)
        products.loc[0, "Listing"] = "合成新Listing"
        path = tmp_path / "updated-products.xlsx"
        products.to_excel(path, sheet_name="产品信息汇总表", index=False)
        DatasetService(
            service.database, SimpleNamespace(data_dir=tmp_path)
        ).add_version(
            "dataset-products",
            path,
            path.name,
            "application/xlsx",
            "合成更新",
            "user-1",
        )
    else:
        with service.database.transaction() as connection:
            if change == "version":
                connection.execute(
                    "UPDATE dataset_versions SET sha256='changed' WHERE id='version-returns'"
                )
            elif change == "standard":
                connection.execute(
                    "UPDATE classification_standards SET name=name || '合成修改'"
                )
            else:
                connection.execute(
                    "UPDATE api_config_versions SET primary_effort=CASE WHEN primary_effort='low' THEN 'high' ELSE 'low' END WHERE id='config-1'"
                )
    response = client.post(url, json=payload)
    assert response.status_code == (
        409 if change in {"version", "standard", "scope", "product"} else 200
    )
    assert prepare.call_count == 2
    assert service.list() == []


def test_preview_cache_rejects_archived_input_and_evicts_old_plans(
    tmp_path, monkeypatch
):
    service, client, payload = _preview(tmp_path)
    prepare = Mock(wraps=service.plan_service.prepare)
    monkeypatch.setattr(service.plan_service, "prepare", prepare)
    url = "/api/tasks/preflight/segment-data"
    for width in range(6):
        assert (
            client.post(url, json={**payload, "store": " " * width}).status_code == 200
        )
    assert len(service.plan_service._preview_cache) == 4
    assert prepare.call_count == 6
    assert client.post(url, json={**payload, "store": ""}).status_code == 200
    assert prepare.call_count == 7
    with service.database.transaction() as connection:
        connection.execute(
            "UPDATE datasets SET archived_at='2026-10-17' WHERE kind='returns'"
        )
    assert client.post(url, json={**payload, "store": ""}).status_code == 400
    assert prepare.call_count == 7
