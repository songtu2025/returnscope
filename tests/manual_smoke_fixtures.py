"""当前人工修正的隔离 HTTP 烟测辅助函数。"""

from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient
from test_review_http_lifecycle import SYNTHETIC_PASSWORD

from web_backend.database import Database


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


def _create_dashboard_report(
    client: TestClient, state: SimpleNamespace, derived: dict[str, Any]
) -> dict[str, str]:
    state.dashboard = _request(
        client, "GET", "/api/analysis-dashboards/" + state.dashboard["id"]
    )
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


def _publish_operation(client, state, operation):
    base_id = state.base["version_id"]
    base_snapshot = _request(
        client, "GET", f"/api/classification-results/{base_id}/records"
    )
    with state.database.connect() as connection:
        orders = [
            row[0]
            for row in connection.execute(
                "SELECT DISTINCT order_id FROM classification_result_records WHERE result_version_id=?",
                (base_id,),
            )
        ]
    current = state.base
    for order_id in orders:
        with state.database.connect() as connection:
            record = connection.execute(
                "SELECT id,comment FROM classification_result_records WHERE result_version_id=? AND order_id=? LIMIT 1",
                (current["version_id"], order_id),
            ).fetchone()
        items = (
            []
            if operation == "remove"
            else [
                {
                    "evidence_text": record["comment"],
                    "opinion": "合成人工确认",
                    "label_code": "FIT_TOO_SMALL_U1",
                    "sentiment": "NEGATIVE",
                }
            ]
        )
        current = _request(
            client,
            "PATCH",
            f"/api/classification-results/{current['version_id']}/records/{record['id']}/semantics",
            json={"semantic_items": items},
        )
    return current, base_snapshot
