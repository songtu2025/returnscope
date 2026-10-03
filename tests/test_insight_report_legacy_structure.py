import pytest
from insight_report_helpers import legacy_evidence

from web_backend.insight_report_profiles import get_insight_report_profile
from web_backend.insight_reports.legacy_structure import (
    _build_caveats,
    _build_structure_section,
)


@pytest.mark.parametrize("context", ["returns", "user_feedback"])
def test_empty_structure_preserves_context_language(context: str) -> None:
    section = _build_structure_section(
        {"analysis_context": context, "included_record_count": 7},
        {},
        get_insight_report_profile("unknown"),
        [],
    )
    label = "退货记录" if context == "returns" else "反馈记录"
    assert section.structure_statement == f"当前共纳入 7 条可分析{label}。"
    assert section.business_statement == section.structure_statement
    assert section.group_evidence_id == "scope"


def test_structure_prefers_first_specific_group_over_other_reasons() -> None:
    evidence = legacy_evidence()
    evidence["analysis"]["business_issues"] = []
    evidence["analysis"]["label_group_breakdown"].insert(
        0, {"value": "其他原因", "record_count": 8, "percentage": 80}
    )
    section = _build_structure_section(
        evidence["source"],
        evidence["analysis"],
        get_insight_report_profile("footwear"),
        [],
    )
    assert section.group_evidence_id == "group.2"
    assert section.structure_statement.startswith("尺码覆盖 2 条记录")


@pytest.mark.parametrize("provisional", [False, True])
@pytest.mark.parametrize("concentrated", [False, True])
def test_caveats_keep_review_bias_and_quality_warning_order(
    provisional: bool, concentrated: bool
) -> None:
    evidence = legacy_evidence(
        mapping_issue=True, text_issue=True, provisional=provisional
    )
    evidence["analysis"]["review_bias"] = {
        "status": "concentrated" if concentrated else "not_detected",
        "note": "合成审核偏差提示",
    }
    caveats = _build_caveats(evidence)
    assert ("合成审核偏差提示" in caveats) is (provisional and concentrated)
    if provisional:
        assert caveats[0].startswith("这是临时报告：2 条待审核记录未纳入")
        if concentrated:
            assert caveats[1] == "合成审核偏差提示"
    else:
        assert caveats[0].startswith("本报告只描述")
    assert caveats[-2:] == ["合成商品映射提示", "合成文本质量提示"]


def test_structure_uses_only_the_first_three_primary_issues() -> None:
    evidence = legacy_evidence()
    evidence["analysis"]["business_issues"] = [
        {
            "id": f"issue.{index}",
            "role": "primary",
            "label": "偏小",
            "hotspots": [
                {
                    "value": f"SKU-{index}",
                    "product_reason_rate": 40,
                    "overall_reason_rate": 20,
                }
            ],
        }
        for index in range(4)
    ]
    section = _build_structure_section(
        evidence["source"],
        evidence["analysis"],
        get_insight_report_profile("footwear"),
        [],
    )
    assert section.business_evidence_ids == ["issue.0", "issue.1", "issue.2"]
    assert "SKU-3" not in section.business_statement
    assert "比整体基线高+20.0pp" in section.business_statement
