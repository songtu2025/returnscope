from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from test_review_dashboard_report_lifecycle import _prepare_item_operation
from test_review_dashboard_report_lifecycle import lifecycle as lifecycle

from web_backend.database import Database
from web_backend.security import SecretBox, hash_password
from web_backend.settings import Settings

SYNTHETIC_PASSWORD = "synthetic-http-test-password"


@pytest.fixture
def http_lifecycle(
    lifecycle: SimpleNamespace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> SimpleNamespace:
    settings = Settings(
        data_dir=tmp_path,
        database_path=lifecycle.database.path,
        session_days=14,
        task_workers=1,
        bootstrap_email="admin@example.test",
        bootstrap_name="合成测试管理员",
        bootstrap_password=SYNTHETIC_PASSWORD,
        encryption_key=Fernet.generate_key().decode("ascii"),
        secure_cookies=False,
    )
    with lifecycle.database.transaction() as connection:
        connection.execute(
            "UPDATE users SET password_hash = ?, is_admin = 0 WHERE id = 'user-1'",
            (hash_password(SYNTHETIC_PASSWORD),),
        )
        connection.execute(
            "UPDATE api_config_versions SET api_key_ciphertext = ?",
            (SecretBox(settings.encryption_key).encrypt("synthetic-model-key"),),
        )
    # 模块默认应用也使用隔离配置，避免首次导入读取项目环境文件。
    monkeypatch.setattr(Settings, "from_env", classmethod(lambda cls: settings))
    from web_backend.app import create_app

    def open_client() -> TestClient:
        app = create_app(start_worker=False, settings_override=settings)
        # 仅替换外部模型，保留正式登录、路由、服务和数据库实现。
        app.state.insight_report_service.client_factory = (
            lifecycle.reports.client_factory
        )
        return TestClient(app)

    return SimpleNamespace(state=lifecycle, open_client=open_client)


def _request(
    client: TestClient, method: str, path: str, status: int = 200, **kwargs: Any
) -> Any:
    response = client.request(method, path, **kwargs)
    assert response.status_code == status, response.text
    return response.json()


def _login(client: TestClient) -> None:
    _request(
        client,
        "POST",
        "/api/auth/login",
        json={"email": "one@example.com", "password": SYNTHETIC_PASSWORD},
    )


def _publish_operation(
    client: TestClient, state: SimpleNamespace, operation: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    record, details, _ = _prepare_item_operation(state, operation)
    batch_path = f"/api/review-batches/{state.batch['id']}"
    base_snapshot = _request(
        client,
        "GET",
        f"/api/classification-results/{state.base['version_id']}/records",
    )
    _request(
        client,
        "PATCH",
        f"{batch_path}/records/{record['id']}",
        json={
            "expected_revision": record["revision"],
            "action": "confirm",
            "reason": "合成 HTTP 逐项处置",
            **details,
        },
    )
    batch = _request(client, "GET", batch_path)
    derived = _request(
        client,
        "POST",
        f"{batch_path}/publish",
        json={"expected_revision": batch["revision"], "reason": "发布合成处置"},
    )
    return derived, base_snapshot


def _create_dashboard_report(
    client: TestClient, state: SimpleNamespace, derived: dict[str, Any]
) -> dict[str, str]:
    scope = {"result_version_ids": [derived["version_id"]], "filters": {}}
    plan = _request(client, "POST", "/api/dashboard-plans/preflight", json=scope)
    assert plan["ready"] is True
    assert plan["summary"]["pending_review_comment_count"] == 0
    dashboard = _request(
        client,
        "POST",
        f"/api/analysis-dashboards/{state.dashboard['id']}/versions",
        201,
        json={
            **scope,
            "expected_revision": state.dashboard["revision"],
            "plan_hash": plan["plan_hash"],
            "reason": "使用人工处置结果",
        },
    )
    dashboard_id = dashboard["id"]
    dashboard_version_id = dashboard["version"]["version_id"]
    queued = _request(
        client,
        "POST",
        f"/api/analysis-dashboards/{dashboard_id}/versions/"
        f"{dashboard_version_id}/ai-insight-reports",
        201,
        json={"model_id": "model-1", "reasoning_effort": "high"},
    )
    # 执行与后台工作器相同的领任务和运行入口，不替换报告业务逻辑。
    reports = client.app.state.insight_report_service
    assert reports.claim_next() == queued["id"]
    reports.run(queued["id"])
    return {
        "result_id": derived["version_id"],
        "dashboard_id": dashboard_id,
        "dashboard_version_id": dashboard_version_id,
        "report_id": queued["id"],
    }


def _published_snapshot(client: TestClient, ids: dict[str, str]) -> dict[str, Any]:
    dashboard_path = f"/api/analysis-dashboards/{ids['dashboard_id']}"
    version_path = f"{dashboard_path}/versions/{ids['dashboard_version_id']}"
    paths = {
        "result": f"/api/classification-results/{ids['result_id']}",
        "records": f"/api/classification-results/{ids['result_id']}/records",
        "dashboard": f"{dashboard_path}?version_id={ids['dashboard_version_id']}",
        "summary": f"{version_path}/summary",
        "sources": f"{version_path}/sources",
        "dashboard_records": f"{version_path}/records",
        "report": f"/api/ai-insight-reports/{ids['report_id']}",
        "report_list": (
            f"{dashboard_path}/ai-insight-reports"
            f"?version_id={ids['dashboard_version_id']}"
        ),
    }
    return {key: _request(client, "GET", path) for key, path in paths.items()}


@pytest.mark.parametrize(
    "operation",
    [
        "remove",
        "no_tag_needed",
        "add",
        "unknown",
        "diagnostic_change",
        "diagnostic_no_tag",
    ],
)
def test_item_operations_survive_http_publication_and_app_restart(
    http_lifecycle: SimpleNamespace, operation: str
) -> None:
    state = http_lifecycle.state
    base_path = f"/api/classification-results/{state.base['version_id']}/records"
    with http_lifecycle.open_client() as client:
        _login(client)
        derived, base_snapshot = _publish_operation(client, state, operation)
        assert _request(client, "GET", base_path) == base_snapshot
        ids = _create_dashboard_report(client, state, derived)
        snapshot = _published_snapshot(client, ids)
        _assert_published_scope(snapshot, ids, operation)
        before_retry = _write_snapshot(state.database)
        batch_path = f"/api/review-batches/{state.batch['id']}"
        batch = _request(client, "GET", batch_path)
        _request(
            client,
            "POST",
            f"{batch_path}/publish",
            409,
            json={"expected_revision": batch["revision"], "reason": "重复发布"},
        )
        assert _write_snapshot(state.database) == before_retry
    # 重新构造正式应用和所有服务，确认结果来自持久化数据。
    with http_lifecycle.open_client() as restarted:
        _login(restarted)
        assert _published_snapshot(restarted, ids) == snapshot
        assert _request(restarted, "GET", base_path) == base_snapshot
        batch = _request(restarted, "GET", f"/api/review-batches/{state.batch['id']}")
        assert batch["published_version_id"] == ids["result_id"]


def _assert_published_scope(
    snapshot: dict[str, Any], ids: dict[str, str], operation: str
) -> None:
    codes = (
        {"FIT_TOO_SMALL_U1", "FIT_TOO_LARGE_U1"}
        if operation == "add"
        else {"FIT_TOO_LARGE_U1"}
        if operation in {"unknown", "diagnostic_change"}
        else set()
    )
    classification = snapshot["records"]["items"][0]["classification"]
    assert {unit["label_code"] for unit in classification["semantic_units"]} == codes
    assert snapshot["result"]["version"] == 2
    assert snapshot["result"]["changed_unit_count"] == 1
    assert snapshot["summary"]["record_count"] == 2
    assert snapshot["summary"]["review_changed_unit_count"] == 1
    assert {
        unit["label_code"]
        for record in snapshot["dashboard_records"]["items"]
        for unit in record["classification"]["semantic_units"]
    } == codes
    assert {source["result_version_id"] for source in snapshot["sources"]} == {
        ids["result_id"]
    }
    report = snapshot["report"]
    assert report["status"] == "completed", report["error"]
    assert report["dashboard_version_id"] == ids["dashboard_version_id"]
    assert (
        report["evidence"]["source"]["dashboard_version_id"]
        == (ids["dashboard_version_id"])
    )
    assert {
        key.removeprefix("reason.")
        for key in report["evidence"]["catalog"]
        if key.startswith("reason.")
    } == codes
    assert [item["id"] for item in snapshot["report_list"]] == [report["id"]]


def _write_snapshot(database: Database) -> dict[str, list[tuple[Any, ...]]]:
    tables = (
        "review_records",
        "review_revisions",
        "review_batches",
        "classification_result_versions",
        "classification_units",
        "dashboard_versions",
        "ai_insight_reports",
        "ai_insight_report_versions",
    )
    with database.connect() as connection:
        return {
            table: [tuple(row) for row in connection.execute(f"SELECT * FROM {table}")]
            for table in tables
        }


def _audit_snapshot(database: Database) -> list[dict[str, Any]]:
    with database.connect() as connection:
        return [
            dict(row)
            for row in connection.execute("SELECT * FROM audit_logs ORDER BY rowid")
        ]


@pytest.mark.parametrize(
    "failure,status",
    [
        ("invalid_direction", 422),
        ("disallowed_direction", 400),
        ("missing_direction", 400),
        ("changed_existing_direction", 400),
        ("stale_record", 409),
        ("pending_publish", 409),
        ("stale_publish", 409),
    ],
)
def test_rejected_http_review_preserves_all_related_rows(
    http_lifecycle: SimpleNamespace, failure: str, status: int
) -> None:
    state = http_lifecycle.state
    record = state.reviews.batch_records(state.batch["id"])["items"][0]
    batch_path = f"/api/review-batches/{state.batch['id']}"
    with http_lifecycle.open_client() as client:
        _login(client)
        before = _write_snapshot(state.database)
        audit_before = _audit_snapshot(state.database)
        if failure in {"pending_publish", "stale_publish"}:
            body = {
                "expected_revision": state.batch["revision"]
                + int(failure == "stale_publish"),
                "reason": "合成无效发布",
            }
            _request(client, "POST", f"{batch_path}/publish", status, json=body)
        else:
            body = _invalid_record_body(record, failure)
            _request(
                client,
                "PATCH",
                f"{batch_path}/records/{record['id']}",
                status,
                json=body,
            )
        assert _write_snapshot(state.database) == before
        audit_after = _audit_snapshot(state.database)
        if status == 409:
            # 冲突只追加审计事件，不能更新业务数据或创建下游版本。
            assert audit_after[:-1] == audit_before
            assert audit_after[-1]["action"] == "conflict"
            assert audit_after[-1]["actor_id"] == "user-1"
            assert audit_after[-1]["entity_id"] == state.batch["id"]
        else:
            assert audit_after == audit_before


def _invalid_record_body(record: dict[str, Any], failure: str) -> dict[str, Any]:
    body: dict[str, Any] = {
        "expected_revision": record["revision"] + int(failure == "stale_record"),
        "reason": "合成无效请求",
    }
    if failure == "changed_existing_direction":
        item = record["classification"]["semantic_review"]["semantic_items"][0]
        body["semantic_item_reviews"] = [
            {
                "semantic_item_id": item["item_id"],
                "action": "change_label",
                "label_code": "FIT_TOO_LARGE_U1",
                "sentiment": "POSITIVE",
            }
        ]
    elif failure != "stale_record":
        added = {
            "evidence_text": record["comment"],
            "opinion": "合成补录观点",
            "label_code": (
                "SIZE_AVAILABILITY_U1"
                if failure == "missing_direction"
                else "FIT_TOO_LARGE_U1"
            ),
        }
        if failure != "missing_direction":
            added["sentiment"] = (
                "INVALID" if failure == "invalid_direction" else "POSITIVE"
            )
        body["added_semantic_items"] = [added]
    return body


def test_http_review_keeps_explicit_direction_in_draft_and_published_result(
    http_lifecycle: SimpleNamespace,
) -> None:
    state = http_lifecycle.state
    record = state.reviews.batch_records(state.batch["id"])["items"][0]
    batch_path = f"/api/review-batches/{state.batch['id']}"
    with http_lifecycle.open_client() as client:
        _login(client)
        saved = _request(
            client,
            "PATCH",
            f"{batch_path}/records/{record['id']}",
            json={
                "expected_revision": record["revision"],
                "reason": "补录合成正向观点",
                "added_semantic_items": [
                    {
                        "evidence_text": record["comment"],
                        "opinion": "合成正向观点",
                        "label_code": "SIZE_AVAILABILITY_U1",
                        "sentiment": "POSITIVE",
                    }
                ],
            },
        )
        assert (
            saved["classification"]["human_added_semantic_items"][0]["sentiment"]
            == "POSITIVE"
        )
    with http_lifecycle.open_client() as client:
        _login(client)
        reloaded = _request(client, "GET", f"/api/reviews/{record['id']}")
        assert reloaded == saved
        batch = _request(client, "GET", batch_path)
        derived = _request(
            client,
            "POST",
            f"{batch_path}/publish",
            json={"expected_revision": batch["revision"], "reason": "发布方向校验结果"},
        )
        classification = _request(
            client,
            "GET",
            f"/api/classification-results/{derived['version_id']}/records",
        )["items"][0]["classification"]
        assert classification["semantic_units"][-1]["sentiment"] == "POSITIVE"
        assert classification["comment_summary"]["status"] == "MIXED"
        ids = _create_dashboard_report(client, state, derived)
        snapshot = _published_snapshot(client, ids)
        report = snapshot["report"]
        assert report["status"] == "completed", report["error"]
        assert {
            key.removeprefix("reason.")
            for key in report["evidence"]["catalog"]
            if key.startswith("reason.")
        } == {"FIT_TOO_SMALL_U1"}
