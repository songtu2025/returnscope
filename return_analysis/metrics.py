from __future__ import annotations

import pandas as pd

from return_analysis.calculations.common import (
    REVIEW_STATUSES,
    SIZE_DIRECTION_NAMES,
    SPECIFIC_PART_EXCLUSIONS,
    STATUS_NAMES,
    explode_labels,
    label_codes,
    split_values,
)
from return_analysis.calculations.diagnosis import (
    dimension_problem_over_index,
    problem_pair_summary,
    problem_variant_matrix,
)
from return_analysis.calculations.filters import (
    filter_details,
)
from return_analysis.calculations.priorities import (
    common_problem_summary,
    problem_priority_summary,
)
from return_analysis.calculations.summaries import (
    category_summary,
    claim_relation_summary,
    label_summary,
    multi_value_summary,
    overview_metrics,
    pareto_problem_summary,
    product_label_matrix,
    product_summary,
    review_reason_summary,
    status_summary,
    trend_summary,
)

__all__ = [
    "REVIEW_STATUSES",
    "STATUS_NAMES",
    "SIZE_DIRECTION_NAMES",
    "SPECIFIC_PART_EXCLUSIONS",
    "split_values",
    "label_codes",
    "explode_labels",
    "filter_details",
    "overview_metrics",
    "status_summary",
    "category_summary",
    "label_summary",
    "pareto_problem_summary",
    "multi_value_summary",
    "trend_summary",
    "product_summary",
    "product_label_matrix",
    "review_reason_summary",
    "claim_relation_summary",
    "problem_priority_summary",
    "common_problem_summary",
    "listing_problem_summary",
    "size_direction_summary",
    "specific_part_summary",
    "listing_quality_summary",
    "problem_variant_matrix",
    "dimension_problem_over_index",
    "problem_pair_summary",
]


def listing_problem_summary(
    frame: pd.DataFrame,
    label_catalog: pd.DataFrame,
    min_records: int = 5,
    min_share: float = 0.01,
) -> pd.DataFrame:
    columns = [
        "标签编码",
        "标签名称",
        "一级分类",
        "退货记录数",
        "问题记录占比",
        "影响Listing数",
        "有效Listing数",
        "Listing覆盖率",
        "有效Listing覆盖率",
        "Listing中位占比",
        "Listing最小占比",
        "Listing最大占比",
        "Top Listing集中度",
        "覆盖范围",
    ]
    work = frame.loc[frame["Listing"].ne("") & frame["问题标签"].ne("")].reset_index(
        drop=True
    )
    if work.empty:
        return pd.DataFrame(columns=columns)

    labels = explode_labels(work, "问题标签", keep_columns=["Listing"])
    if labels.empty:
        return pd.DataFrame(columns=columns)

    listings = sorted(work["Listing"].unique())
    listing_totals = work.groupby("Listing").size().reindex(listings)
    counts = (
        labels.groupby(["标签编码", "Listing"])["_record_id"]
        .nunique()
        .unstack(fill_value=0)
        .reindex(columns=listings, fill_value=0)
    )
    shares = counts.div(listing_totals, axis=1).fillna(0.0)
    record_counts = counts.sum(axis=1)
    effective = counts.ge(min_records) & shares.ge(min_share)

    result = pd.DataFrame(
        {
            "标签编码": counts.index,
            "退货记录数": record_counts.values,
            "问题记录占比": (record_counts / len(work)).values,
            "影响Listing数": counts.gt(0).sum(axis=1).values,
            "有效Listing数": effective.sum(axis=1).values,
            "Listing中位占比": shares.median(axis=1).values,
            "Listing最小占比": shares.min(axis=1).values,
            "Listing最大占比": shares.max(axis=1).values,
            "Top Listing集中度": (
                counts.max(axis=1).div(record_counts).fillna(0.0).values
            ),
        }
    )
    result["Listing覆盖率"] = result["影响Listing数"] / len(listings)
    result["有效Listing覆盖率"] = result["有效Listing数"] / len(listings)
    result = result.merge(label_catalog, on="标签编码", how="left")
    result["标签名称"] = result["标签名称"].fillna(result["标签编码"])
    result["一级分类"] = result["一级分类"].fillna("未分类")
    if len(listings) == 1:
        result["覆盖范围"] = "单 Listing 范围"
    else:
        result["覆盖范围"] = result["有效Listing覆盖率"].map(
            lambda value: (
                "全站共性"
                if value >= 0.7
                else "部分 Listing 共性"
                if value >= 0.3
                else "局部问题"
            )
        )
    return result.sort_values(
        ["有效Listing覆盖率", "Listing中位占比", "退货记录数"],
        ascending=[False, False, False],
    )[columns].reset_index(drop=True)


def size_direction_summary(frame: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "Listing",
        "标签编码",
        "尺码方向",
        "记录数",
        "Listing退货记录数",
        "Listing内占比",
        "全站占比",
        "提升度",
    ]
    work = frame.loc[frame["Listing"].ne("")].reset_index(drop=True)
    if work.empty:
        return pd.DataFrame(columns=columns)

    labels = explode_labels(work, "主因标签", keep_columns=["Listing"])
    labels = labels.loc[labels["标签编码"].isin(SIZE_DIRECTION_NAMES)]
    if labels.empty:
        return pd.DataFrame(columns=columns)

    result = labels.groupby(["Listing", "标签编码"], as_index=False).agg(
        记录数=("_record_id", "nunique")
    )
    listing_totals = (
        work.groupby("Listing", as_index=False)
        .size()
        .rename(columns={"size": "Listing退货记录数"})
    )
    overall = labels.groupby("标签编码", as_index=False).agg(
        全站记录数=("_record_id", "nunique")
    )
    result = result.merge(listing_totals, on="Listing", how="left")
    result = result.merge(overall, on="标签编码", how="left")
    result["尺码方向"] = result["标签编码"].map(SIZE_DIRECTION_NAMES)
    result["Listing内占比"] = result["记录数"] / result["Listing退货记录数"]
    result["全站占比"] = result["全站记录数"] / len(work)
    result["提升度"] = result["Listing内占比"] / result["全站占比"]
    return (
        result[columns]
        .sort_values(
            ["Listing", "记录数"],
            ascending=[True, False],
        )
        .reset_index(drop=True)
    )


def specific_part_summary(frame: pd.DataFrame) -> pd.DataFrame:
    columns = ["Listing", "部位", "记录数", "Listing退货记录数", "Listing内占比"]
    work = frame.loc[frame["Listing"].ne("")].reset_index(drop=True)
    if work.empty:
        return pd.DataFrame(columns=columns)

    parts = work.loc[:, ["Listing", "部位"]].copy()
    parts["_record_id"] = range(len(parts))
    parts["部位"] = parts["部位"].map(
        lambda value: list(dict.fromkeys(split_values(value)))
    )
    parts = parts.explode("部位")
    parts = parts.loc[
        parts["部位"].notna()
        & parts["部位"].ne("")
        & ~parts["部位"].isin(SPECIFIC_PART_EXCLUSIONS)
    ]
    if parts.empty:
        return pd.DataFrame(columns=columns)

    result = parts.groupby(["Listing", "部位"], as_index=False).agg(
        记录数=("_record_id", "nunique")
    )
    listing_totals = (
        work.groupby("Listing", as_index=False)
        .size()
        .rename(columns={"size": "Listing退货记录数"})
    )
    result = result.merge(listing_totals, on="Listing", how="left")
    result["Listing内占比"] = result["记录数"] / result["Listing退货记录数"]
    return (
        result[columns]
        .sort_values(
            ["记录数", "Listing"],
            ascending=[False, True],
        )
        .reset_index(drop=True)
    )


def listing_quality_summary(frame: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "Listing",
        "退货记录数",
        "有评论率",
        "标签覆盖率",
        "无文本率",
        "未知语义率",
        "需复核率",
    ]
    work = frame.loc[frame["Listing"].ne("")].copy()
    if work.empty:
        return pd.DataFrame(columns=columns)

    rows = []
    for listing, group in work.groupby("Listing"):
        total = len(group)
        rows.append(
            {
                "Listing": listing,
                "退货记录数": total,
                "有评论率": float(group["has_text"].mean()),
                "标签覆盖率": float(group["问题标签"].ne("").mean()),
                "无文本率": float(group["处理状态"].eq("NO_TEXT_EVIDENCE").mean()),
                "未知语义率": float(group["处理状态"].eq("UNKNOWN_SEMANTIC").mean()),
                "需复核率": float(group["处理状态"].isin(REVIEW_STATUSES).mean()),
            }
        )
    return (
        pd.DataFrame(rows, columns=columns)
        .sort_values("退货记录数", ascending=False)
        .reset_index(drop=True)
    )
