from __future__ import annotations

import hashlib
import re

import pandas as pd

RISK_PATTERN = re.compile(
    r"\b(not|but|however|although|reviews? say|need|wanted|compared|instead)\b",
    flags=re.IGNORECASE,
)


def classify_sample_bucket(comment: str) -> str:
    if "|" in comment:
        return "问卷式评论"
    if len(comment) <= 25:
        return "短评论"
    if len(comment) >= 150:
        return "长评论"
    if RISK_PATTERN.search(comment):
        return "语义风险评论"
    return "普通评论"


def build_gold_sample(
    unique_comments: pd.DataFrame,
    total: int = 500,
    calibration_size: int = 300,
    seed: int = 20260805,
) -> pd.DataFrame:
    if total <= 0:
        raise ValueError("抽样数量必须大于 0")
    if calibration_size < 0 or calibration_size > total:
        raise ValueError("校准集数量必须在 0 到总抽样数量之间")
    if total > len(unique_comments):
        raise ValueError("抽样数量不能超过去重评论数量")

    candidates = unique_comments.copy()
    candidates["抽样类型"] = candidates["comment_normalized"].map(
        classify_sample_bucket
    )
    candidates = candidates.sample(frac=1, random_state=seed)

    guaranteed = (
        candidates.groupby(["reason", "抽样类型"], group_keys=False)
        .head(2)
        .drop_duplicates(subset=["classification_key"])
    )
    if len(guaranteed) > total:
        guaranteed = guaranteed.sample(n=total, random_state=seed)

    remaining_count = total - len(guaranteed)
    remaining = candidates.loc[
        ~candidates["classification_key"].isin(guaranteed["classification_key"])
    ]
    if remaining_count:
        remaining = remaining.sample(n=remaining_count, random_state=seed)
        sample = pd.concat([guaranteed, remaining], ignore_index=True)
    else:
        sample = guaranteed.reset_index(drop=True)

    sample = sample.sample(frac=1, random_state=seed).reset_index(drop=True)
    sample.insert(
        0,
        "样本编号",
        sample["classification_key"].map(
            lambda value: hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
        ),
    )
    sample.insert(
        1,
        "数据用途",
        [
            "提示校准" if index < calibration_size else "不可见验收"
            for index in range(total)
        ],
    )
    sample = sample.rename(
        columns={
            "reason": "Amazon原因",
            "comment_normalized": "标准化评论",
            "record_count": "重复记录数",
        }
    )
    sample = sample[
        [
            "样本编号",
            "数据用途",
            "抽样类型",
            "Amazon原因",
            "标准化评论",
            "重复记录数",
        ]
    ]
    for column in (
        "人工问题标签",
        "人工正面标签",
        "人工主因标签",
        "人工部位",
        "人工证据",
        "是否未知语义",
        "标注备注",
    ):
        sample[column] = ""
    return sample
