from __future__ import annotations

from collections import Counter
from itertools import combinations, groupby
from operator import itemgetter

import pandas as pd

from return_analysis.calculations.common import explode_labels
from return_analysis.calculations.filters import filter_details


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
