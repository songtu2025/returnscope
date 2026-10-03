from __future__ import annotations

from copy import deepcopy

import pytest
from insight_report_helpers import analysis as _analysis

from web_backend.insight_report_contracts import PROMPT_VERSION, V5_PROMPT_VERSION
from web_backend.insight_report_evidence import _build_evidence


@pytest.mark.parametrize("prompt_version", [V5_PROMPT_VERSION, PROMPT_VERSION])
@pytest.mark.parametrize("context", ["returns", "user_feedback"])
@pytest.mark.parametrize(
    "mapping_issue,text_issue",
    [(False, False), (True, False), (False, True), (True, True)],
)
def test_evidence_preserves_quality_filters_and_input(
    prompt_version: str, context: str, mapping_issue: bool, text_issue: bool
) -> None:
    analysis = _analysis()
    analysis["analysis_context"] = context
    analysis["summary"]["product_unmatched_count"] = int(mapping_issue)
    analysis["text_quality"]["status"] = "needs_review" if text_issue else "passed"
    original = deepcopy(analysis)
    evidence = _build_evidence(analysis, prompt_version=prompt_version)
    assert analysis == original
    source = evidence["source"]
    assert source["clean_comment_record_count"] == 8
    assert source["clean_comment_rate"] == 80.0
    assert source["coverage_rate"] == 83.3
    assert source["taxonomy_versions"] == ["test-taxonomy-1", "test-taxonomy-2"]
    assert source["agent_keys"] == ["footwear"]
    assert source["quality_issue_codes"] == (
        ["pending_review"]
        + (["text_quality"] if text_issue else [])
        + (["product_mapping"] if mapping_issue else [])
    )
    safe = evidence["analysis"]
    diagnostic = safe["diagnostics"][0]
    assert bool(safe["product_reason_matrix"]) is not mapping_issue
    assert bool(safe["issue_cases"]) is not mapping_issue
    assert bool(diagnostic["variants"]) is not mapping_issue
    assert bool(diagnostic["hotspots"]) is not mapping_issue
    assert len(diagnostic["samples"]) == (2 if text_issue else 3)
    assert len(diagnostic["semantic_profile"]["opinions"]) == (1 if text_issue else 2)
    assert diagnostic["samples"][0]["product_sku"] == (
        None if mapping_issue else "TEST-SKU"
    )
    assert [sample["evidence_id"] for sample in safe["samples"]] == (
        ["diagnostic.FIT_TOO_SMALL.sample.1"]
        + ([] if text_issue else ["diagnostic.FIT_TOO_SMALL.sample.3"])
    )
    catalog = evidence["catalog"]
    assert list(catalog)[:8] == [
        "scope",
        "review_bias",
        "product_mapping",
        "text_quality",
        "report_profile",
        "group.1",
        "reason.FIT_TOO_SMALL",
        "subject.PRODUCT",
    ]
    assert list(catalog)[-1] == "business_issue.FIT_TOO_SMALL"
    assert ("issue_case.FIT_TOO_SMALL.test" in catalog) is not mapping_issue
    if not mapping_issue:
        assert catalog["product.1"]["value"] == (
            "10 条已分析退货" if context == "returns" else "10 条已分析反馈"
        )


@pytest.mark.parametrize("prompt_version", [V5_PROMPT_VERSION, PROMPT_VERSION])
def test_empty_evidence_preserves_default_scope(prompt_version: str) -> None:
    evidence = _build_evidence({}, prompt_version=prompt_version)
    source = evidence["source"]
    assert source["total_record_count"] == 0
    assert source["coverage_rate"] == 0.0
    assert source["clean_comment_rate"] == 0.0
    assert source["quality_issue_codes"] == []
    assert source["report_status"] == "final"
    assert source["analysis_context"] == "returns"
    assert source["report_profile"]["key"] == "generic"
    assert evidence["analysis"]["samples"] == []
    assert list(evidence["catalog"]) == [
        "scope",
        "review_bias",
        "product_mapping",
        "text_quality",
        "report_profile",
    ]


@pytest.mark.parametrize("prompt_version", [V5_PROMPT_VERSION, PROMPT_VERSION])
def test_evidence_preserves_limits_and_sample_order(prompt_version: str) -> None:
    analysis = _analysis()
    for key in (
        "label_group_breakdown",
        "reasons",
        "subject_breakdown",
        "product_reason_matrix",
        "diagnostics",
        "issue_cases",
    ):
        analysis[key] = [deepcopy(analysis[key][0]) for _ in range(16)]
    for index, diagnostic in enumerate(analysis["diagnostics"]):
        diagnostic["reason_code"] = f"TEST_{index}"
        diagnostic["samples"] = [
            {"comment": f"模拟反馈 {sample}"} for sample in range(index, index + 6)
        ]
    analysis["issue_cases"][0]["id"] = ""
    original = deepcopy(analysis)
    evidence = _build_evidence(analysis, prompt_version=prompt_version)
    safe = evidence["analysis"]
    assert analysis == original
    assert [
        len(safe[key])
        for key in (
            "label_group_breakdown",
            "reasons",
            "subject_breakdown",
            "product_reason_matrix",
            "diagnostics",
            "issue_cases",
        )
    ] == [12, 15, 10, 8, 4, 12]
    assert [sample["comment"] for sample in safe["samples"]] == [
        f"模拟反馈 {index}" for index in range(8)
    ]
    assert [sample["evidence_id"] for sample in safe["samples"]][-2:] == [
        "diagnostic.TEST_1.sample.6",
        "diagnostic.TEST_2.sample.6",
    ]
    assert "issue_case.FIT_TOO_SMALL.test" in evidence["catalog"]
    assert "" not in evidence["catalog"]
