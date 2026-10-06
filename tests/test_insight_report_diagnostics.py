from __future__ import annotations

import pytest

from web_backend.insight_report_service import InsightReportService


@pytest.mark.parametrize(
    "reasons,expected",
    [
        ([], []),
        ([{"value": "BUYER", "subjects": ["BUYER"]}], ["BUYER"]),
        ([{"value": ""}, {"value": "BUYER"}], []),
        (
            [{"value": code, "subjects": ["PRODUCT"]} for code in ("A", "B", "C")],
            ["A", "B"],
        ),
        (
            [
                {"value": "OTHER", "label_group": "其他原因"},
                {"value": "A", "subjects": ["PRODUCT"]},
                {"value": "A", "subjects": ["PRODUCT"]},
                {"value": "B", "subjects": ["PRODUCT"]},
            ],
            ["A", "OTHER"],
        ),
        (
            [
                {"value": "BROAD", "subjects": ["BUYER", "ORDER"]},
                {"value": "OTHER", "label_group": "其他原因"},
                {"value": "A", "subjects": ["PRODUCT"]},
            ],
            ["A", "BROAD"],
        ),
    ],
)
def test_diagnostic_reason_selection_keeps_fallback_and_first_occurrence(
    reasons: list[dict], expected: list[str]
) -> None:
    assert (
        InsightReportService._diagnostic_reason_codes({"reasons": reasons}) == expected
    )


def test_diagnostic_reason_scan_excludes_sixteenth_preferred_reason() -> None:
    reasons = [{"value": f"BUYER_{index}"} for index in range(15)]
    reasons.append({"value": "FIT_TOO_SMALL", "subjects": ["PRODUCT"]})
    assert InsightReportService._diagnostic_reason_codes(
        {"sources": [{"agent_key": "footwear"}], "reasons": reasons}
    ) == ["BUYER_0"]


def test_diagnostic_reasons_follow_report_blueprint() -> None:
    analysis = {
        "reasons": [
            {
                "value": "OTHER_NO_LONGER_NEEDED",
                "label_group": "其他原因",
                "subjects": ["BUYER", "ORDER"],
            },
            {
                "value": "FIT_TOO_SMALL",
                "label_group": "尺码",
                "subjects": ["PRODUCT"],
            },
            {
                "value": "FIT_TOO_LARGE",
                "label_group": "尺码",
                "subjects": ["PRODUCT"],
            },
            {
                "value": "COLOR_MISMATCH",
                "label_group": "外观",
                "subjects": ["PRODUCT"],
            },
        ]
    }

    assert InsightReportService._diagnostic_reason_codes(analysis) == [
        "FIT_TOO_SMALL",
        "FIT_TOO_LARGE",
        "OTHER_NO_LONGER_NEEDED",
    ]


def test_glove_profile_prioritizes_category_problems() -> None:
    analysis = {
        "sources": [{"agent_key": "gloves"}],
        "reasons": [
            {
                "value": "OTHER_EXPECTATION_MISMATCH",
                "label_group": "其他原因",
                "subjects": ["PRODUCT", "BUYER"],
            },
            {
                "value": "GLOVE_WARMTH",
                "label_group": "功能",
                "subjects": ["PRODUCT"],
            },
            {
                "value": "GLOVE_SIZE_LARGE",
                "label_group": "尺码",
                "subjects": ["PRODUCT"],
            },
            {
                "value": "GLOVE_SIZE_SMALL",
                "label_group": "尺码",
                "subjects": ["PRODUCT"],
            },
        ],
    }

    assert InsightReportService._diagnostic_reason_codes(analysis) == [
        "GLOVE_SIZE_SMALL",
        "GLOVE_SIZE_LARGE",
        "GLOVE_WARMTH",
        "OTHER_EXPECTATION_MISMATCH",
    ]
