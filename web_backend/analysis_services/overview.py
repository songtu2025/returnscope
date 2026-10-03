from __future__ import annotations

from typing import Any

import pandas as pd

from return_analysis.data import (
    AnalysisData,
)
from return_analysis.metrics import (
    listing_problem_summary,
    overview_metrics,
    size_direction_summary,
    specific_part_summary,
)
from web_backend.analysis_services.records import _AnalysisRecords


class _AnalysisOverview(_AnalysisRecords):
    def _overview(
        self,
        frame: pd.DataFrame,
        data: AnalysisData,
        priorities: pd.DataFrame,
        metrics: dict[str, int | float],
    ) -> dict[str, Any]:
        return {
            "metrics": metrics,
            "top_problems": self._priority_records(priorities.head(10)),
            "listing_problems": self._records(
                listing_problem_summary(frame, data.label_catalog).head(12),
                {
                    "标签编码": "code",
                    "标签名称": "name",
                    "一级分类": "group",
                    "退货记录数": "records",
                    "问题记录占比": "share",
                    "有效Listing覆盖率": "listing_coverage",
                    "Top Listing集中度": "top_listing_share",
                    "覆盖范围": "coverage_label",
                },
            ),
            "listing_quality": self._listing_quality(frame),
            "size_directions": self._records(
                size_direction_summary(frame).head(24),
                {
                    "Listing": "listing",
                    "尺码方向": "direction",
                    "记录数": "records",
                    "Listing内占比": "share",
                    "提升度": "lift",
                },
            ),
            "parts": self._records(
                specific_part_summary(frame).head(20),
                {
                    "Listing": "listing",
                    "部位": "part",
                    "记录数": "records",
                    "Listing内占比": "share",
                },
            ),
        }

    @staticmethod
    def _metric_summary(frame: pd.DataFrame) -> dict[str, int | float]:
        metrics = overview_metrics(frame)
        matched = int(frame["Listing"].ne("").sum())
        labeled = int(frame["问题标签"].fillna("").str.strip().ne("").sum())
        text_records = int(metrics["text_records"])
        metrics.update(
            {
                "listing_count": int(
                    frame.loc[frame["Listing"].ne(""), "Listing"].nunique()
                ),
                "product_matched": matched,
                "product_match_rate": matched / len(frame) if len(frame) else 0.0,
                "labeled_records": labeled,
                "label_coverage": labeled / text_records if text_records else 0.0,
            }
        )
        return metrics
