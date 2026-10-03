from __future__ import annotations

from datetime import timedelta
from math import log

import pandas as pd

from return_analysis.calculations.common import (
    REVIEW_STATUSES,
    explode_labels,
    label_codes,
    split_values,
)
from return_analysis.calculations.summaries import label_summary


def _normalized_entropy(values: pd.Series) -> float:
    shares = values.loc[values.gt(0)]
    if len(shares) <= 1:
        return 0.0
    entropy = -sum(value * log(value) for value in shares)
    return float(entropy / log(len(shares)))


def problem_priority_summary(
    frame: pd.DataFrame,
    label_catalog: pd.DataFrame,
    comparison_days: int = 30,
) -> pd.DataFrame:
    work = frame.reset_index(drop=True).copy()
    work["_multi_problem"] = work["问题标签"].map(
        lambda value: len(label_codes(value)) > 1
    )
    work["_listing_conflict"] = work["Listing承诺关系"].map(
        lambda value: "CONTRADICTS" in split_values(value)
    )
    work["_needs_review"] = work["处理状态"].isin(REVIEW_STATUSES)
    labels = explode_labels(
        work,
        "问题标签",
        keep_columns=[
            "sku",
            "_multi_problem",
            "_listing_conflict",
            "_needs_review",
        ],
    )
    if labels.empty:
        return pd.DataFrame()

    result = labels.groupby(
        ["标签编码", "标签名称"],
        as_index=False,
    ).agg(
        退货记录数=("_record_id", "nunique"),
        影响SKU数=("sku", lambda values: values[values.ne("")].nunique()),
        多问题记录数=("_multi_problem", "sum"),
        Listing冲突数=("_listing_conflict", "sum"),
        需复核记录数=("_needs_review", "sum"),
    )
    catalog = label_catalog.drop_duplicates(subset=["标签编码"])
    result = result.merge(
        catalog[["标签编码", "标签名称", "一级分类"]],
        on="标签编码",
        how="left",
        suffixes=("", "_配置"),
    )
    result["标签名称"] = result["标签名称_配置"].fillna(result["标签名称"])
    result = result.drop(columns=["标签名称_配置"])
    result["一级分类"] = result["一级分类"].fillna("未配置")
    total = len(work)
    result["退货构成占比"] = result["退货记录数"] / total

    product_counts = (
        labels.loc[labels["sku"].ne("")]
        .groupby(["标签编码", "sku"], as_index=False)
        .size()
    )
    top_products = (
        product_counts.groupby("标签编码", as_index=False)[["size"]]
        .max()
        .rename(columns={"size": "Top SKU记录数"})
    )
    result = result.merge(top_products, on="标签编码", how="left")
    result["Top SKU记录数"] = result["Top SKU记录数"].fillna(0)
    result["Top SKU集中度"] = result["Top SKU记录数"] / result["退货记录数"]

    valid_dates = work["return_date"].dropna()
    period_names = ("近30天占比", "前30天占比")
    if valid_dates.empty:
        result[period_names[0]] = float("nan")
        result[period_names[1]] = float("nan")
    else:
        end_date = valid_dates.max().date()
        current_start = end_date - timedelta(days=comparison_days - 1)
        previous_end = current_start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=comparison_days - 1)
        record_dates = work["return_date"].dt.date
        periods = (
            work.loc[record_dates.between(current_start, end_date)],
            work.loc[record_dates.between(previous_start, previous_end)],
        )
        for period_name, period in zip(period_names, periods, strict=True):
            if period.empty:
                result[period_name] = float("nan")
                continue
            shares = label_summary(
                period,
                "问题标签",
                label_catalog,
            )[["标签编码", "占退货记录比例"]].rename(
                columns={"占退货记录比例": period_name}
            )
            result = result.merge(shares, on="标签编码", how="left")
            result[period_name] = pd.to_numeric(
                result[period_name],
                errors="coerce",
            ).fillna(0.0)

    result["变化百分点"] = (result["近30天占比"] - result["前30天占比"]) * 100
    return result.sort_values(
        ["退货记录数", "标签名称"],
        ascending=[False, True],
    ).reset_index(drop=True)


def common_problem_summary(
    frame: pd.DataFrame,
    label_catalog: pd.DataFrame,
) -> pd.DataFrame:
    result = problem_priority_summary(frame, label_catalog)
    if result.empty:
        return result

    dimensions = explode_labels(
        frame,
        "问题标签",
        keep_columns=["款式", "尺码"],
    )
    if dimensions.empty:
        return result

    breadth = dimensions.groupby("标签编码", as_index=False).agg(
        影响款式数=(
            "款式",
            lambda values: values[values.ne("")].nunique(),
        ),
        影响尺码数=(
            "尺码",
            lambda values: values[values.ne("")].nunique(),
        ),
    )
    style_counts = (
        dimensions.loc[dimensions["款式"].ne("")]
        .groupby(["标签编码", "款式"], as_index=False)
        .size()
    )
    style_counts["款式份额"] = style_counts["size"].div(
        style_counts.groupby("标签编码")["size"].transform("sum")
    )
    top_styles = (
        style_counts.groupby("标签编码", as_index=False)[["size"]]
        .max()
        .rename(columns={"size": "Top款式记录数"})
    )
    concentration = style_counts.groupby(
        "标签编码",
        as_index=False,
    ).agg(
        款式HHI=("款式份额", lambda values: float((values**2).sum())),
        款式分布均衡度=("款式份额", _normalized_entropy),
    )
    result = result.merge(breadth, on="标签编码", how="left")
    result = result.merge(top_styles, on="标签编码", how="left")
    result = result.merge(concentration, on="标签编码", how="left")
    result[["影响款式数", "影响尺码数"]] = (
        result[["影响款式数", "影响尺码数"]].fillna(0).astype(int)
    )
    result["Top款式记录数"] = result["Top款式记录数"].fillna(0)
    result[["款式HHI", "款式分布均衡度"]] = result[
        ["款式HHI", "款式分布均衡度"]
    ].fillna(0.0)
    result["Top款式集中度"] = result["Top款式记录数"] / result["退货记录数"]

    style_total = frame.loc[frame["款式"].ne(""), "款式"].nunique()
    size_total = frame.loc[frame["尺码"].ne(""), "尺码"].nunique()
    result["款式覆盖率"] = result["影响款式数"] / style_total if style_total else 0.0
    result["尺码覆盖率"] = result["影响尺码数"] / size_total if size_total else 0.0
    result["覆盖范围"] = result["款式覆盖率"].map(
        lambda value: (
            "跨多数款式"
            if value >= 0.5
            else "跨部分款式"
            if value >= 0.2
            else "少数款式"
        )
    )
    return result.sort_values(
        ["款式覆盖率", "影响款式数", "退货记录数"],
        ascending=[False, False, False],
    ).reset_index(drop=True)
