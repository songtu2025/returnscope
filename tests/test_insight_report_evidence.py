from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from web_backend.insight_report_contracts import PROMPT_VERSION, V5_PROMPT_VERSION
from web_backend.insight_report_evidence import _build_evidence


def _analysis() -> dict[str, Any]:
    reason = {
        "value": "FIT_TOO_SMALL",
        "label": "尺码偏小",
        "label_group": "尺码",
        "record_count": 2,
        "percentage": 20.0,
        "subjects": ["PRODUCT"],
    }
    samples = [
        {"comment": "Too small", "product_name": "模拟商品", "product_sku": "TEST-SKU"},
        {"comment": "Too small", "product_name": "模拟商品", "product_sku": "TEST-SKU"},
        {
            "comment": "It doesn�� fit",
            "product_name": "模拟商品",
            "product_sku": "TEST-SKU",
        },
    ]
    semantic_profile = {
        "opinions": [
            {"opinion": "too small", "record_count": 2},
            {"opinion": "It doesn�� fit", "record_count": 1},
        ]
    }
    hotspot = {
        "value": "TEST-SKU",
        "record_count": 2,
        "total_record_count": 5,
        "product_reason_rate": 40.0,
        "overall_reason_rate": 20.0,
        "lift": 2.0,
    }
    return {
        "dashboard_id": "test-dashboard",
        "version_id": "test-version",
        "summary": {
            "record_count": 10,
            "total_record_count": 12,
            "pending_review_record_count": 2,
            "coverage_rate": 83.3,
        },
        "label_group_breakdown": [
            {"value": "尺码", "record_count": 2, "percentage": 20.0}
        ],
        "reasons": [reason],
        "subject_breakdown": [{"value": "PRODUCT", "label": "商品", "record_count": 2}],
        "product_reason_matrix": [{"value": "模拟商品", "total_record_count": 10}],
        "diagnostics": [
            {
                "reason_code": "FIT_TOO_SMALL",
                "selected_reason": reason,
                "trend_summary": {
                    "status": "available",
                    "window_weeks": 4,
                    "early_rate": 10.0,
                    "recent_rate": 20.0,
                    "delta_percentage_points": 10.0,
                },
                "hotspots": [hotspot],
                "variants": [hotspot],
                "samples": samples,
                "semantic_profile": semantic_profile,
            }
        ],
        "issue_cases": [
            {
                "id": "issue_case.FIT_TOO_SMALL.test",
                "reason_code": "FIT_TOO_SMALL",
                "label": "尺码偏小",
                "product_sku": "TEST-SKU",
                "record_count": 2,
                "total_record_count": 5,
                "issue_rate": 40.0,
                "overall_rate": 20.0,
                "lift": 2.0,
                "trend": [{"period_start": "2026-01-05", "record_count": 2}],
                "samples": samples,
                "semantic_profile": semantic_profile,
            }
        ],
        "review_bias": {"status": "not_detected", "note": "模拟审核偏差"},
        "text_quality": {
            "status": "passed",
            "checked_record_count": 10,
            "anomaly_record_count": 2,
        },
        "filter_options": {"listings": ["TEST-LISTING"], "product_names": ["模拟商品"]},
        "sources": [
            {"agent_key": "footwear", "taxonomy_version": "test-taxonomy-2"},
            {"agent_key": "footwear", "taxonomy_version_id": "test-taxonomy-1"},
            {},
        ],
    }


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
