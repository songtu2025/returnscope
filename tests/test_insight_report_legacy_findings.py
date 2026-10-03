import pytest
from insight_report_helpers import legacy_evidence

from web_backend.insight_report_profiles import get_insight_report_profile
from web_backend.insight_reports.legacy_findings import (
    _build_diagnostic_finding,
    _build_information_finding,
    _select_reasons,
)


def test_reason_selection_follows_profile_and_keeps_broad_reason() -> None:
    reasons = [
        {"value": code, "subjects": ["PRODUCT"], "label_group": "尺码"}
        for code in ["GLOVE_WARMTH", "GLOVE_SIZE_LARGE", "GLOVE_SIZE_SMALL", "OTHER"]
    ]
    broad = {"value": "BROAD", "subjects": ["BUYER", "PRODUCT"]}
    selected, information = _select_reasons(
        [*reasons, broad], get_insight_report_profile("gloves")
    )
    assert [reason["value"] for reason in selected] == [
        "GLOVE_SIZE_SMALL",
        "GLOVE_SIZE_LARGE",
        "GLOVE_WARMTH",
    ]
    assert information == broad


@pytest.mark.parametrize("dimension", ["variants", "hotspots"])
def test_diagnostic_falls_back_to_catalogued_hotspots(dimension: str) -> None:
    evidence = legacy_evidence()
    evidence["analysis"]["business_issues"] = []
    diagnostic = evidence["analysis"]["diagnostics"][0]
    if dimension == "hotspots":
        diagnostic["variants"] = []
    suffix = "variant" if dimension == "variants" else "hotspot"
    evidence["catalog"][f"diagnostic.FIT_TOO_SMALL.{suffix}.1"] = {}
    finding, ids, targets = _build_diagnostic_finding(
        evidence, evidence["analysis"]["reasons"]
    )
    assert finding is not None
    assert f"diagnostic.FIT_TOO_SMALL.{suffix}.1" in ids
    assert targets == ["TEST-SKU"]


def test_findings_preserve_empty_results() -> None:
    assert _build_diagnostic_finding(legacy_evidence(), []) == (None, [], [])
    assert _build_information_finding(None, {}) == (None, [])


def test_information_finding_keeps_unspecified_parts_and_opinion() -> None:
    reason = {
        "value": "BROAD",
        "label": "宽泛原因",
        "record_count": 4,
        "percentage": 40,
    }
    diagnostics = {
        "BROAD": {
            "semantic_profile": {
                "parts": [{"value": "UNSPECIFIED", "percentage": 75}],
                "opinions": [{"opinion": "不合预期", "record_count": 3}],
            }
        }
    }
    finding, ids = _build_information_finding(reason, diagnostics)
    assert finding is not None
    assert "75.0%未明确商品部位" in finding["conclusion"]
    assert "不合预期" in finding["conclusion"]
    assert ids == ["reason.BROAD", "diagnostic.BROAD.opinion.1"]
