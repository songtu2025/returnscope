from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from web_backend.insight_report_consistency import _decision_report_consistency
from web_backend.insight_report_quality_v6 import _evaluate_live_quality_v6
from web_backend.insight_report_service import InsightReportService


@pytest.fixture
def report_pair() -> tuple[dict[str, Any], dict[str, Any]]:
    reason = {"value": "A", "record_count": 2, "percentage": 20}
    opinions = [{"opinion": "偏小"}, {"opinion": "Didn稚 fit"}]
    samples = [{"comment": "偏小"}, {"comment": "Didn稚 fit"}]
    issue = {
        "id": "issue.A",
        "metrics": {"matched_return_samples": 2, "return_sample_share": 20},
        "evidence_ids": ["reason.A"],
        "known": ["高频反馈为偏小", "共有两条记录", " 高频反馈为保留"],
        "evidence_explanation": "已有说明",
        "readiness": {
            "status": "verification_ready",
            "label": "原始标签",
            "reason": "原始说明",
        },
    }
    content = {"issues": [issue], "caveats": ["只有退货样本"]}
    evidence = {
        "source": {
            "product_mapping": {"status": "passed"},
            "pending_review_record_count": 0,
        },
        "analysis": {
            "reasons": [reason],
            "diagnostics": [
                {
                    "reason_code": "A",
                    "selected_reason": reason,
                    "semantic_profile": {"opinions": opinions, "parts": ["尺码"]},
                    "samples": samples,
                    "hotspots": [{"value": "商品甲"}],
                }
            ],
            "issue_cases": [
                {"semantic_profile": {"opinions": opinions}, "samples": samples}
            ],
            "business_issues": [
                {"contexts": {"opinions": opinions, "samples": samples}}
            ],
            "samples": samples,
            "review_bias": {},
        },
        "catalog": {
            "reason.A": {"label": "原因", "value": "偏小", "data": reason},
            "diagnostic.A.sample.1": {
                "label": "正常证据",
                "value": "偏小",
                "data": {"comment": "偏小"},
            },
            "diagnostic.A.opinion.2": {
                "label": "异常证据",
                "value": "原始观点",
                "data": {"opinion": "Didn稚 fit"},
            },
        },
        "blueprint": {"issues": [deepcopy(issue)]},
    }
    return content, evidence


@pytest.mark.parametrize("text_status", ["passed", "needs_review"])
@pytest.mark.parametrize("mapping_status", ["passed", "needs_review"])
@pytest.mark.parametrize("pending", [0, "3"])
@pytest.mark.parametrize("blocked", [False, True])
def test_quality_combinations_preserve_priority_and_readiness(
    report_pair: tuple[dict[str, Any], dict[str, Any]],
    text_status: str,
    mapping_status: str,
    pending: int | str,
    blocked: bool,
) -> None:
    content, evidence = report_pair
    evidence["source"]["product_mapping"]["status"] = mapping_status
    evidence["source"]["pending_review_record_count"] = pending
    if blocked:
        content["issues"][0]["metrics"]["matched_return_samples"] = 3
    text_quality = {"status": text_status}
    before = deepcopy((content, evidence, text_quality))
    actual = _evaluate_live_quality_v6(content, evidence, text_quality)
    expected_codes = []
    if blocked:
        expected_codes.append("report_consistency")
    if text_status == "needs_review":
        expected_codes.append("text_quality")
    if mapping_status == "needs_review":
        expected_codes.append("product_mapping")
    if pending:
        expected_codes.append("pending_review")
    expected_status = (
        "blocked" if blocked else "warning" if expected_codes else "passed"
    )
    expected_readiness = {
        "blocked": {
            "status": "unusable",
            "label": "不可使用",
            "reason": "报告内部数据不一致，请重新生成报告。",
        },
        "warning": {
            "status": "diagnostic_only",
            "label": "仅供诊断",
            "reason": "数据质量或审核范围仍有限，只能用于定位问题。",
        },
        "passed": {
            "status": "verification_ready",
            "label": "可进入验证",
            "reason": "数据质量和报告一致性校验均已通过。",
        },
    }[expected_status]
    gate = actual["quality_gate"]
    assert gate["status"] == expected_status
    assert [item["code"] for item in gate["issues"]] == expected_codes
    assert gate["decision_readiness"] == expected_readiness
    assert gate["consistency"] == {
        "status": "blocked" if blocked else "passed",
        "issues": ["问题 issue.A 的指标与确定性证据不一致"] if blocked else [],
    }
    assert gate["text_quality"] == text_quality
    assert gate["product_mapping"] == evidence["source"]["product_mapping"]
    assert actual["evidence"]["source"]["quality_issue_codes"] == expected_codes
    assert actual["evidence"]["source"]["report_status"] == (
        "provisional" if expected_codes else "final"
    )
    expected_issue_readiness = (
        expected_readiness if expected_codes else content["issues"][0]["readiness"]
    )
    assert actual["content"]["issues"][0]["readiness"] == expected_issue_readiness
    assert (content, evidence, text_quality) == before


def test_untrusted_text_preserves_structured_data_and_normal_evidence(
    report_pair: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    content, evidence = report_pair
    actual = _evaluate_live_quality_v6(content, evidence, {"status": "needs_review"})
    analysis = actual["evidence"]["analysis"]
    diagnostic = analysis["diagnostics"][0]
    assert diagnostic["selected_reason"] == evidence["analysis"]["reasons"][0]
    assert diagnostic["hotspots"] == [{"value": "商品甲"}]
    assert diagnostic["semantic_profile"] == {
        "opinions": [{"opinion": "偏小"}],
        "parts": ["尺码"],
    }
    assert diagnostic["samples"] == [{"comment": "偏小"}]
    assert diagnostic["text_evidence"] == {
        "status": "available",
        "opinion_count": 1,
        "sample_count": 1,
    }
    assert analysis["issue_cases"] == [
        {
            "semantic_profile": {"opinions": [{"opinion": "偏小"}]},
            "samples": [{"comment": "偏小"}],
        }
    ]
    assert analysis["business_issues"] == [
        {
            "contexts": {
                "opinions": [{"opinion": "偏小"}],
                "samples": [{"comment": "偏小"}],
            }
        }
    ]
    assert analysis["samples"] == []
    catalog = actual["evidence"]["catalog"]
    assert list(catalog) == [*evidence["catalog"], "text_quality"]
    assert (
        catalog["diagnostic.A.sample.1"] == evidence["catalog"]["diagnostic.A.sample.1"]
    )
    assert catalog["diagnostic.A.opinion.2"] == {
        "label": "异常证据",
        "value": "文本质量未通过，原始文本证据暂不可用",
        "data": {},
    }
    issue = actual["content"]["issues"][0]
    assert issue["known"] == ["共有两条记录", " 高频反馈为保留"]
    assert issue["metrics"] == content["issues"][0]["metrics"]
    assert issue["evidence_ids"] == content["issues"][0]["evidence_ids"]
    assert issue["evidence_explanation"] == (
        "评论文本质量未通过，当前仅保留结构化指标用于定位，不能据此判断原因。"
    )
    assert actual["content"]["caveats"] == content["caveats"]


@pytest.mark.parametrize("field", ["opinion", "evidence", "comment", "reason"])
@pytest.mark.parametrize(
    ("evidence_id", "masked"),
    [
        ("diagnostic.A.sample.1", True),
        ("diagnostic.A.opinion.1", True),
        ("scope", False),
        ("sample.1", False),
        ("diagnostic.A.sample", False),
    ],
)
def test_catalog_masks_only_anomalous_text_with_matching_markers(
    evidence_id: str,
    masked: bool,
    field: str,
) -> None:
    item = {"label": "样本", "value": "原始值", "data": {field: "Didn稚 fit"}}
    evidence = {"catalog": {evidence_id: item}}
    before = deepcopy(evidence)
    actual = _evaluate_live_quality_v6({}, evidence, {"status": "needs_review"})
    assert actual["evidence"]["catalog"][evidence_id] == (
        {"label": "样本", "value": "文本质量未通过，原始文本证据暂不可用", "data": {}}
        if masked
        else item
    )
    assert evidence == before


def test_passed_text_and_mapping_warning_do_not_filter_v6_content(
    report_pair: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    content, evidence = report_pair
    evidence["source"]["product_mapping"] = {"status": "needs_review"}
    actual = _evaluate_live_quality_v6(content, evidence, {"status": "passed"})
    assert actual["content"]["issues"][0]["known"] == content["issues"][0]["known"]
    assert actual["content"]["issues"][0]["evidence_explanation"] == "已有说明"
    assert (
        actual["evidence"]["analysis"]["diagnostics"]
        == evidence["analysis"]["diagnostics"]
    )
    assert actual["evidence"]["analysis"]["samples"] == evidence["analysis"]["samples"]
    assert (
        actual["evidence"]["catalog"]["diagnostic.A.opinion.2"]
        == evidence["catalog"]["diagnostic.A.opinion.2"]
    )


@pytest.mark.parametrize("note", [None, "", "需要人工核对"])
def test_quality_notes_keep_original_fallbacks(note: str | None) -> None:
    text_quality = {"status": "needs_review", "note": note}
    evidence = {
        "source": {
            "product_mapping": {"status": "needs_review", "note": note},
            "pending_review_record_count": "3",
        },
        "analysis": {"review_bias": {"note": note}},
    }
    actual = _evaluate_live_quality_v6({}, evidence, text_quality)
    assert [item["detail"] for item in actual["quality_gate"]["issues"]] == [
        note or "评论文本需要核对。",
        note or "商品主数据映射需要核对。",
        note or "3 条待审核记录未进入本次统计。",
    ]
    assert actual["evidence"]["catalog"]["text_quality"] == {
        "label": "评论文本质量",
        "value": note or "未发现明显编码异常",
        "data": text_quality,
    }
    assert actual["evidence"]["source"]["text_quality"] is text_quality
    assert actual["evidence"]["analysis"]["text_quality"] is text_quality


@pytest.mark.parametrize(
    ("pending", "expected"), [(None, 0), ("", 0), (0, 0), ("0", 0), ("3", 3), (-2, -2)]
)
def test_pending_review_preserves_integer_conversion_and_truthiness(
    pending: Any,
    expected: int,
) -> None:
    evidence = {"source": {"pending_review_record_count": pending}}
    actual = _evaluate_live_quality_v6({}, evidence, {})
    assert [item["detail"] for item in actual["quality_gate"]["issues"]] == (
        [f"{expected} 条待审核记录未进入本次统计。"] if expected else []
    )


@pytest.mark.parametrize("pending", ["不是数字", "3.5"])
def test_invalid_pending_review_still_raises(pending: str) -> None:
    evidence = {"source": {"pending_review_record_count": pending}}
    before = deepcopy(evidence)
    with pytest.raises(ValueError):
        _evaluate_live_quality_v6({}, evidence, {"status": "needs_review"})
    assert evidence == before


def test_consistency_is_checked_after_text_filtering(
    report_pair: tuple[dict[str, Any], dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content, evidence = report_pair
    evidence["analysis"]["diagnostics"][0]["semantic_profile"] = {}
    observed = []

    def observe_consistency(
        filtered_content: dict[str, Any],
        filtered_evidence: dict[str, Any],
    ) -> dict[str, Any]:
        assert filtered_content["issues"][0]["known"] == [
            "共有两条记录",
            " 高频反馈为保留",
        ]
        assert filtered_evidence["analysis"]["samples"] == []
        assert filtered_evidence["catalog"]["diagnostic.A.opinion.2"]["data"] == {}
        assert filtered_evidence["source"]["text_quality"]["status"] == "needs_review"
        observed.append(True)
        return _decision_report_consistency(filtered_content, filtered_evidence)

    monkeypatch.setattr(
        "web_backend.insight_report_quality_v6._decision_report_consistency",
        observe_consistency,
    )
    actual = _evaluate_live_quality_v6(content, evidence, {"status": "needs_review"})
    assert observed == [True]
    assert actual["quality_gate"]["consistency"] == {"status": "passed", "issues": []}
    assert actual["evidence"]["analysis"]["diagnostics"][0]["text_evidence"] == {
        "status": "available",
        "opinion_count": 0,
        "sample_count": 1,
    }


def test_consistency_errors_precede_warnings_and_limit_detail_to_three(
    report_pair: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    content, evidence = report_pair
    evidence["analysis"]["diagnostics"] = [{}, {"reason_code": "B"}]
    content["issues"][0]["metrics"] = {}
    content["issues"][0]["evidence_ids"] = []
    actual = _evaluate_live_quality_v6(content, evidence, {"status": "needs_review"})
    consistency = actual["quality_gate"]["consistency"]
    assert consistency["issues"] == [
        "存在未标明原因代码的诊断数据",
        "诊断原因 B 不在分类结果中",
        "问题 issue.A 的指标与确定性证据不一致",
        "问题 issue.A 的证据引用不一致",
    ]
    assert actual["quality_gate"]["issues"][0] == {
        "code": "report_consistency",
        "label": "报告内部数据不一致",
        "detail": "；".join(consistency["issues"][:3]),
        "evidence_ids": [],
    }


@pytest.mark.parametrize("text_status", ["passed", "needs_review"])
@pytest.mark.parametrize("blocked", [False, True])
def test_readiness_applies_to_every_issue_only_when_report_is_limited(
    report_pair: tuple[dict[str, Any], dict[str, Any]],
    text_status: str,
    blocked: bool,
) -> None:
    content, evidence = report_pair
    second = {**deepcopy(content["issues"][0]), "id": "issue.B"}
    content["issues"].append(second)
    evidence["blueprint"]["issues"].append(deepcopy(second))
    if blocked:
        content["issues"][0]["evidence_ids"] = []
    actual = _evaluate_live_quality_v6(content, evidence, {"status": text_status})
    expected = actual["quality_gate"]["decision_readiness"]
    if expected["status"] == "verification_ready":
        assert [item["readiness"] for item in actual["content"]["issues"]] == [
            item["readiness"] for item in content["issues"]
        ]
    else:
        assert [item["readiness"] for item in actual["content"]["issues"]] == [
            expected,
            expected,
        ]


def test_empty_input_and_service_alias_keep_complete_result() -> None:
    actual = _evaluate_live_quality_v6({}, {}, {})
    assert actual == {
        "content": {},
        "evidence": {
            "source": {
                "text_quality": {},
                "quality_issue_codes": [],
                "report_status": "final",
            },
            "analysis": {"text_quality": {}},
            "catalog": {
                "text_quality": {
                    "label": "评论文本质量",
                    "value": "未发现明显编码异常",
                    "data": {},
                }
            },
        },
        "quality_gate": {
            "status": "passed",
            "issues": [],
            "text_quality": {},
            "product_mapping": {},
            "consistency": {"status": "passed", "issues": []},
            "decision_readiness": {
                "status": "verification_ready",
                "label": "可进入验证",
                "reason": "数据质量和报告一致性校验均已通过。",
            },
        },
    }
    assert InsightReportService._evaluate_live_quality_v6({}, {}, {}) == actual
