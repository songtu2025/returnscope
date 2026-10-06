from __future__ import annotations

from copy import deepcopy

import pytest

from web_backend.insight_reports.decision_issue_details import (
    _issue_metrics,
    _issue_readiness,
    _issue_scope,
)


@pytest.mark.parametrize(
    "row,expected",
    [
        ({}, (12.6, None, None, None)),
        (
            {
                "product_reason_rate": 0,
                "issue_rate": 9,
                "overall_reason_rate": 0,
                "overall_rate": 8,
                "lift": 0,
            },
            (0.0, 0.0, 0.0, 0.0),
        ),
        (
            {
                "product_reason_rate": None,
                "issue_rate": 0,
                "overall_reason_rate": None,
                "overall_rate": 2,
            },
            (0.0, 2.0, -2.0, None),
        ),
        (
            {
                "issue_rate": None,
                "overall_reason_rate": 4,
                "overall_rate": 8,
                "lift": 1.234,
            },
            (12.6, 4.0, 8.6, 1.23),
        ),
        (
            {
                "product_reason_rate": 3.25,
                "issue_rate": 4.2,
                "overall_rate": 2.5,
                "lift": 1.5,
            },
            (3.2, 2.5, 0.8, 1.5),
        ),
    ],
)
def test_issue_metrics_keep_zero_priority_rounding_and_key_order(
    row: dict, expected: tuple
) -> None:
    issue = {"record_count": 7, "percentage": 12.56}
    source = {"included_record_count": 20}
    original = deepcopy((row, issue, source))
    metrics = _issue_metrics(row, issue, source)
    assert list(metrics) == [
        "matched_return_samples",
        "scoped_return_samples",
        "return_sample_share",
        "baseline_return_sample_share",
        "gap_percentage_points",
        "lift",
        "recent_change_percentage_points",
        "trend_direction",
    ]
    assert (metrics["matched_return_samples"], metrics["scoped_return_samples"]) == (
        7,
        20,
    )
    assert tuple(metrics[key] for key in list(metrics)[2:6]) == expected
    assert (row, issue, source) == original


@pytest.mark.parametrize("count", [None, 0, "0", "3"])
def test_issue_counts_keep_truthy_fallback_before_integer_conversion(count) -> None:
    metrics = _issue_metrics(
        {"record_count": count, "total_record_count": count},
        {"record_count": 7},
        {"included_record_count": 20},
    )
    expected = (7, 20) if count in (None, 0) else (int(count), int(count))
    assert (
        metrics["matched_return_samples"],
        metrics["scoped_return_samples"],
    ) == expected


@pytest.mark.parametrize(
    "trend,expected",
    [
        ({}, (-2.0, "falling")),
        ({"status": "available"}, (0.0, "stable")),
        ({"status": "insufficient", "direction": "rising"}, (None, "insufficient")),
        (
            {
                "status": "available",
                "direction": "rising",
                "delta_percentage_points": "2.5",
            },
            (2.5, "rising"),
        ),
        ({"status": "available", "direction": "unknown"}, (0.0, "insufficient")),
        ({"status": "available", "direction": ""}, (0.0, "stable")),
    ],
)
def test_issue_trend_keeps_available_gate_direction_and_business_fallback(
    trend: dict, expected: tuple
) -> None:
    metrics = _issue_metrics(
        {"trend_summary": trend},
        {
            "trend_summary": {
                "status": "available",
                "direction": "falling",
                "delta_percentage_points": -2,
            }
        },
        {},
    )
    assert (
        metrics["recent_change_percentage_points"],
        metrics["trend_direction"],
    ) == expected


def test_invalid_counts_precede_invalid_rate_conversion() -> None:
    with pytest.raises(ValueError, match="invalid literal"):
        _issue_metrics(
            {"record_count": "bad-count", "product_reason_rate": "bad-rate"}, {}, {}
        )


@pytest.mark.parametrize(
    "matched,scoped,quality,status",
    [
        (9, 10, [], "diagnostic_only"),
        (10, 9, [], "diagnostic_only"),
        (10, 10, [], "verification_ready"),
        (10, 10, ["text_quality"], "diagnostic_only"),
    ],
)
def test_issue_readiness_preserves_ten_sample_boundary_and_quality_priority(
    matched: int, scoped: int, quality: list, status: str
) -> None:
    result = _issue_readiness(
        {"quality_issue_codes": quality},
        {},
        "模拟商品",
        None,
        {"matched_return_samples": matched, "scoped_return_samples": scoped},
    )
    assert result["status"] == status


@pytest.mark.parametrize(
    "dimension,row,expected",
    [
        ("variant", {}, ("", None, None, "issue.reason.X")),
        (
            "variant",
            {
                "id": " existing ",
                "value": " ignored ",
                "product_name": " P ",
                "product_sku": " S ",
            },
            (" existing ", "P", "S", " existing "),
        ),
        ("variant", {"value": " S "}, ("", None, "S", "issue.X.9048c8ab899d")),
        ("product", {"value": " P "}, ("", "P", None, "issue.X.c8763b60ef7a")),
        (
            "unexpected",
            {"product_name": "P", "product_sku": "S"},
            ("", "P", "S", "issue.X.c3fde46db078"),
        ),
        ("variant", {"id": 0, "value": 0}, ("", None, None, "issue.reason.X")),
        (
            "variant",
            {"id": False, "product_name": "P", "product_sku": "S"},
            ("", "P", "S", "issue.X.827134e2832e"),
        ),
        (
            "product",
            {"value": " new ", "product_name": " old ", "product_sku": " S "},
            ("", "new", "S", "issue.X.f0e6becf808b"),
        ),
        (
            "variant",
            {"value": " new ", "product_name": " P ", "product_sku": " old "},
            ("", "P", "new", "issue.X.ceba41971e60"),
        ),
    ],
)
def test_issue_scope_keeps_id_whitespace_fallback_and_stable_hash(
    dimension: str, row: dict, expected: tuple
) -> None:
    original = deepcopy(row)
    assert _issue_scope("X", dimension, row) == expected
    assert row == original
