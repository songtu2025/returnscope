from copy import deepcopy
from typing import Any

import pytest
from insight_report_helpers import legacy_evidence

from web_backend.insight_report_legacy_blueprint import _build_blueprint
from web_backend.insight_report_service import InsightReportService


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
