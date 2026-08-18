from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from datetime import date, timedelta
from itertools import combinations, groupby
from math import log
from operator import itemgetter

import pandas as pd

REVIEW_STATUSES = {
    "SECONDARY_REVIEW",
    "MANUAL_REVIEW",
    "UNKNOWN_SEMANTIC",
    "MODEL_ERROR",
}

STATUS_NAMES = {
    "AUTO_APPROVED": "自动通过",
    "NO_TEXT_EVIDENCE": "无文本证据",
    "MANUAL_REVIEW": "人工复核",
    "UNKNOWN_SEMANTIC": "未知语义",
    "SECONDARY_REVIEW": "待二次复核",
    "MODEL_ERROR": "模型错误",
}

SIZE_DIRECTION_NAMES = {
    "FIT_TOO_LARGE": "偏大",
    "FIT_TOO_SMALL": "偏小",
    "FIT_TOO_LONG": "偏长",
    "FIT_TOO_SHORT": "偏短",
    "FIT_TOO_LOOSE_WIDE": "偏松宽",
    "FIT_TOO_TIGHT_NARROW": "偏紧窄",
    "FIT_UNSPECIFIED": "方向不明",
}

SPECIFIC_PART_EXCLUSIONS = {"WHOLE_SHOE", "UNSPECIFIED"}


def split_values(value: object) -> list[str]:
    if value is None or pd.isna(value):
        return []
    return [item.strip() for item in str(value).split(" | ") if item.strip()]


def label_codes(value: object) -> list[str]:
    return [item.partition(":")[0].strip() for item in split_values(value)]


def _normalized_entropy(values: pd.Series) -> float:
    shares = values.loc[values.gt(0)]
    if len(shares) <= 1:
        return 0.0
    entropy = -sum(value * log(value) for value in shares)
    return float(entropy / log(len(shares)))


def explode_labels(
    frame: pd.DataFrame,
    column: str,
    keep_columns: Iterable[str] = (),
) -> pd.DataFrame:
    columns = [column, *keep_columns]
    work = frame.loc[:, columns].copy()
    work["_record_id"] = range(len(work))
    work["_label"] = work[column].map(split_values)
    work = work.explode("_label")
    work = work.loc[work["_label"].notna() & work["_label"].ne("")].copy()
    if work.empty:
        return pd.DataFrame(
            columns=[*keep_columns, "标签编码", "标签名称", "_record_id"]
        )

    parts = work["_label"].str.partition(":")
    work["标签编码"] = parts[0].str.strip()
    work["标签名称"] = parts[2].str.strip()
    return work.loc[
        work["标签编码"].ne(""),
        [*keep_columns, "标签编码", "标签名称", "_record_id"],
    ].drop_duplicates(subset=["_record_id", "标签编码"])


def filter_details(
    frame: pd.DataFrame,
    start_date: date | None = None,
    end_date: date | None = None,
    skus: Iterable[str] = (),
    asins: Iterable[str] = (),
    category_as: Iterable[str] = (),
    category_bs: Iterable[str] = (),
    listings: Iterable[str] = (),
    styles: Iterable[str] = (),
    sizes: Iterable[str] = (),
    reasons: Iterable[str] = (),
    statuses: Iterable[str] = (),
    problem_codes: Iterable[str] = (),
    claim_relations: Iterable[str] = (),
) -> pd.DataFrame:
    result = frame.copy()
    if start_date is not None:
        result = result.loc[result["return_date"].dt.date >= start_date]
    if end_date is not None:
        result = result.loc[result["return_date"].dt.date <= end_date]

    filters = (
        ("sku", set(skus)),
        ("asin", set(asins)),
        ("品类A", set(category_as)),
        ("品类B", set(category_bs)),
        ("Listing", set(listings)),
        ("款式", set(styles)),
        ("尺码", set(sizes)),
        ("Amazon原因", set(reasons)),
        ("处理状态", set(statuses)),
    )
    for column, selected in filters:
        if selected:
            result = result.loc[result[column].isin(selected)]

    selected_codes = set(problem_codes)
    if selected_codes:
        result = result.loc[
            result["问题标签"].map(
                lambda value: bool(selected_codes.intersection(label_codes(value)))
            )
        ]

    selected_relations = set(claim_relations)
    if selected_relations:
        result = result.loc[
            result["Listing承诺关系"].map(
                lambda value: bool(selected_relations.intersection(split_values(value)))
            )
        ]
    return result.copy()


def overview_metrics(frame: pd.DataFrame) -> dict[str, int | float]:
    total = len(frame)
    text_records = int(frame["has_text"].sum())
    auto_approved = int(frame["处理状态"].eq("AUTO_APPROVED").sum())
    review_records = int(frame["处理状态"].isin(REVIEW_STATUSES).sum())
    unique_comments = int(frame.loc[frame["分类键"].ne(""), "分类键"].nunique())
    return {
        "total_records": total,
        "text_records": text_records,
        "unique_comments": unique_comments,
        "auto_approved": auto_approved,
        "review_records": review_records,
        "sku_count": int(frame.loc[frame["sku"].ne(""), "sku"].nunique()),
        "text_coverage": text_records / total if total else 0.0,
        "auto_rate": auto_approved / text_records if text_records else 0.0,
        "review_rate": review_records / text_records if text_records else 0.0,
    }


def status_summary(frame: pd.DataFrame) -> pd.DataFrame:
    counts = frame["处理状态"].value_counts().rename_axis("处理状态")
    result = counts.rename("退货记录数").reset_index()
    result["状态名称"] = result["处理状态"].map(STATUS_NAMES).fillna(result["处理状态"])
    total = len(frame)
    result["占比"] = result["退货记录数"] / total if total else 0.0
    return result[["处理状态", "状态名称", "退货记录数", "占比"]]


def category_summary(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    values = frame.loc[frame[column].ne(""), column]
    counts = values.value_counts().rename_axis(column)
    result = counts.rename("退货记录数").reset_index()
    total = len(frame)
    result["占退货记录比例"] = result["退货记录数"] / total if total else 0.0
    return result


def label_summary(
    frame: pd.DataFrame,
    column: str,
    label_catalog: pd.DataFrame,
    top_n: int | None = None,
) -> pd.DataFrame:
    exploded = explode_labels(frame, column)
    if exploded.empty:
        return pd.DataFrame(
            columns=[
                "标签编码",
                "标签名称",
                "一级分类",
                "退货记录数",
                "占退货记录比例",
            ]
        )

    counts = (
        exploded.groupby(["标签编码", "标签名称"], as_index=False)
        .size()
        .rename(columns={"size": "退货记录数"})
    )
    catalog = label_catalog.drop_duplicates(subset=["标签编码"])
    result = counts.merge(
        catalog[["标签编码", "标签名称", "一级分类"]],
        on="标签编码",
        how="left",
        suffixes=("", "_配置"),
    )
    result["标签名称"] = result["标签名称_配置"].fillna(result["标签名称"])
    result = result.drop(columns=["标签名称_配置"])
    total = len(frame)
    result["占退货记录比例"] = result["退货记录数"] / total if total else 0.0
    result = result.sort_values(
        ["退货记录数", "标签名称"],
        ascending=[False, True],
    ).reset_index(drop=True)
    return result.head(top_n) if top_n is not None else result


def pareto_problem_summary(
    frame: pd.DataFrame,
    label_catalog: pd.DataFrame,
) -> pd.DataFrame:
    result = label_summary(frame, "主因标签", label_catalog)
    if result.empty:
        result["主因贡献率"] = pd.Series(dtype=float)
        result["累计贡献率"] = pd.Series(dtype=float)
        return result

    total = result["退货记录数"].sum()
    result["主因贡献率"] = result["退货记录数"] / total
    result["累计贡献率"] = result["主因贡献率"].cumsum()
    return result


def multi_value_summary(
    frame: pd.DataFrame,
    column: str,
    top_n: int | None = None,
    excluded: Iterable[str] = (),
) -> pd.DataFrame:
    values = (
        frame[column]
        .map(lambda value: list(dict.fromkeys(split_values(value))))
        .explode()
    )
    excluded_values = set(excluded)
    values = values.loc[values.notna() & values.ne("") & ~values.isin(excluded_values)]
    if values.empty:
        return pd.DataFrame(columns=[column, "退货记录数", "占退货记录比例"])

    result = (
        values.value_counts().rename_axis(column).rename("退货记录数").reset_index()
    )
    total = len(frame)
    result["占退货记录比例"] = result["退货记录数"] / total if total else 0.0
    return result.head(top_n) if top_n is not None else result


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
        product_counts.groupby("标签编码", as_index=False)["size"]
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
        style_counts.groupby("标签编码", as_index=False)["size"]
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


def problem_variant_matrix(
    frame: pd.DataFrame,
    problem_code: str,
) -> pd.DataFrame:
    selected = filter_details(frame, problem_codes=[problem_code])
    selected = selected.loc[selected["款式"].ne("") & selected["尺码"].ne("")]
    if selected.empty:
        return pd.DataFrame()

    matrix = pd.crosstab(selected["款式"], selected["尺码"])
    row_order = matrix.sum(axis=1).sort_values(ascending=False).index
    return matrix.reindex(index=row_order).sort_index(axis=1)


def dimension_problem_over_index(
    frame: pd.DataFrame,
    dimension: str,
    problem_code: str | None = None,
    min_records: int = 5,
    top_n: int | None = 10,
) -> pd.DataFrame:
    columns = [
        dimension,
        "标签编码",
        "标签名称",
        "记录数",
        "维度内占比",
        "整体占比",
        "提升度",
        "期望记录数",
        "标准化残差",
    ]
    work = frame.loc[frame[dimension].ne("")].reset_index(drop=True)
    if work.empty:
        return pd.DataFrame(columns=columns)

    labels = explode_labels(work, "问题标签", keep_columns=[dimension])
    if problem_code:
        labels = labels.loc[labels["标签编码"].eq(problem_code)]
    if labels.empty:
        return pd.DataFrame(columns=columns)

    observed = labels.groupby([dimension, "标签编码", "标签名称"], as_index=False).agg(
        记录数=("_record_id", "nunique")
    )
    dimension_totals = (
        work.groupby(dimension, as_index=False)
        .size()
        .rename(columns={"size": "维度记录数"})
    )
    label_totals = labels.groupby("标签编码", as_index=False).agg(
        标签记录数=("_record_id", "nunique")
    )
    result = observed.merge(dimension_totals, on=dimension, how="left")
    result = result.merge(label_totals, on="标签编码", how="left")

    total = len(work)
    result["维度内占比"] = result["记录数"] / result["维度记录数"]
    result["整体占比"] = result["标签记录数"] / total
    result["提升度"] = result["维度内占比"] / result["整体占比"]
    result["期望记录数"] = result["维度记录数"] * result["整体占比"]
    row_share = result["维度记录数"] / total
    column_share = result["整体占比"]
    denominator = (result["期望记录数"] * (1 - row_share) * (1 - column_share)).pow(0.5)
    result["标准化残差"] = (
        (result["记录数"] - result["期望记录数"])
        .div(denominator.where(denominator.ne(0)))
        .fillna(0.0)
    )
    result = result.loc[result["记录数"].ge(min_records), columns]
    result = result.sort_values(
        ["标准化残差", "记录数"],
        ascending=[False, False],
    ).reset_index(drop=True)
    return result.head(top_n) if top_n is not None else result


def problem_pair_summary(
    frame: pd.DataFrame,
    top_n: int = 10,
    focus_code: str | None = None,
) -> pd.DataFrame:
    columns = [
        "问题组合",
        "退货记录数",
        "占多问题记录比例",
        "支持度",
        "聚焦置信度",
        "提升度",
    ]
    exploded = explode_labels(frame, "问题标签")
    if exploded.empty:
        return pd.DataFrame(columns=columns)

    transaction_count = exploded["_record_id"].nunique()
    label_counts = exploded.groupby("标签编码")["_record_id"].nunique()
    exploded["显示名称"] = exploded["标签名称"].where(
        exploded["标签名称"].ne(""),
        exploded["标签编码"],
    )
    ordered = exploded.sort_values(["_record_id", "标签编码"])
    rows = ordered[["_record_id", "标签编码", "显示名称"]].itertuples(
        index=False, name=None
    )
    pair_counts: Counter[tuple[str, str, str]] = Counter()
    multi_problem_records = 0
    for _, record_rows in groupby(rows, key=itemgetter(0)):
        items = [(code, name) for _, code, name in record_rows]
        record_has_pair = False
        for left, right in combinations(items, 2):
            if focus_code and focus_code not in {left[0], right[0]}:
                continue
            pair_counts[(left[0], right[0], f"{left[1]} + {right[1]}")] += 1
            record_has_pair = True
        if record_has_pair:
            multi_problem_records += 1

    if not pair_counts:
        return pd.DataFrame(columns=columns)

    result = pd.DataFrame(
        [
            {
                "左标签编码": left_code,
                "右标签编码": right_code,
                "问题组合": name,
                "退货记录数": count,
            }
            for (left_code, right_code, name), count in pair_counts.items()
        ]
    )
    result["占多问题记录比例"] = result["退货记录数"] / multi_problem_records
    result["支持度"] = result["退货记录数"] / transaction_count
    result["左标签记录数"] = result["左标签编码"].map(label_counts)
    result["右标签记录数"] = result["右标签编码"].map(label_counts)
    result["提升度"] = (
        result["退货记录数"]
        * transaction_count
        / (result["左标签记录数"] * result["右标签记录数"])
    )
    if focus_code:
        focus_count = label_counts.get(focus_code, 0)
        result["聚焦置信度"] = (
            result["退货记录数"] / focus_count if focus_count else 0.0
        )
    else:
        result["聚焦置信度"] = pd.NA
    result = result.sort_values(
        ["提升度", "退货记录数", "问题组合"],
        ascending=[False, False, True],
    ).reset_index(drop=True)
    return result[columns].head(top_n)


def trend_summary(frame: pd.DataFrame, frequency: str = "week") -> pd.DataFrame:
    work = frame.loc[frame["return_date"].notna()].copy()
    if work.empty:
        return pd.DataFrame(columns=["周期", "统计类型", "退货记录数"])

    dates = work["return_date"].dt.tz_convert(None)
    period_code = "W-SUN" if frequency == "week" else "M"
    work["周期"] = dates.dt.to_period(period_code).dt.start_time
    work["有评论"] = work["has_text"].astype(int)
    work["需复核"] = work["处理状态"].isin(REVIEW_STATUSES).astype(int)
    grouped = work.groupby("周期", as_index=False).agg(
        退货记录=("分类键", "size"),
        有评论=("有评论", "sum"),
        需复核=("需复核", "sum"),
    )
    return grouped.melt(
        id_vars="周期",
        value_vars=["退货记录", "有评论", "需复核"],
        var_name="统计类型",
        value_name="退货记录数",
    )


def product_summary(frame: pd.DataFrame, dimension: str) -> pd.DataFrame:
    work = frame.loc[frame[dimension].ne("")].copy()
    if work.empty:
        return pd.DataFrame()

    work["有评论数"] = work["has_text"].astype(int)
    work["需复核数"] = work["处理状态"].isin(REVIEW_STATUSES).astype(int)
    result = work.groupby(dimension, as_index=False).agg(
        退货记录数=("分类键", "size"),
        有评论数=("有评论数", "sum"),
        需复核数=("需复核数", "sum"),
    )
    result["文本覆盖率"] = result["有评论数"] / result["退货记录数"]
    result["复核占比"] = (
        result["需复核数"]
        .div(result["有评论数"].where(result["有评论数"].ne(0)))
        .fillna(0.0)
    )

    labels = explode_labels(work, "主因标签", keep_columns=[dimension])
    if not labels.empty:
        top_labels = (
            labels.groupby([dimension, "标签名称"], as_index=False)
            .size()
            .sort_values([dimension, "size"], ascending=[True, False])
            .drop_duplicates(subset=[dimension])
            .rename(columns={"标签名称": "首要问题"})
        )
        result = result.merge(
            top_labels[[dimension, "首要问题"]],
            on=dimension,
            how="left",
        )
    else:
        result["首要问题"] = ""

    result["首要问题"] = result["首要问题"].fillna("")
    return result.sort_values("退货记录数", ascending=False).reset_index(drop=True)


def product_label_matrix(
    frame: pd.DataFrame,
    dimension: str,
    top_products: int = 15,
    top_labels: int = 8,
) -> pd.DataFrame:
    exploded = explode_labels(frame, "主因标签", keep_columns=[dimension])
    if exploded.empty:
        return pd.DataFrame()

    product_order = exploded[dimension].value_counts().head(top_products).index.tolist()
    label_order = exploded["标签名称"].value_counts().head(top_labels).index.tolist()
    selected = exploded.loc[
        exploded[dimension].isin(product_order) & exploded["标签名称"].isin(label_order)
    ]
    matrix = pd.crosstab(selected[dimension], selected["标签名称"])
    return matrix.reindex(index=product_order, columns=label_order, fill_value=0)


def review_reason_summary(frame: pd.DataFrame, top_n: int = 12) -> pd.DataFrame:
    review = frame.loc[
        frame["处理状态"].isin(REVIEW_STATUSES) & frame["分类键"].ne("")
    ].drop_duplicates(subset=["分类键"])
    reasons = review["复核原因"].map(split_values).explode()
    reasons = reasons.loc[reasons.notna() & reasons.ne("")]
    result = (
        reasons.value_counts()
        .rename_axis("复核原因")
        .rename("去重评论数")
        .reset_index()
    )
    return result.head(top_n)


def claim_relation_summary(frame: pd.DataFrame) -> pd.DataFrame:
    relations = frame["Listing承诺关系"].map(split_values).explode()
    relations = relations.loc[
        relations.notna() & relations.ne("") & relations.ne("NONE")
    ]
    return (
        relations.value_counts()
        .rename_axis("承诺关系")
        .rename("退货记录数")
        .reset_index()
    )
