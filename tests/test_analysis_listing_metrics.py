import pandas as pd
import pytest
from analysis_metric_helpers import catalog as _catalog
from analysis_metric_helpers import details as _details

from return_analysis.metrics import (
    listing_problem_summary,
    listing_quality_summary,
    size_direction_summary,
    specific_part_summary,
)


def test_listing_problem_summary_separates_common_and_local_issues() -> None:
    details = _details()
    extra = details.iloc[[0]].copy()
    extra["分类键"] = "key-3"
    extra["sku"] = "SKU-3"
    extra["Listing"] = "SK002"
    extra["问题标签"] = "FIT_TOO_SMALL:偏小"
    details = pd.concat([details, extra], ignore_index=True)

    result = listing_problem_summary(
        details,
        _catalog(),
        min_records=1,
        min_share=0.1,
    )

    small = result.loc[result["标签编码"].eq("FIT_TOO_SMALL")].iloc[0]
    comfort = result.loc[result["标签编码"].eq("COMFORT_GENERAL")].iloc[0]
    assert small["有效Listing数"] == 2
    assert small["有效Listing覆盖率"] == 1.0
    assert small["覆盖范围"] == "全站共性"
    assert comfort["有效Listing数"] == 1


def test_size_direction_summary_uses_listing_return_denominator() -> None:
    result = size_direction_summary(_details())
    small = result.loc[
        result["Listing"].eq("SK001") & result["标签编码"].eq("FIT_TOO_SMALL")
    ].iloc[0]

    assert small["记录数"] == 2
    assert small["Listing退货记录数"] == 2
    assert small["Listing内占比"] == 1.0


def test_specific_part_summary_excludes_non_actionable_parts() -> None:
    result = specific_part_summary(_details())

    assert set(result["部位"]) == {"TOE"}
    assert result.loc[0, "记录数"] == 2
    assert result.loc[0, "Listing内占比"] == 1.0


def test_listing_quality_summary_exposes_evidence_coverage() -> None:
    result = listing_quality_summary(_details())
    sk001 = result.loc[result["Listing"].eq("SK001")].iloc[0]
    sk002 = result.loc[result["Listing"].eq("SK002")].iloc[0]

    assert sk001["标签覆盖率"] == 1.0
    assert sk001["需复核率"] == 0.5
    assert sk002["无文本率"] == 1.0


@pytest.mark.parametrize("empty", [True, False])
def test_listing_metrics_preserve_columns_without_listing(empty: bool) -> None:
    frame = _details().iloc[:0] if empty else _details().assign(Listing="")
    for calculate in (
        size_direction_summary,
        specific_part_summary,
        listing_quality_summary,
    ):
        result = calculate(frame)
        assert result.empty
        assert result.columns.tolist() == calculate(_details()).columns.tolist()
    result = listing_problem_summary(frame, _catalog())
    assert result.empty
    assert (
        result.columns.tolist()
        == listing_problem_summary(_details(), _catalog()).columns.tolist()
    )


@pytest.mark.parametrize(
    ("min_records", "min_share", "effective"),
    [(2, 1.0, 1), (3, 1.0, 0), (1, 0.5, 1), (1, 0.51, 0)],
)
def test_listing_problem_thresholds_include_the_boundary(
    min_records: int, min_share: float, effective: int
) -> None:
    code = "FIT_TOO_SMALL" if min_records >= 2 else "COMFORT_GENERAL"
    result = listing_problem_summary(_details(), _catalog(), min_records, min_share)
    selected = result.loc[result["标签编码"].eq(code)].iloc[0]
    assert selected["有效Listing数"] == effective
    assert selected["覆盖范围"] == "单 Listing 范围"


def test_specific_parts_deduplicate_and_exclude_unspecified() -> None:
    frame = _details()
    frame.loc[0, "部位"] = "TOE | TOE | WHOLE_SHOE | UNSPECIFIED"
    result = specific_part_summary(frame)
    assert result["部位"].tolist() == ["TOE"]
    assert result["记录数"].tolist() == [2]


def test_listing_quality_keeps_records_without_labels_in_denominator() -> None:
    frame = _details()
    frame.loc[1, "问题标签"] = ""
    result = listing_quality_summary(frame).set_index("Listing")
    assert result.loc["SK001", "标签覆盖率"] == 0.5
    assert result.loc["SK002", "有评论率"] == 0.0
