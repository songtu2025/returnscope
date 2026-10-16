from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_task_planning import NoopRunner, _database_with_inputs

from web_backend.dataset_service import DatasetService
from web_backend.routers.task_planning_routes import register_task_collection_routes
from web_backend.task_service import TaskService
from web_backend.tasks.plan_selection import selected_plan
from web_backend.worker import TaskWorker


def _service(tmp_path: Path) -> TaskService:
    database, _, products_path = _database_with_inputs(tmp_path)
    products = pd.read_excel(products_path)
    products.loc[1, ["Listing", "品类A", "品类B"]] = ["L2", "水鞋", "薄底水鞋"]
    products.to_excel(products_path, sheet_name="产品信息汇总表", index=False)
    DatasetService(database, SimpleNamespace(data_dir=tmp_path)).add_version(
        "dataset-products",
        products_path,
        products_path.name,
        "application/xlsx",
        "测试输入",
        "user-1",
    )
    returns_path = tmp_path / "returns.csv"
    returns = pd.read_csv(returns_path)
    returns["店铺/站点"] = "SEEKWAY:US"
    returns.to_csv(returns_path, index=False, encoding="utf-8-sig")
    return TaskService(database)


def _client(service: TaskService) -> TestClient:
    from fastapi import APIRouter

    router = APIRouter()
    register_task_collection_routes(router, service, lambda: {"id": "user-1"})
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _payload(service: TaskService) -> dict:
    plan = service.preflight(
        "version-returns", "version-products", None, None, "config-1"
    )
    return {
        "title": "合成范围选择",
        "dataset_version_id": "version-returns",
        "product_version_id": "version-products",
        "config_version_id": "config-1",
        "plan_hash": plan["plan_hash"],
        "segment_order": [item["segment_key"] for item in plan["segments"]],
        "selected_segment_keys": [plan["segments"][1]["segment_key"]],
    }


def test_selected_listing_only_is_persisted_and_retry_keeps_scope(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    payload = _payload(service)
    response = _client(service).post("/api/tasks", json=payload)
    assert response.status_code == 201
    task = response.json()
    assert [item["segment_key"] for item in task["segments"]] == payload[
        "selected_segment_keys"
    ]
    assert task["segments"][0]["execution_order"] == 1
    assert task["snapshot"]["execution_plan"]["summary"]["executable_count"] == 1
    assert task["snapshot"]["scope"]["selected_listings"] == [
        {"store": "SEEKWAY:US", "listing": "L2"}
    ]
    with service.database.transaction() as connection:
        connection.execute(
            "UPDATE tasks SET status = 'completed' WHERE id = ?", (task["id"],)
        )
    retry = service.retry(task["id"], "user-1")
    assert len(retry["segments"]) == 1
    assert retry["segments"][0]["scope"]["listing"] == "L2"
    assert (
        retry["snapshot"]["scope"]["selected_listings"]
        == task["snapshot"]["scope"]["selected_listings"]
    )
    with service.database.transaction() as connection:
        connection.execute(
            "UPDATE tasks SET status = 'partial' WHERE id = ?", (task["id"],)
        )
    plan = service.replan_preflight(task["id"], "version-products")
    assert len(plan["segments"]) == 1
    replanned = service.replan(
        task["id"],
        "user-1",
        "version-products",
        task["revision"],
        plan["plan_hash"],
        "run_ready",
        "",
    )
    assert [item["scope"]["listing"] for item in replanned["segments"]] == ["L2"]
    assert len(pd.read_csv(tmp_path / "returns.csv")) == 2


@pytest.mark.parametrize(
    "selected, status",
    [([], 400), (["不存在"], 409), (["duplicate", "duplicate"], 409)],
)
def test_api_rejects_empty_unknown_or_duplicate_selection(
    tmp_path: Path, selected: list[str], status: int
) -> None:
    service = _service(tmp_path)
    payload = {**_payload(service), "selected_segment_keys": selected}
    assert _client(service).post("/api/tasks", json=payload).status_code == status
    assert service.list() == []


def test_missing_selection_keeps_legacy_all_and_stale_plan_is_rejected(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    payload = _payload(service)
    payload.pop("selected_segment_keys")
    response = _client(service).post("/api/tasks", json=payload)
    assert len(response.json()["segments"]) == 2
    response = _client(service).post(
        "/api/tasks", json={**payload, "plan_hash": "0" * 64}
    )
    assert response.status_code == 409


def test_selection_cannot_split_a_listing_between_categories() -> None:
    response = {
        "segments": [
            {"segment_key": "a", "scope": {"store": "合成", "listing": "L1"}},
            {"segment_key": "b", "scope": {"store": "合成", "listing": "L1"}},
        ]
    }
    with pytest.raises(ValueError, match="全部执行分组"):
        selected_plan(response, ["a"])


def test_worker_only_claims_selected_listing(tmp_path: Path) -> None:
    service = _service(tmp_path)
    task = _client(service).post("/api/tasks", json=_payload(service)).json()
    worker = TaskWorker(service.database, NoopRunner(), concurrency=1)
    try:
        assert worker._claim_next_segment() == (task["id"], task["segments"][0]["id"])
        assert worker._claim_next_segment() is None
    finally:
        worker.stop()
