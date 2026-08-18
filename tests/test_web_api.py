from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pandas as pd
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient

from return_semantics.data import RETURN_COLUMNS, RETURN_STORE_COLUMN
from web_backend.app import create_app
from web_backend.routers.tasks import create_task_router
from web_backend.settings import Settings


class FakeResponsesHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != "/models":
            self.send_error(404)
            return
        body = json.dumps(
            {"data": [{"id": "test-model"}, {"id": "review-model"}]}
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if payload.get("model") == "auth-fail":
            body = json.dumps({"error": "invalid api key"}).encode("utf-8")
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if isinstance(payload.get("input"), str):
            text = "OK"
        else:
            text = json.dumps(
                {
                    "semantic_units": [
                        {
                            "subject": "PRODUCT",
                            "label_code": "FIT_TOO_LARGE",
                            "opinion": "鞋子太大",
                            "sentiment": "NEGATIVE",
                            "assertion": "AFFIRMED",
                            "part": "WHOLE_SHOE",
                            "evidence": "鞋子太大",
                            "implicit": False,
                            "claim_relation": "NONE",
                            "claim_id": None,
                        }
                    ],
                    "unknown_semantics": [],
                    "primary_label_codes": ["FIT_TOO_LARGE"],
                    "needs_review": True,
                    "review_reasons": ["测试人工复核"],
                }
            )
        body = json.dumps(
            {
                "model": payload["model"],
                "output": [{"content": [{"type": "output_text", "text": text}]}],
                "usage": {"input_tokens": 10, "output_tokens": 20},
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *args: object) -> None:
        return


def _write_input_files(tmp_path: Path) -> tuple[Path, Path]:
    returns_path = tmp_path / "returns.csv"
    row = {
        "return-date": "2026-08-01",
        "order-id": "ORDER-1",
        "sku": "SKU-1",
        "asin": "ASIN-1",
        "fnsku": "FNSKU-1",
        "product-name": "Water Shoes",
        "quantity": "1",
        "reason": "Too large",
        "customer-comments": "鞋子太大。",
    }
    pd.DataFrame([row], columns=RETURN_COLUMNS).to_csv(
        returns_path,
        index=False,
        encoding="utf-8-sig",
    )
    products_path = tmp_path / "products.xlsx"
    products = pd.DataFrame(
        [
            {
                "MSKU": "SKU-1",
                "店铺/站点": "SEEKWAY:US",
                "Listing": "SK001",
                "产品名称": "旧名称",
                "品类A": "水鞋",
                "品类B": "薄底水鞋",
            }
        ]
    )
    with pd.ExcelWriter(products_path, engine="openpyxl") as writer:
        products.to_excel(writer, sheet_name="产品信息汇总表", index=False)
    return returns_path, products_path


def _upload_dataset(
    client: TestClient,
    path: Path,
    name: str,
    kind: str,
) -> dict[str, object]:
    with path.open("rb") as file_handle:
        response = client.post(
            "/api/datasets",
            data={"name": name, "kind": kind},
            files={"file": (path.name, file_handle)},
        )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize("action", ["resume", "cancel"])
def test_task_segment_control_route_accepts_slashes(action: str) -> None:
    received: dict[str, object] = {}

    class StubTaskService:
        def segment_action(self, **kwargs: object) -> dict[str, object]:
            received.update(kwargs)
            return {"status": "queued"}

    app = FastAPI()
    app.include_router(
        create_task_router(
            task_service=StubTaskService(),
            analysis_service=object(),
            current_user=lambda: {"id": "user-1"},
        )
    )
    segment_key = "SEEKWAY:US/KP001/footwear"

    with TestClient(app) as client:
        response = client.post(
            f"/api/tasks/task-1/segments/{segment_key}/{action}",
            json={"expected_revision": 3, "note": "用户操作"},
        )

    assert response.status_code == 200, response.text
    assert received["segment_key"] == segment_key
    assert received["action"] == action
    assert received["expected_revision"] == 3


def test_category_completion_updates_multiple_stores_in_one_version(
    tmp_path: Path,
) -> None:
    settings = Settings(
        data_dir=tmp_path / "runtime",
        database_path=tmp_path / "runtime" / "app.db",
        session_days=14,
        task_workers=1,
        bootstrap_email="admin@example.com",
        bootstrap_name="管理员",
        bootstrap_password="test-password-123",
        encryption_key=Fernet.generate_key().decode("ascii"),
        secure_cookies=False,
    )
    app = create_app(start_worker=False, settings_override=settings)
    _returns_path, products_path = _write_input_files(tmp_path)

    with TestClient(app) as client:
        assert (
            client.post(
                "/api/auth/login",
                json={
                    "email": "admin@example.com",
                    "password": "test-password-123",
                },
            ).status_code
            == 200
        )
        products = _upload_dataset(client, products_path, "商品维度", "products")
        response = client.post(
            f"/api/datasets/{products['id']}/category-completion",
            json={
                "expected_version": 1,
                "items": [
                    {
                        "store": "SEEKWAY:US",
                        "msku": "SKU-US",
                        "listing": "US-LISTING",
                        "category_a": "眼镜",
                        "category_b": "儿童眼镜",
                    },
                    {
                        "store": "SEEKWAY:CA",
                        "msku": "SKU-CA",
                        "listing": "CA-LISTING",
                        "category_a": "遮阳帽",
                        "category_b": "儿童渔夫帽",
                    },
                ],
                "change_note": "一次补充两个站点的商品",
            },
        )

        assert response.status_code == 200, response.text
        updated = response.json()
        assert updated["current_version"] == 2
        rows = client.get(f"/api/datasets/{products['id']}/rows", params={"limit": 10})
        by_key = {
            (item["店铺/站点"], item["MSKU"]): item for item in rows.json()["records"]
        }
        assert by_key[("SEEKWAY:US", "SKU-US")]["Listing"] == "US-LISTING"
        assert by_key[("SEEKWAY:CA", "SKU-CA")]["品类B"] == "儿童渔夫帽"


def test_return_version_fills_only_missing_store_values(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "runtime",
        database_path=tmp_path / "runtime" / "app.db",
        session_days=14,
        task_workers=1,
        bootstrap_email="admin@example.com",
        bootstrap_name="管理员",
        bootstrap_password="test-password-123",
        encryption_key=Fernet.generate_key().decode("ascii"),
        secure_cookies=False,
    )
    app = create_app(start_worker=False, settings_override=settings)
    returns_path, _products_path = _write_input_files(tmp_path)
    frame = pd.read_csv(returns_path, dtype=str)
    version_path = tmp_path / "returns-v2.csv"
    version_frame = pd.concat([frame, frame], ignore_index=True)
    version_frame[RETURN_STORE_COLUMN] = ["SEEKWAY:CA", ""]
    version_frame.to_csv(version_path, index=False, encoding="utf-8-sig")

    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login",
            json={
                "email": "admin@example.com",
                "password": "test-password-123",
            },
        )
        assert login.status_code == 200
        returns = _upload_dataset(client, returns_path, "退货数据", "returns")
        with version_path.open("rb") as file_handle:
            response = client.post(
                f"/api/datasets/{returns['id']}/versions",
                data={
                    "change_note": "删除无效记录并补充站点",
                    "default_store": "SEEKWAY:US",
                },
                files={"file": (version_path.name, file_handle)},
            )

        assert response.status_code == 201, response.text
        updated = response.json()
        assert updated["current_version"] == 2
        assert updated["quality"]["matching_key_ready_rows"] == 2
        assert updated["quality"]["missing_store_rows"] == 0
        assert updated["quality"]["stores"] == ["SEEKWAY:CA", "SEEKWAY:US"]
        rows = client.get(f"/api/datasets/{returns['id']}/rows", params={"limit": 10})
        assert [item[RETURN_STORE_COLUMN] for item in rows.json()["records"]] == [
            "SEEKWAY:CA",
            "SEEKWAY:US",
        ]


def test_real_web_task_flow(tmp_path: Path) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeResponsesHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    settings = Settings(
        data_dir=tmp_path / "runtime",
        database_path=tmp_path / "runtime" / "app.db",
        session_days=14,
        task_workers=1,
        bootstrap_email="admin@example.com",
        bootstrap_name="管理员",
        bootstrap_password="test-password-123",
        encryption_key=Fernet.generate_key().decode("ascii"),
        secure_cookies=False,
    )
    app = create_app(start_worker=True, settings_override=settings)
    returns_path, products_path = _write_input_files(tmp_path)

    try:
        with TestClient(app) as client:
            login = client.post(
                "/api/auth/login",
                json={
                    "email": "admin@example.com",
                    "password": "test-password-123",
                },
            )
            assert login.status_code == 200
            admin_id = login.json()["id"]

            returns = _upload_dataset(client, returns_path, "退货数据", "returns")
            products = _upload_dataset(client, products_path, "商品维度", "products")
            versions = client.get("/api/data-versions").json()
            assert {item["kind"] for item in versions} == {"returns", "products"}
            scopes = client.get(
                f"/api/data-versions/{products['version_id']}/scopes"
            ).json()
            assert scopes == [{"store": "SEEKWAY:US", "listings": ["SK001"]}]
            downloaded_source = client.get(f"/api/datasets/{returns['id']}/download")
            assert downloaded_source.status_code == 200
            assert "鞋子太大" in downloaded_source.content.decode("utf-8-sig")
            dimension_rows = client.get(f"/api/datasets/{products['id']}/rows").json()
            assert dimension_rows["records"][0]["MSKU"] == "SKU-1"
            searched_rows = client.get(
                f"/api/datasets/{products['id']}/rows",
                params={"q": "SEEKWAY:US"},
            ).json()
            assert searched_rows["total"] == 1
            updated_dimension = client.patch(
                f"/api/datasets/{products['id']}/rows",
                json={
                    "row_index": 0,
                    "expected_version": 1,
                    "changes": {
                        "MSKU": "SKU-1",
                        "店铺/站点": "SEEKWAY:US",
                        "Listing": "SK001",
                        "产品名称": "涉水鞋",
                        "品类A": "水鞋",
                        "品类B": "薄底水鞋",
                    },
                    "change_note": "确认商品映射",
                },
            )
            assert updated_dimension.status_code == 200
            products = updated_dimension.json()
            assert products["current_version"] == 2
            dimension_audit = products["audit"][0]
            assert dimension_audit["action"] == "dimension_row_update"
            assert dimension_audit["before"]["values"]["产品名称"] == "旧名称"
            assert dimension_audit["after"]["values"]["产品名称"] == "涉水鞋"
            assert dimension_audit["after"]["note"] == "确认商品映射"
            stale_dimension = client.patch(
                f"/api/datasets/{products['id']}/rows",
                json={
                    "row_index": 0,
                    "expected_version": 1,
                    "changes": {"Listing": "STALE"},
                    "change_note": "过期修改",
                },
            )
            assert stale_dimension.status_code == 409

            completed_categories = client.post(
                f"/api/datasets/{products['id']}/category-completion",
                json={
                    "expected_version": 2,
                    "store": "SEEKWAY:US",
                    "items": [
                        {
                            "msku": "SKU-2",
                            "listing": "SK002",
                            "category_a": "水鞋",
                            "category_b": "儿童水鞋",
                            "product_name": "儿童涉水鞋",
                        }
                    ],
                    "change_note": "补充阻断任务商品品类",
                },
            )
            assert completed_categories.status_code == 200
            products = completed_categories.json()
            assert products["current_version"] == 3
            assert products["row_count"] == 2
            assert products["audit"][0]["action"] == "dimension_category_completion"
            added_row = client.get(
                f"/api/datasets/{products['id']}/rows",
                params={"q": "SKU-2"},
            ).json()["records"][0]
            assert added_row["Listing"] == "SK002"
            assert added_row["品类B"] == "儿童水鞋"

            config = client.post(
                "/api/configs",
                json={
                    "name": "测试线路",
                    "base_url": f"http://127.0.0.1:{server.server_port}",
                    "api_key": "test-key",
                    "primary_model": "test-model",
                    "primary_effort": "medium",
                    "cheap_model": None,
                    "secondary_model": None,
                    "change_note": "创建测试模型线路",
                    "models": [
                        {
                            "model_key": "test-model",
                            "display_name": "测试主模型",
                            "supported_efforts": ["medium"],
                        }
                    ],
                },
            )
            assert config.status_code == 201, config.text
            assert config.json()["api_key_masked"] == "••••-key"
            assert config.json()["change_note"] == "创建测试模型线路"
            config_id = config.json()["id"]
            config_audit = client.get(
                f"/api/audit/api_connection/{config.json()['connection_id']}"
            ).json()
            assert config_audit[0]["after"]["note"] == "创建测试模型线路"
            assert config_audit[0]["actor_name"] == "管理员"
            connection_id = config.json()["connection_id"]
            saved_connection = next(
                item
                for item in client.get("/api/configs").json()
                if item["id"] == connection_id
            )
            assert saved_connection["models"][0]["model_key"] == "test-model"
            assert saved_connection["models"][0]["supported_efforts"] == ["medium"]
            stale_model = client.post(
                f"/api/connections/{connection_id}/models",
                json={
                    "model_key": "stale-model",
                    "display_name": "过期模型",
                    "supported_efforts": ["medium"],
                },
            )
            assert stale_model.status_code == 201, stale_model.text
            discovered_models = client.post(
                f"/api/connections/{connection_id}/models/discover"
            )
            assert discovered_models.status_code == 200, discovered_models.text
            assert discovered_models.json()["model_keys"] == [
                "review-model",
                "test-model",
            ]
            synced_connection = next(
                item
                for item in client.get("/api/configs").json()
                if item["id"] == connection_id
            )
            assert {item["model_key"] for item in synced_connection["models"]} == {
                "review-model",
                "stale-model",
                "test-model",
            }
            assert not next(
                item
                for item in synced_connection["models"]
                if item["model_key"] == "stale-model"
            )["active"]
            extra_model = client.post(
                f"/api/connections/{connection_id}/models",
                json={
                    "model_key": "risk-model",
                    "display_name": "复核模型",
                    "supported_efforts": ["high"],
                },
            )
            assert extra_model.status_code == 201, extra_model.text
            extra_model_id = extra_model.json()["id"]
            model_validation = client.post(
                f"/api/models/{extra_model_id}/validation-runs"
            )
            assert model_validation.status_code == 201, model_validation.text
            model_validation_id = model_validation.json()["id"]
            deadline = time.time() + 5
            validated_model = {}
            while time.time() < deadline:
                validated_model = client.get(
                    f"/api/validation-runs/{model_validation_id}"
                ).json()
                if validated_model["status"] in {"passed", "failed"}:
                    break
                time.sleep(0.05)
            assert validated_model["status"] == "passed", validated_model
            assert validated_model["items"][0]["http_status"] == 200
            assert validated_model["items"][0]["duration_ms"] >= 0
            failed_model = client.post(
                f"/api/connections/{connection_id}/models",
                json={
                    "model_key": "auth-fail",
                    "display_name": "鉴权失败模型",
                    "supported_efforts": ["medium"],
                },
            )
            assert failed_model.status_code == 201, failed_model.text
            failed_validation = client.post(
                f"/api/models/{failed_model.json()['id']}/validation-runs"
            )
            assert failed_validation.status_code == 201
            failed_validation_id = failed_validation.json()["id"]
            deadline = time.time() + 5
            failed_run = {}
            while time.time() < deadline:
                failed_run = client.get(
                    f"/api/validation-runs/{failed_validation_id}"
                ).json()
                if failed_run["status"] in {"passed", "failed"}:
                    break
                time.sleep(0.05)
            assert failed_run["status"] == "failed", failed_run
            assert failed_run["error_category"] == "authentication"
            assert "API 密钥" in failed_run["suggestion"]
            assert failed_run["items"][0]["http_status"] == 401
            updated_model = client.patch(
                f"/api/models/{extra_model_id}",
                json={
                    "display_name": "风险复核模型",
                    "supported_efforts": ["high"],
                    "active": True,
                },
            )
            assert updated_model.status_code == 200, updated_model.text
            assert updated_model.json()["display_name"] == "风险复核模型"
            model_audit = client.get(f"/api/audit/api_model/{extra_model_id}").json()
            assert {item["action"] for item in model_audit} == {
                "create",
                "update",
                "validate",
            }
            disabled_model = client.patch(
                f"/api/models/{extra_model_id}",
                json={
                    "display_name": "风险复核模型",
                    "supported_efforts": ["high"],
                    "active": False,
                },
            )
            assert disabled_model.status_code == 200, disabled_model.text
            unknown_model_version = client.post(
                "/api/configs",
                json={
                    "connection_id": connection_id,
                    "name": "测试线路",
                    "base_url": f"http://127.0.0.1:{server.server_port}",
                    "api_key": "",
                    "primary_model": "missing-model",
                    "primary_effort": "medium",
                    "cheap_model": None,
                    "secondary_model": None,
                    "change_note": "测试模型列表约束",
                },
            )
            assert unknown_model_version.status_code == 400
            draft_for_discard = client.post(
                "/api/configs",
                json={
                    "connection_id": connection_id,
                    "name": "测试线路",
                    "base_url": f"http://127.0.0.1:{server.server_port}",
                    "api_key": "",
                    "primary_model": "test-model",
                    "primary_effort": "medium",
                    "cheap_model": None,
                    "secondary_model": None,
                    "change_note": "测试放弃草稿",
                },
            )
            assert draft_for_discard.status_code == 201, draft_for_discard.text
            discarded_version_id = draft_for_discard.json()["id"]
            discarded = client.delete(f"/api/configs/{discarded_version_id}")
            assert discarded.status_code == 200, discarded.text
            assert discarded.json()["id"] == discarded_version_id
            connection_after_discard = next(
                item
                for item in client.get("/api/configs").json()
                if item["id"] == connection_id
            )
            assert all(
                item["id"] != discarded_version_id
                for item in connection_after_discard["versions"]
            )
            discard_audit = client.get(
                f"/api/audit/api_connection/{connection_id}"
            ).json()
            assert any(item["action"] == "discard_draft" for item in discard_audit)
            config_validation = client.post(f"/api/configs/{config_id}/validation-runs")
            assert config_validation.status_code == 201, config_validation.text
            config_validation_id = config_validation.json()["id"]
            deadline = time.time() + 5
            validated_config = {}
            while time.time() < deadline:
                validated_config = client.get(
                    f"/api/validation-runs/{config_validation_id}"
                ).json()
                if validated_config["status"] in {"passed", "failed"}:
                    break
                time.sleep(0.05)
            assert validated_config["status"] == "passed", validated_config
            assert validated_config["completed_count"] == 1
            with client.stream(
                "GET",
                f"/api/validation-runs/{config_validation_id}/events",
            ) as validation_stream:
                validation_stream_text = "".join(validation_stream.iter_text())
            assert '"stage": "requesting"' in validation_stream_text
            assert '"stage": "checking"' in validation_stream_text
            assert "event: close" in validation_stream_text
            assert (
                client.get(f"/api/connections/{connection_id}/active-validation").json()
                is None
            )
            assert client.post(f"/api/configs/{config_id}/publish").status_code == 200
            assert client.post(f"/api/configs/{config_id}/publish").status_code == 200
            primary_model = saved_connection["models"][0]
            disabled_primary = client.patch(
                f"/api/models/{primary_model['id']}",
                json={
                    "display_name": "测试主模型",
                    "supported_efforts": ["medium"],
                    "active": False,
                },
            )
            assert disabled_primary.status_code == 200
            assert disabled_primary.json()["active"] is False
            publish_audit = client.get(
                f"/api/audit/api_connection/{config.json()['connection_id']}"
            ).json()
            assert (
                len([item for item in publish_audit if item["action"] == "publish"])
                == 1
            )

            preflight = client.post(
                "/api/tasks/preflight",
                json={
                    "dataset_version_id": returns["version_id"],
                    "product_version_id": products["version_id"],
                    "store": "SEEKWAY:US",
                    "listing": "SK001",
                },
            )
            assert preflight.status_code == 200, preflight.text
            assert preflight.json()["blocked_count"] == 0
            stale_plan = client.post(
                "/api/tasks",
                json={
                    "title": "过期计划",
                    "dataset_version_id": returns["version_id"],
                    "product_version_id": products["version_id"],
                    "store": "SEEKWAY:US",
                    "listing": "SK001",
                    "plan_hash": "0" * 64,
                    "unresolved_policy": "run_ready",
                },
            )
            assert stale_plan.status_code == 409

            task = client.post(
                "/api/tasks",
                json={
                    "title": "SK001 真实分析",
                    "dataset_version_id": returns["version_id"],
                    "product_version_id": products["version_id"],
                    "store": "SEEKWAY:US",
                    "listing": "SK001",
                    "plan_hash": preflight.json()["plan_hash"],
                    "unresolved_policy": "run_ready",
                },
            )
            assert task.status_code == 201, task.text
            task_id = task.json()["id"]

            deadline = time.time() + 15
            current = {}
            while time.time() < deadline:
                current = client.get(f"/api/tasks/{task_id}").json()
                if current["status"] in {"completed", "failed"}:
                    break
                time.sleep(0.1)
            assert current["status"] == "completed", current
            assert current["progress_percent"] == 100
            assert current["metrics"]["top_problem_labels"][0]["name"] == "偏大"
            assert current["metrics"]["category_registry_version"] == (
                "category-capabilities-2026-08-10-v1"
            )
            category_segment = current["metrics"]["category_segments"][0]
            assert category_segment["agent_family"] == "鞋履智能体"
            assert category_segment["logic_version"] == (
                "footwear-semantic-2026-08-10-v1"
            )
            assert category_segment["record_count"] == 1
            assert category_segment["model_calls"] == 2
            assert category_segment["claims_version"] == ("sk001-listing-2026-08-05-v1")
            assert category_segment["model_policy_version"] == (
                "footwear-model-policy-2026-08-10-v1"
            )
            assert category_segment["cache_hits"] == 0
            assert category_segment["status"] == "completed"
            assert current["segments"][0]["status"] == "completed"
            assert current["segments"][0]["model_calls"] == 2
            assert client.get(f"/api/tasks/{task_id}/download").status_code == 200
            analysis = client.get(f"/api/tasks/{task_id}/analysis")
            assert analysis.status_code == 200, analysis.text
            analysis_payload = analysis.json()
            assert analysis_payload["scope"] == {
                "total_records": 1,
                "filtered_records": 1,
            }
            assert analysis_payload["filters"]["listings"] == ["SK001"]
            assert analysis_payload["overview"]["metrics"]["text_records"] == 1
            assert analysis_payload["quality_gate"]["status"] == "ready"
            assert analysis_payload["quality_gate"]["labeled_records"] == 1
            assert analysis_payload["diagnosis"]["priorities"][0]["name"] == "偏大"
            assert analysis_payload["products"]["summary"][0]["name"] == "SK001"
            assert analysis_payload["details"]["records"][0]["sku"] == "SKU-1"
            overview_only = client.get(
                f"/api/tasks/{task_id}/analysis",
                params={"view": "overview"},
            ).json()
            assert overview_only["view"] == "overview"
            assert "top_problems" in overview_only["overview"]
            assert "diagnosis" not in overview_only
            assert "products" not in overview_only
            assert (
                settings.data_dir / "results" / task_id / "analysis-v1.web-cache.pkl"
            ).exists()
            filtered_download = client.get(
                f"/api/tasks/{task_id}/analysis/download",
                params={
                    "problem_code": analysis_payload["diagnosis"]["focus_code"],
                },
            )
            assert filtered_download.status_code == 200
            assert filtered_download.headers["content-type"].startswith(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            with client.stream(
                "GET",
                f"/api/tasks/{task_id}/events",
                headers={"Last-Event-ID": "999999999"},
            ) as stream:
                stream_text = "".join(stream.iter_text())
            assert "event: task" not in stream_text
            assert "event: close" in stream_text

            reviews = client.get(
                "/api/reviews",
                params={"task_id": task_id},
            ).json()
            assert reviews == []
            base_version_id = current["segments"][0]["result_version_id"]
            batch_response = client.post(
                f"/api/classification-results/{base_version_id}/review-batches",
                json={"reason": "创建复核批次"},
            )
            assert batch_response.status_code == 201, batch_response.text
            batch = batch_response.json()
            batch_records = client.get(
                f"/api/review-batches/{batch['id']}/records"
            ).json()
            assert batch_records["total"] == 1
            review = batch_records["items"][0]
            resolved = client.patch(
                f"/api/review-batches/{batch['id']}/records/{review['id']}",
                json={
                    "expected_revision": review["revision"],
                    "label_code": "FIT_TOO_SMALL",
                    "reason": "人工确认标签",
                },
            )
            assert resolved.status_code == 200, resolved.text
            assert resolved.json()["classification"]["status"] == "MANUAL_RESOLVED"
            stale = client.patch(
                f"/api/review-batches/{batch['id']}/records/{review['id']}",
                json={
                    "expected_revision": review["revision"],
                    "label_code": "FIT_TOO_LARGE",
                    "reason": "重复提交",
                },
            )
            assert stale.status_code == 409
            current_batch = client.get(
                f"/api/review-batches/{batch['id']}"
            ).json()
            published = client.post(
                f"/api/review-batches/{batch['id']}/publish",
                json={
                    "expected_revision": current_batch["revision"],
                    "reason": "发布复核结果",
                },
            )
            assert published.status_code == 200, published.text
            history = client.get(
                f"/api/classification-results/{base_version_id}/versions"
            ).json()
            assert [item["version"] for item in history] == [2, 1]
            collaborator = client.post(
                "/api/users",
                json={
                    "email": "collaborator@example.com",
                    "display_name": "协作者",
                    "password": "collaborator-password-123",
                },
            )
            assert collaborator.status_code == 201
            user_audit = client.get(
                f"/api/audit/user/{collaborator.json()['id']}"
            ).json()
            assert user_audit[0]["action"] == "create"
            assert user_audit[0]["actor_name"] == "管理员"
            self_deactivate = client.patch(
                f"/api/users/{admin_id}",
                json={
                    "active": False,
                    "expected_active": True,
                    "note": "不应允许停用自己",
                },
            )
            assert self_deactivate.status_code == 400
            collaborator_id = collaborator.json()["id"]
            deactivated = client.patch(
                f"/api/users/{collaborator_id}",
                json={
                    "active": False,
                    "expected_active": True,
                    "note": "协作者暂时离岗",
                },
            )
            assert deactivated.status_code == 200
            assert deactivated.json()["active"] == 0
            stale_status = client.patch(
                f"/api/users/{collaborator_id}",
                json={
                    "active": True,
                    "expected_active": True,
                    "note": "使用了过期页面",
                },
            )
            assert stale_status.status_code == 409
            reactivated = client.patch(
                f"/api/users/{collaborator_id}",
                json={
                    "active": True,
                    "expected_active": False,
                    "note": "协作者恢复工作",
                },
            )
            assert reactivated.status_code == 200
            collaborator_audit = client.get(f"/api/audit/user/{collaborator_id}").json()
            assert collaborator_audit[0]["action"] == "activate"
            assert collaborator_audit[0]["before"] == {"active": False}
            assert collaborator_audit[0]["after"] == {
                "active": True,
                "note": "协作者恢复工作",
            }
            users = client.get("/api/users").json()
            collaborator_user = next(
                item for item in users if item["id"] == collaborator_id
            )
            assert collaborator_user["audit"][0]["after"]["note"] == ("协作者恢复工作")
            for index in range(2, 5):
                created = client.post(
                    "/api/users",
                    json={
                        "email": f"user{index}@example.com",
                        "display_name": f"用户 {index}",
                        "password": f"user-{index}-password-123",
                    },
                )
                assert created.status_code == 201
            over_limit = client.post(
                "/api/users",
                json={
                    "email": "user5@example.com",
                    "display_name": "用户 5",
                    "password": "user-5-password-123",
                },
            )
            assert over_limit.status_code == 409
            assert client.post("/api/auth/logout").status_code == 204
            assert (
                client.post(
                    "/api/auth/login",
                    json={
                        "email": "collaborator@example.com",
                        "password": "collaborator-password-123",
                    },
                ).status_code
                == 200
            )
            before_rename = client.get(f"/api/tasks/{task_id}").json()
            renamed = client.patch(
                f"/api/tasks/{task_id}",
                json={
                    "expected_revision": before_rename["revision"],
                    "title": "协作者修订后的分析任务",
                    "note": "统一任务命名",
                },
            )
            assert renamed.status_code == 200, renamed.text
            assert renamed.json()["title"] == "协作者修订后的分析任务"
            assert renamed.json()["owner_name"] == "管理员"
            stale_rename = client.patch(
                f"/api/tasks/{task_id}",
                json={
                    "expected_revision": before_rename["revision"],
                    "title": "过期修改",
                    "note": "模拟版本冲突",
                },
            )
            assert stale_rename.status_code == 409
            task_audit = client.get(f"/api/audit/task/{task_id}").json()
            assert task_audit[0]["action"] == "rename"
            assert task_audit[0]["actor_name"] == "协作者"
            assert task_audit[0]["before"]["title"] == "SK001 真实分析"
            assert task_audit[0]["after"]["title"] == "协作者修订后的分析任务"
            assert task_audit[0]["after"]["note"] == "统一任务命名"
            retried = client.post(f"/api/tasks/{task_id}/retry")
            assert retried.status_code == 201
            assert retried.json()["owner_name"] == "协作者"
            assert retried.json()["dataset_version_id"] == returns["version_id"]
            assert retried.json()["product_version_id"] == products["version_id"]
            task_audit = client.get(f"/api/audit/task/{task_id}").json()
            assert task_audit[0]["action"] == "retry"
            assert task_audit[0]["after"]["new_task_id"] == retried.json()["id"]
            assert client.post("/api/auth/logout").status_code == 204
            assert (
                client.post(
                    "/api/auth/login",
                    json={
                        "email": "admin@example.com",
                        "password": "test-password-123",
                    },
                ).status_code
                == 200
            )
            changed_password = client.post(
                "/api/auth/password",
                json={
                    "current_password": "test-password-123",
                    "new_password": "new-test-password-456",
                },
            )
            assert changed_password.status_code == 204
            assert client.get("/api/auth/me").status_code == 401
            assert (
                client.post(
                    "/api/auth/login",
                    json={
                        "email": "admin@example.com",
                        "password": "new-test-password-456",
                    },
                ).status_code
                == 200
            )
    finally:
        server.shutdown()
        server.server_close()


def test_login_is_rate_limited(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "runtime",
        database_path=tmp_path / "runtime" / "app.db",
        session_days=14,
        task_workers=1,
        bootstrap_email="admin@example.com",
        bootstrap_name="管理员",
        bootstrap_password="test-password-123",
        encryption_key=Fernet.generate_key().decode("ascii"),
        secure_cookies=False,
    )
    app = create_app(start_worker=False, settings_override=settings)

    with TestClient(app) as client:
        for _ in range(5):
            response = client.post(
                "/api/auth/login",
                json={
                    "email": "admin@example.com",
                    "password": "wrong-password",
                },
            )
            assert response.status_code == 401

        blocked = client.post(
            "/api/auth/login",
            json={
                "email": "admin@example.com",
                "password": "test-password-123",
            },
        )
        assert blocked.status_code == 429
        assert int(blocked.headers["Retry-After"]) > 0


def test_health_fails_when_worker_stops(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "runtime",
        database_path=tmp_path / "runtime" / "app.db",
        session_days=14,
        task_workers=1,
        bootstrap_email="admin@example.com",
        bootstrap_name="管理员",
        bootstrap_password="test-password-123",
        encryption_key=Fernet.generate_key().decode("ascii"),
        secure_cookies=False,
    )
    app = create_app(start_worker=True, settings_override=settings)

    with TestClient(app) as client:
        app.state.worker.stop()
        response = client.get("/api/health")
        assert response.status_code == 503
        assert response.json()["detail"]["worker"] == "unavailable"


def test_production_settings_reject_development_defaults(monkeypatch) -> None:
    monkeypatch.setenv("WEBAPP_PRODUCTION", "true")
    monkeypatch.delenv("WEBAPP_BOOTSTRAP_PASSWORD", raising=False)
    monkeypatch.delenv("WEBAPP_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("WEBAPP_SECURE_COOKIES", raising=False)

    with pytest.raises(ValueError, match="生产环境"):
        Settings.from_env()


def test_production_settings_accept_secure_values(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("WEBAPP_PRODUCTION", "true")
    monkeypatch.setenv("WEBAPP_DATA_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("WEBAPP_BOOTSTRAP_PASSWORD", "strong-password-123")
    monkeypatch.setenv(
        "WEBAPP_ENCRYPTION_KEY",
        Fernet.generate_key().decode("ascii"),
    )
    monkeypatch.setenv("WEBAPP_SECURE_COOKIES", "true")

    settings = Settings.from_env()

    assert settings.production is True
    assert settings.secure_cookies is True


def test_production_settings_require_full_team_listing_capacity(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("WEBAPP_PRODUCTION", "true")
    monkeypatch.setenv("WEBAPP_DATA_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("WEBAPP_BOOTSTRAP_PASSWORD", "strong-password-123")
    monkeypatch.setenv(
        "WEBAPP_ENCRYPTION_KEY",
        Fernet.generate_key().decode("ascii"),
    )
    monkeypatch.setenv("WEBAPP_SECURE_COOKIES", "true")
    monkeypatch.setenv("WEBAPP_TASK_WORKERS", "14")

    with pytest.raises(ValueError, match="15 个 Listing 槽位"):
        Settings.from_env()


def test_production_app_starts_with_secure_session(
    tmp_path: Path,
) -> None:
    settings = Settings(
        data_dir=tmp_path / "runtime",
        database_path=tmp_path / "runtime" / "app.db",
        session_days=14,
        task_workers=15,
        bootstrap_email="admin@example.com",
        bootstrap_name="系统管理员",
        bootstrap_password="strong-production-password",
        encryption_key=Fernet.generate_key().decode("ascii"),
        secure_cookies=True,
        production=True,
    )
    settings.validate()
    app = create_app(start_worker=False, settings_override=settings)

    with TestClient(app, base_url="https://testserver") as client:
        health = client.get("/api/health")
        login = client.post(
            "/api/auth/login",
            json={
                "email": "admin@example.com",
                "password": "strong-production-password",
            },
        )
        current_user = client.get("/api/auth/me")

    assert health.status_code == 200
    assert login.status_code == 200
    assert "Secure" in login.headers["set-cookie"]
    assert current_user.status_code == 200
