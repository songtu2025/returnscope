import pandas as pd
import pytest
from analysis_metric_helpers import catalog as _catalog
from analysis_metric_helpers import details as _details

from return_analysis.metrics import (
    common_problem_summary,
    dimension_problem_over_index,
    problem_pair_summary,
    problem_priority_summary,
    problem_variant_matrix,
)


def test_problem_pair_summary_counts_multi_problem_records() -> None:
    result = problem_pair_summary(_details())

    assert result.loc[0, "问题组合"] == "不舒适 + 偏小"
    assert result.loc[0, "退货记录数"] == 1
    assert result.loc[0, "占多问题记录比例"] == 1.0
    assert result.loc[0, "支持度"] == 0.5
    assert result.loc[0, "提升度"] == 1.0

    focused = problem_pair_summary(
        _details(),
        focus_code="FIT_TOO_SMALL",
    )
    assert focused.loc[0, "聚焦置信度"] == 0.5
    assert problem_pair_summary(
        _details(),
        focus_code="QUALITY_GENERAL",
    ).empty


def test_problem_priority_summary_combines_diagnosis_dimensions() -> None:
    result = problem_priority_summary(_details(), _catalog())

    small = result.loc[result["标签编码"].eq("FIT_TOO_SMALL")].iloc[0]
    assert small["退货记录数"] == 2
    assert small["影响SKU数"] == 1
    assert small["Top SKU集中度"] == 1.0
    assert small["多问题记录数"] == 1
    assert small["Listing冲突数"] == 1
    assert small["需复核记录数"] == 1
    assert small["近30天占比"] == 0.0
    assert small["前30天占比"] == 1.0
    assert small["变化百分点"] == -100.0


def test_common_problem_summary_measures_cross_style_breadth() -> None:
    details = _details()
    extra = details.iloc[[0]].copy()
    extra["分类键"] = "key-3"
    extra["sku"] = "SKU-3"
    extra["asin"] = "ASIN-3"
    extra["款式"] = "782"
    extra["尺码"] = "40-41"
    extra["问题标签"] = "FIT_TOO_SMALL:偏小"
    details = pd.concat([details, extra], ignore_index=True)

    result = common_problem_summary(details, _catalog())
    small = result.loc[result["标签编码"].eq("FIT_TOO_SMALL")].iloc[0]

    assert small["影响款式数"] == 2
    assert small["款式覆盖率"] == 1.0
    assert small["影响尺码数"] == 2
    assert small["影响SKU数"] == 2
    assert small["Top SKU集中度"] == 2 / 3
    assert small["Top款式集中度"] == 2 / 3
    assert small["款式HHI"] == 5 / 9
    assert round(small["款式分布均衡度"], 4) == 0.9183
    assert small["覆盖范围"] == "跨多数款式"

    matrix = problem_variant_matrix(details, "FIT_TOO_SMALL")
    assert matrix.loc["731", "38-39"] == 2
    assert matrix.loc["782", "40-41"] == 1


def test_dimension_problem_over_index_compares_with_baseline() -> None:
    result = dimension_problem_over_index(
        _details(),
        "款式",
        problem_code="FIT_TOO_SMALL",
        min_records=1,
        top_n=None,
    )
    style = result.loc[result["款式"].eq("731")].iloc[0]

    assert style["记录数"] == 2
    assert style["维度内占比"] == 1.0
    assert style["整体占比"] == 2 / 3
    assert style["提升度"] == 1.5
    assert style["标准化残差"] > 0


def test_priority_summary_without_dates_keeps_missing_comparison() -> None:
    frame = _details()
    frame["return_date"] = pd.to_datetime([None] * len(frame), utc=True)
    result = problem_priority_summary(frame, _catalog())
    assert result[["近30天占比", "前30天占比", "变化百分点"]].isna().all().all()


def test_priority_summary_includes_both_period_boundaries() -> None:
    frame = _details()
    frame["return_date"] = pd.to_datetime(
        ["2026-08-01", "2026-07-03", "2026-07-02"], utc=True
    )
    result = problem_priority_summary(frame, _catalog()).set_index("标签编码")
    assert result.loc["FIT_TOO_SMALL", "近30天占比"] == 1.0
    assert result.loc["FIT_TOO_SMALL", "前30天占比"] == 0.0
    assert result.loc["COMFORT_GENERAL", "变化百分点"] == 50.0


@pytest.mark.parametrize("min_records, expected", [(2, 1), (3, 0)])
def test_dimension_summary_includes_minimum_record_threshold(
    min_records: int, expected: int
) -> None:
    result = dimension_problem_over_index(
        _details(), "sku", "FIT_TOO_SMALL", min_records, None
    )
    assert len(result) == expected


def test_problem_pairs_ignore_duplicate_labels_within_a_record() -> None:
    frame = _details()
    frame.loc[0, "问题标签"] += " | FIT_TOO_SMALL:偏小"
    result = problem_pair_summary(frame, focus_code="FIT_TOO_SMALL")
    assert result["退货记录数"].tolist() == [1]
    assert result["支持度"].tolist() == [0.5]


def test_variant_matrix_excludes_missing_dimensions() -> None:
    frame = _details()
    frame.loc[1, "尺码"] = ""
    assert problem_variant_matrix(frame, "FIT_TOO_SMALL").loc["731", "38-39"] == 1
