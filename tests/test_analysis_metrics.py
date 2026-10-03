from datetime import date

import pandas as pd
import pytest
from analysis_metric_helpers import catalog as _catalog
from analysis_metric_helpers import details as _details

from return_analysis.metrics import (
    category_summary,
    claim_relation_summary,
    explode_labels,
    filter_details,
    label_summary,
    multi_value_summary,
    overview_metrics,
    pareto_problem_summary,
    product_label_matrix,
    product_summary,
    review_reason_summary,
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


def test_product_label_matrix_uses_primary_labels() -> None:
    matrix = product_label_matrix(_details(), "sku")

    assert matrix.loc["SKU-1", "偏小"] == 2


def test_review_reason_summary_deduplicates_classification_key() -> None:
    details = pd.concat([_details(), _details().iloc[[1]]], ignore_index=True)

    result = review_reason_summary(details)

    assert result.loc[0, "去重评论数"] == 1


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
