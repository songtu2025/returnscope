from __future__ import annotations

from copy import deepcopy

import pytest

from web_backend.insight_report_evidence import _mask_product_diagnostics
from web_backend.insight_reports.quality_context import (
    _LiveQualityEvaluation,
    _prepare_live_quality,
)
from web_backend.insight_reports.quality_filtering import (
    _sanitize_analysis,
    _sanitize_catalog,
)
from web_backend.insight_reports.quality_narrative import _summary_is_blocked


def _context(mapping_trusted: bool, text_trusted: bool) -> _LiveQualityEvaluation:
    return _prepare_live_quality(
        {},
        {
            "source": {
                "product_mapping": {
                    "status": "consistent" if mapping_trusted else "needs_review"
                }
            },
            "analysis": {"product_reason_matrix": [{"value": "模拟商品"}]},
        },
        {"status": "passed" if text_trusted else "needs_review"},
    )


@pytest.mark.parametrize("mapping_trusted", [False, True])
@pytest.mark.parametrize("text_trusted", [False, True])
def test_catalog_preserves_marker_priority_and_remaining_order(
    mapping_trusted: bool, text_trusted: bool
) -> None:
    context = _context(mapping_trusted, text_trusted)
    contexts = {
        "opinions": [{"opinion": "clean"}, {"opinion": "bad混排"}],
        "samples": [{"comment": "clean"}, {"comment": "bad混排"}],
    }
    context.catalog = {
        "scope": {"data": {}},
        "reason.X.hotspot.1": {"data": {}},
        "reason.X.variant.1": {"data": {}},
        "issue_case.X": {"data": {}},
        "diagnostic.X.sample.clean": {"data": {"comment": "clean"}},
        "diagnostic.X.sample.bad": {"data": {"comment": "bad混排"}},
        "diagnostic.X.opinion.bad": {"data": {"opinion": "bad混排"}},
        "business_issue.X": {"data": {"contexts": deepcopy(contexts)}},
        "business_issue.X.sample.1": {"data": {"contexts": deepcopy(contexts)}},
    }
    expected = ["scope"]
    if mapping_trusted:
        expected.extend(["reason.X.hotspot.1", "reason.X.variant.1", "issue_case.X"])
    expected.append("diagnostic.X.sample.clean")
    if text_trusted:
        expected.extend(["diagnostic.X.sample.bad", "diagnostic.X.opinion.bad"])
    if mapping_trusted:
        expected.extend(["business_issue.X", "business_issue.X.sample.1"])

    _sanitize_catalog(context)

    assert list(context.catalog) == expected
    if mapping_trusted:
        filtered = context.catalog["business_issue.X"]["data"]["contexts"]
        assert len(filtered["opinions"]) == (2 if text_trusted else 1)
        assert len(filtered["samples"]) == (2 if text_trusted else 1)
        # 同时带 sample 标记时走样本文本判断，不再进入业务问题的嵌套过滤。
        assert (
            context.catalog["business_issue.X.sample.1"]["data"]["contexts"] == contexts
        )


@pytest.mark.parametrize("mapping_trusted", [False, True])
@pytest.mark.parametrize("text_trusted", [False, True])
@pytest.mark.parametrize(
    "evidence_id,is_product,is_text",
    [
        ("prefix.hotspot.1", True, False),
        ("prefix.variant.1", True, False),
        ("prefix.business_issue.X", True, False),
        ("prefix.issue_case.X", True, False),
        ("prefix.sample.1", False, True),
        ("prefix.opinion.1", False, True),
        ("scope", False, False),
    ],
)
def test_summary_blocks_only_untrusted_evidence_types(
    mapping_trusted: bool,
    text_trusted: bool,
    evidence_id: str,
    is_product: bool,
    is_text: bool,
) -> None:
    context = _context(mapping_trusted, text_trusted)
    summary = {
        "title": "范围结论",
        "statement": "模拟摘要",
        "evidence_ids": [evidence_id],
    }
    assert _summary_is_blocked(summary, context) is (
        (is_product and not mapping_trusted) or (is_text and not text_trusted)
    )


@pytest.mark.parametrize("field", ["title", "statement"])
def test_summary_preserves_product_name_guard_without_references(field: str) -> None:
    summary = {field: "模拟商品需要核对", "evidence_ids": []}
    assert _summary_is_blocked(summary, _context(False, True)) is True
    assert _summary_is_blocked(summary, _context(True, True)) is False


def test_product_mask_preserves_input_and_non_product_evidence() -> None:
    diagnostic = {
        "hotspots": [{"value": "模拟商品"}],
        "variants": [{"value": "模拟规格"}],
        "selected_reason": {"value": "X"},
        "samples": [
            {"comment": "模拟反馈", "product_name": "模拟商品", "product_sku": "SKU"}
        ],
    }
    before = deepcopy(diagnostic)
    masked = _mask_product_diagnostics([diagnostic])[0]
    assert diagnostic == before
    assert masked["hotspots"] == masked["variants"] == []
    assert masked["samples"] == [
        {"comment": "模拟反馈", "product_name": None, "product_sku": None}
    ]
    assert masked["selected_reason"] is diagnostic["selected_reason"]
    assert masked["samples"][0] is not diagnostic["samples"][0]


def test_analysis_masks_product_identity_before_text_filtering() -> None:
    context = _context(False, False)
    context.analysis.update(
        {
            "diagnostics": [
                {
                    "hotspots": [{"value": "模拟商品"}],
                    "variants": [{"value": "模拟规格"}],
                    "samples": [
                        {"comment": "clean", "product_name": "模拟商品"},
                        {"comment": "bad混排", "product_name": "模拟商品"},
                    ],
                }
            ],
            "issue_cases": [{"id": "case"}],
            "business_issues": [{"id": "issue"}],
            "samples": [{"comment": "clean", "product_sku": "SKU"}],
        }
    )
    _sanitize_analysis(context)
    assert context.analysis["product_reason_matrix"] == []
    assert context.analysis["issue_cases"] == context.analysis["business_issues"] == []
    diagnostic = context.analysis["diagnostics"][0]
    assert diagnostic["samples"] == [
        {"comment": "clean", "product_name": None, "product_sku": None}
    ]
    assert diagnostic["text_evidence"] == {
        "status": "available",
        "opinion_count": 0,
        "sample_count": 1,
    }
    assert context.analysis["samples"] == [
        {"comment": "clean", "product_sku": None, "product_name": None}
    ]
