from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from insight_report_helpers import legacy_evidence
from test_insight_reports import _report_payload, _service_context

from web_backend.insight_report_contracts import V5_PROMPT_VERSION
from web_backend.insight_report_legacy_blueprint import _build_blueprint
from web_backend.insight_report_service import InsightReportService
from web_backend.routers.insight_reports import create_insight_report_router


@pytest.mark.parametrize("context", ["returns", "user_feedback"])
@pytest.mark.parametrize("profile", ["footwear", "gloves", "generic"])
@pytest.mark.parametrize("mapping_issue", [False, True])
@pytest.mark.parametrize("text_issue", [False, True])
@pytest.mark.parametrize("provisional", [False, True])
def test_legacy_report_preserves_scope_priority_and_input(
    context: str,
    profile: str,
    mapping_issue: bool,
    text_issue: bool,
    provisional: bool,
) -> None:
    evidence = legacy_evidence(context, profile, mapping_issue, text_issue, provisional)
    before = deepcopy(evidence)
    report = _build_blueprint(evidence)
    subject = "退货问题" if context == "returns" else "用户反馈问题"
    assert report["title"] == (
        f"TEST-LISTING {subject}{'临时' if provisional else ''}诊断报告"
    )
    assert [item["id"] for item in report["executive_summary"]] == [
        "summary.1",
        "summary.2",
        "summary.3",
    ]
    assert report["executive_summary"][2]["tone"] == (
        "warning" if provisional else "neutral"
    )
    expected = ["action.mapping"] if mapping_issue else ["action.diagnostic"]
    if text_issue:
        expected.append("action.text_quality")
    expected.append("action.scope")
    assert [action["id"] for action in report["actions"]] == expected
    assert report["findings"][0]["id"] == "finding.structure"
    assert report["findings"][1]["id"] == "finding.diagnostic"
    assert evidence == before
    assert InsightReportService._build_blueprint(evidence) == report


@pytest.mark.parametrize("listings", [[], ["ONE"], ["ONE", "TWO"]])
def test_legacy_report_preserves_listing_title(listings: list[str]) -> None:
    evidence = legacy_evidence()
    evidence["source"]["listings"] = listings
    report = _build_blueprint(evidence)
    scope = (
        listings[0]
        if len(listings) == 1
        else "2 个 Listing"
        if listings
        else "当前范围"
    )
    assert report["title"] == f"{scope} 退货问题诊断报告"


@pytest.mark.parametrize("pending", ["bad", []])
def test_legacy_report_preserves_invalid_pending_result(pending: Any) -> None:
    evidence = legacy_evidence()
    evidence["source"]["pending_review_record_count"] = pending
    if pending:
        with pytest.raises(ValueError):
            _build_blueprint(evidence)
    else:
        assert (
            "无待审核记录"
            in _build_blueprint(evidence)["executive_summary"][2]["statement"]
        )


@pytest.mark.parametrize("model_failed", [False, True])
def test_legacy_report_api_generation_and_retry(
    tmp_path: Path, model_failed: bool
) -> None:
    context, dashboard, service, _ = _service_context(
        tmp_path,
        client_payload=_report_payload(),
        client_error="合成模型失败" if model_failed else None,
    )
    app = FastAPI()
    app.include_router(create_insight_report_router(service, lambda: {"id": "user-1"}))
    with TestClient(app) as client:
        response = client.post(
            f"/api/analysis-dashboards/{dashboard['id']}/versions/"
            f"{dashboard['version']['version_id']}/ai-insight-reports",
            json={"model_id": "model-1", "reasoning_effort": "high"},
        )
        assert response.status_code == 201
        report_id = response.json()["id"]
        # 在隔离数据库模拟既有 V5 排队任务，模型请求由现有替身处理。
        with context.database.transaction() as connection:
            connection.execute(
                "UPDATE ai_insight_reports SET prompt_version=? WHERE id=?",
                (V5_PROMPT_VERSION, report_id),
            )
        assert service.claim_next() == report_id
        service.run(report_id)
        result = client.get(f"/api/ai-insight-reports/{report_id}")
        assert result.status_code == 200
        payload = result.json()
        assert payload["prompt_version"] == V5_PROMPT_VERSION
        if model_failed:
            assert payload["status"] == "failed"
            assert payload["version_no"] is None
            retried = client.post(f"/api/ai-insight-reports/{report_id}/retry")
            assert retried.status_code == 200
            assert retried.json()["id"] != report_id
            assert retried.json()["status"] == "queued"
            assert retried.json()["attempt_no"] == 2
            assert service.get(report_id)["status"] == "failed"
        else:
            assert payload["status"] == "completed"
            assert payload["content"]["title"] == "L1 退货问题诊断报告"
            summaries = payload["content"]["executive_summary"]
            assert [item["title"] for item in summaries] == [
                "最明确的问题分化",
                "优先验证对象",
                "结论可信边界",
            ]
            assert summaries[2]["evidence_ids"] == ["scope", "review_bias"]
            assert all("id" not in item for item in summaries)
            assert "issues" not in payload["content"]
