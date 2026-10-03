from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from return_analysis.calculations.common import (
    REVIEW_STATUSES,
    STATUS_NAMES,
    explode_labels,
    split_values,
)


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
