from __future__ import annotations

import json
from typing import Any

import pandas as pd

from return_analysis.metrics import (
    listing_quality_summary,
)


class _AnalysisRecords:
    def _priority_records(self, frame: pd.DataFrame) -> list[dict[str, Any]]:
        return self._records(
            frame,
            {
                "标签编码": "code",
                "标签名称": "name",
                "一级分类": "group",
                "退货记录数": "records",
                "退货构成占比": "share",
                "变化百分点": "change_pp",
                "影响SKU数": "sku_count",
                "Top SKU集中度": "top_sku_share",
                "多问题记录数": "multi_problem_records",
                "Listing冲突数": "listing_conflicts",
                "需复核记录数": "review_records",
            },
        )

    def _listing_quality(self, frame: pd.DataFrame) -> list[dict[str, Any]]:
        return self._records(
            listing_quality_summary(frame).head(30),
            {
                "Listing": "listing",
                "退货记录数": "records",
                "有评论率": "text_rate",
                "标签覆盖率": "label_coverage",
                "无文本率": "no_text_rate",
                "未知语义率": "unknown_rate",
                "需复核率": "review_rate",
            },
        )

    @staticmethod
    def _options(frame: pd.DataFrame, column: str) -> list[str]:
        return sorted({str(value) for value in frame[column] if str(value).strip()})

    @staticmethod
    def _records(
        frame: pd.DataFrame,
        columns: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        selected = frame
        if columns:
            available = {key: value for key, value in columns.items() if key in frame}
            selected = frame.loc[:, list(available)].rename(columns=available)
        return json.loads(
            selected.to_json(
                orient="records",
                date_format="iso",
                force_ascii=False,
            )
        )
