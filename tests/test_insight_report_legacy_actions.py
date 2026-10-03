import pytest
from insight_report_helpers import legacy_evidence

from web_backend.insight_report_profiles import get_insight_report_profile
from web_backend.insight_reports.legacy_actions import _build_actions
from web_backend.insight_reports.legacy_findings import (
    _build_diagnostic_finding,
    _select_reasons,
)


@pytest.mark.parametrize("mapping_issue", [False, True])
@pytest.mark.parametrize("text_issue", [False, True])
def test_quality_actions_preserve_order_and_block_untrusted_mapping(
    mapping_issue: bool, text_issue: bool
) -> None:
    evidence = legacy_evidence(mapping_issue=mapping_issue, text_issue=text_issue)
    reasons, _ = _select_reasons(
        evidence["analysis"]["reasons"], get_insight_report_profile("footwear")
    )
    _, ids, targets = _build_diagnostic_finding(evidence, reasons)
    actions = _build_actions(evidence, reasons, ids, targets, (None, []))
    by_id = {action["id"]: action for action in actions}
    assert ("action.diagnostic" in by_id) is not mapping_issue
    assert ("action.mapping" in by_id) is mapping_issue
    assert ("action.text_quality" in by_id) is text_issue
    if mapping_issue:
        assert actions[0]["id"] == "action.mapping"
        assert by_id["action.mapping"]["evidence_ids"] == ["product_mapping", "scope"]
    if text_issue:
        assert "编码异常" in by_id["action.text_quality"]["fallback_rationale"]
    assert actions[-1]["id"] == "action.scope"


def test_diagnostic_action_deduplicates_evidence_and_keeps_case_target() -> None:
    evidence = legacy_evidence()
    reasons = evidence["analysis"]["reasons"]
    _, ids, targets = _build_diagnostic_finding(evidence, reasons)
    actions = _build_actions(evidence, reasons, [*ids, *ids], targets, (None, []))
    action = next(item for item in actions if item["id"] == "action.diagnostic")
    assert action["target"] == "TEST-SKU"
    assert action["evidence_ids"] == list(dict.fromkeys(action["evidence_ids"]))
    assert "issue_case.FIT_TOO_SMALL.test" in action["evidence_ids"]
    assert "不能单凭反馈结构推断原因" in action["fallback_rationale"]


def test_scope_action_is_preserved_without_actionable_reasons() -> None:
    evidence = legacy_evidence(context="user_feedback")
    actions = _build_actions(evidence, [], [], [], (None, []))
    assert [item["id"] for item in actions] == ["action.scope"]
    assert actions[0]["priority"] == "P2"
    assert "总体发生率" in actions[0]["fallback_rationale"]


def test_broad_reason_keeps_information_action_before_scope() -> None:
    evidence = legacy_evidence()
    reason = {"label": "宽泛原因"}
    actions = _build_actions(evidence, [], [], [], (reason, ["reason.BROAD"]))
    assert [item["id"] for item in actions] == ["action.information", "action.scope"]
    assert actions[0]["evidence_ids"] == ["reason.BROAD"]
    assert actions[0]["finding_id"] == "finding.information"
