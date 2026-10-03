from __future__ import annotations

from collections.abc import Iterable
from typing import Any

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


def split_values(value: Any) -> list[str]:
    if value is None or pd.isna(value):
        return []
    return [item.strip() for item in str(value).split(" | ") if item.strip()]


def label_codes(value: object) -> list[str]:
    return [item.partition(":")[0].strip() for item in split_values(value)]


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
