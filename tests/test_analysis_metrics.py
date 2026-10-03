from datetime import date

import pandas as pd
import pytest
from analysis_metric_helpers import catalog as _catalog
from analysis_metric_helpers import details as _details

from return_analysis.metrics import (
    category_summary,
    claim_relation_summary,
    common_problem_summary,
    dimension_problem_over_index,
    explode_labels,
    filter_details,
    label_summary,
    listing_problem_summary,
    listing_quality_summary,
    multi_value_summary,
    overview_metrics,
    pareto_problem_summary,
    problem_pair_summary,
    problem_priority_summary,
    problem_variant_matrix,
    product_label_matrix,
    product_summary,
    review_reason_summary,
    size_direction_summary,
    specific_part_summary,
    split_values,
    status_summary,
    trend_summary,
)


def test_overview_metrics_uses_return_record_grain() -> None:
    result = overview_metrics(_details())

    assert result["total_records"] == 3
    assert result["text_records"] == 2
    assert result["unique_comments"] == 2
    assert result["review_records"] == 1
    assert result["text_coverage"] == 2 / 3


def test_filter_details_combines_date_and_label_filters() -> None:
    result = filter_details(
        _details(),
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 31),
        styles=["731"],
        sizes=["38-39"],
        category_bs=["薄底水鞋"],
        listings=["SK001"],
        problem_codes=["FIT_TOO_SMALL"],
        statuses=["MANUAL_REVIEW"],
    )

    assert result["分类键"].tolist() == ["key-2"]


def test_label_summary_counts_each_record_once_per_label() -> None:
    result = label_summary(_details(), "问题标签", _catalog())

    assert result.loc[0, "标签编码"] == "FIT_TOO_SMALL"
    assert result.loc[0, "退货记录数"] == 2
    comfort = result.loc[result["标签编码"].eq("COMFORT_GENERAL")].iloc[0]
    assert comfort["退货记录数"] == 1


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


def test_multi_value_summary_deduplicates_values_per_record() -> None:
    result = multi_value_summary(_details(), "部位")

    toe = result.loc[result["部位"].eq("TOE")].iloc[0]
    assert toe["退货记录数"] == 2
    assert toe["占退货记录比例"] == 2 / 3


def test_pareto_problem_summary_uses_primary_cause_share() -> None:
    result = pareto_problem_summary(_details(), _catalog())

    assert result.loc[0, "标签编码"] == "FIT_TOO_SMALL"
    assert result.loc[0, "主因贡献率"] == 1.0
    assert result.loc[0, "累计贡献率"] == 1.0


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


def test_product_label_matrix_uses_primary_labels() -> None:
    matrix = product_label_matrix(_details(), "sku")

    assert matrix.loc["SKU-1", "偏小"] == 2


def test_review_reason_summary_deduplicates_classification_key() -> None:
    details = pd.concat([_details(), _details().iloc[[1]]], ignore_index=True)

    result = review_reason_summary(details)

    assert result.loc[0, "去重评论数"] == 1


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


@pytest.mark.parametrize("value", [None, pd.NA, float("nan"), "", " | "])
def test_split_values_ignores_missing_values(value: object) -> None:
    assert split_values(value) == []


def test_explode_labels_deduplicates_codes_within_each_record() -> None:
    frame = _details()
    frame.loc[0, "问题标签"] += " | FIT_TOO_SMALL:偏小"
    result = explode_labels(frame, "问题标签", keep_columns=["sku"])
    assert len(result) == 3
    assert result["_record_id"].tolist() == [0, 0, 1]


def test_status_summary_preserves_unknown_names_and_empty_columns() -> None:
    frame = _details()
    frame.loc[0, "处理状态"] = "OTHER"
    result = status_summary(frame)
    assert result.loc[result["处理状态"].eq("OTHER"), "状态名称"].iloc[0] == "OTHER"
    assert status_summary(frame.iloc[:0]).columns.tolist() == result.columns.tolist()


def test_category_summary_uses_all_records_as_denominator() -> None:
    frame = _details()
    frame.loc[2, "Amazon原因"] = ""
    result = category_summary(frame, "Amazon原因")
    assert result["Amazon原因"].tolist() == ["TOO_SMALL"]
    assert result["占退货记录比例"].tolist() == [2 / 3]


@pytest.mark.parametrize("frequency", ["week", "month"])
def test_trend_summary_excludes_missing_dates(frequency: str) -> None:
    frame = _details()
    frame.loc[2, "return_date"] = pd.NaT
    result = trend_summary(frame, frequency)
    totals = result.groupby("统计类型")["退货记录数"].sum().to_dict()
    assert totals == {"退货记录": 2, "有评论": 2, "需复核": 1}


def test_product_summary_handles_products_without_text() -> None:
    result = product_summary(_details(), "sku").set_index("sku")
    assert result.loc["SKU-1", "首要问题"] == "偏小"
    assert result.loc["SKU-2", "文本覆盖率"] == 0
    assert result.loc["SKU-2", "复核占比"] == 0


def test_claim_relation_summary_excludes_none_and_blank() -> None:
    result = claim_relation_summary(_details())
    assert result.to_dict("records") == [{"承诺关系": "CONTRADICTS", "退货记录数": 1}]
