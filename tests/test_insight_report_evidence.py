from __future__ import annotations

from copy import deepcopy

import pytest
from insight_report_helpers import analysis as _analysis

from web_backend.insight_report_contracts import PROMPT_VERSION, V5_PROMPT_VERSION
from web_backend.insight_report_evidence import _build_evidence
from web_backend.insight_reports.business_issue_context import _BusinessIssueContext
from web_backend.insight_reports.business_issue_details import _business_issue_evidence
from web_backend.insight_reports.evidence_catalog import (
    _diagnostic_evidence,
    _issue_case_evidence,
)


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


@pytest.mark.parametrize("kind", ["case", "diagnostic"])
def test_evidence_entries_preserve_labels_unicode_limits_and_data_identity(
    kind: str,
) -> None:
    opinions = [{"opinion": "模拟观点", "record_count": "2"}, {"opinion": ""}]
    samples = [
        {"comment": "  " + "合" * 161, "product_name": "模拟商品"},
        {"comment": "", "reason": " fallback "},
        {"comment": "   ", "reason": "忽略该兜底"},
    ]
    raw = {
        "id": "case.X",
        "reason_code": "X",
        "product_sku": "模拟SKU",
        "samples": samples,
        "semantic_profile": {"opinions": opinions},
    }
    before = deepcopy(raw)
    catalog = _issue_case_evidence(raw) if kind == "case" else _diagnostic_evidence(raw)
    prefix = "case.X" if kind == "case" else "diagnostic.X"
    ids = [
        f"{prefix}.opinion.1",
        f"{prefix}.opinion.2",
        f"{prefix}.sample.1",
        f"{prefix}.sample.2",
        f"{prefix}.sample.3",
    ]
    assert list(catalog) == (["case.X"] if kind == "case" else []) + ids
    assert catalog[ids[0]]["label"] == "模拟观点" and catalog[ids[0]]["value"] == "2 条"
    assert catalog[ids[1]]["label"] == "高频表述 2"
    assert [catalog[key]["value"] for key in ids[2:]] == [
        "合" * 160,
        "fallback",
        "未提供评论",
    ]
    assert [catalog[key]["label"] for key in ids[2:]] == (
        ["模拟SKU"] * 3 if kind == "case" else ["模拟商品", "原始评论", "原始评论"]
    )
    assert all(
        catalog[key]["data"] is item
        for key, item in zip(ids, opinions + samples, strict=True)
    )
    assert raw == before


@pytest.mark.parametrize(
    "cases,trend,dimension,expected",
    [
        (
            [{"id": "case.X"}, {"id": "case.X"}, {"id": None}],
            {},
            "product",
            [
                "reason.X",
                "case.X",
                "None",
                "case.X.opinion.1",
                "case.X.opinion.2",
                "case.X.sample.1",
            ],
        ),
        (
            [{"id": "reason.X", "trend": [{}]}],
            {"status": "available"},
            "variant",
            [
                "reason.X",
                "reason.X.trend",
                "reason.X.opinion.1",
                "reason.X.opinion.2",
                "reason.X.sample.1",
            ],
        ),
        (
            [],
            {"status": "available"},
            "product",
            [
                "reason.X",
                "diagnostic.X.trend",
                "diagnostic.X.product.1",
                "diagnostic.X.product.2",
                "diagnostic.X.opinion.1",
                "diagnostic.X.opinion.2",
                "diagnostic.X.sample.1",
            ],
        ),
        (
            [],
            {"status": "available"},
            "variant",
            [
                "reason.X",
                "diagnostic.X.trend",
                "diagnostic.X.variant.1",
                "diagnostic.X.variant.2",
                "diagnostic.X.opinion.1",
                "diagnostic.X.opinion.2",
                "diagnostic.X.sample.1",
            ],
        ),
        ([], {"status": "insufficient"}, "variant", ["reason.X"]),
    ],
)
def test_business_evidence_keeps_case_priority_all_indexes_and_first_occurrence(
    cases: list, trend: dict, dimension: str, expected: list[str]
) -> None:
    context = _BusinessIssueContext(
        cases=cases,
        dimension=dimension,
        hotspots=[{}, {}],
        trend_summary=trend,
        trend=[],
        opinions=[{}, {}],
        samples=[{}],
        parts=[],
        validation_focus="合成验证",
    )
    before = deepcopy(context)
    assert _business_issue_evidence("X", context) == expected
    assert context == before
