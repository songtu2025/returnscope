from __future__ import annotations

from typing import Any

import pandas as pd

from return_analysis.data import (
    AnalysisData,
)
from return_analysis.metrics import (
    REVIEW_STATUSES,
    category_summary,
    claim_relation_summary,
    dimension_problem_over_index,
    multi_value_summary,
    problem_pair_summary,
    product_label_matrix,
    product_summary,
    review_reason_summary,
    status_summary,
)
from web_backend.analysis_services.records import _AnalysisRecords

DIMENSIONS = {
    "listing": "Listing",
    "category_b": "品类B",
    "sku": "sku",
    "asin": "asin",
}


class _AnalysisDiagnosis(_AnalysisRecords):
    def _diagnosis(
        self,
        frame: pd.DataFrame,
        focus: pd.DataFrame,
        priorities: pd.DataFrame,
        focus_code: str | None,
    ) -> dict[str, Any]:
        comments = focus.loc[
            focus["分类键"].ne(""),
            [
                "分类键",
                "sku",
                "Listing",
                "Amazon原因",
                "标准化评论",
                "证据原文",
                "处理状态",
            ],
        ].drop_duplicates(subset=["分类键"])
        return {
            "focus_code": focus_code,
            "priorities": self._priority_records(priorities.head(30)),
            "product_locations": self._records(
                dimension_problem_over_index(
                    frame,
                    "sku",
                    problem_code=focus_code,
                    min_records=1,
                    top_n=12,
                ),
                {
                    "sku": "name",
                    "记录数": "records",
                    "维度内占比": "share",
                    "提升度": "lift",
                },
            ),
            "listing_locations": self._records(
                dimension_problem_over_index(
                    frame,
                    "Listing",
                    problem_code=focus_code,
                    min_records=1,
                    top_n=12,
                ),
                {
                    "Listing": "name",
                    "记录数": "records",
                    "维度内占比": "share",
                    "提升度": "lift",
                },
            ),
            "reasons": self._records(
                category_summary(focus, "Amazon原因").head(10),
                {
                    "Amazon原因": "name",
                    "退货记录数": "records",
                    "占退货记录比例": "share",
                },
            ),
            "parts": self._records(
                multi_value_summary(focus, "部位", top_n=10),
                {
                    "部位": "name",
                    "退货记录数": "records",
                    "占退货记录比例": "share",
                },
            ),
            "claims": self._records(
                claim_relation_summary(focus),
                {"承诺关系": "name", "退货记录数": "records"},
            ),
            "pairs": self._records(
                problem_pair_summary(frame, top_n=10, focus_code=focus_code),
                {
                    "问题组合": "name",
                    "退货记录数": "records",
                    "提升度": "lift",
                    "聚焦置信度": "confidence",
                },
            ),
            "comments": self._records(
                comments.head(40),
                {
                    "分类键": "classification_key",
                    "Listing": "listing",
                    "Amazon原因": "reason",
                    "标准化评论": "comment",
                    "证据原文": "evidence",
                    "处理状态": "status",
                },
            ),
        }

    def _products(self, frame: pd.DataFrame, dimension_key: str) -> dict[str, Any]:
        dimension_key = dimension_key if dimension_key in DIMENSIONS else "listing"
        dimension = DIMENSIONS[dimension_key]
        summary = product_summary(frame, dimension)
        matrix = product_label_matrix(frame, dimension)
        matrix_rows = [
            {
                "name": str(index),
                "values": [
                    {"label": str(label), "records": int(value)}
                    for label, value in row.items()
                ],
            }
            for index, row in matrix.iterrows()
        ]
        return {
            "dimension": dimension_key,
            "summary": self._records(
                summary.head(50),
                {
                    dimension: "name",
                    "退货记录数": "records",
                    "有评论数": "text_records",
                    "需复核数": "review_records",
                    "文本覆盖率": "text_coverage",
                    "复核占比": "review_rate",
                    "首要问题": "top_problem",
                },
            ),
            "matrix": matrix_rows,
        }

    def _quality(self, frame: pd.DataFrame, data: AnalysisData) -> dict[str, Any]:
        classification_keys = set(frame.loc[frame["分类键"].ne(""), "分类键"])
        unknowns = data.unknowns.loc[
            data.unknowns["分类键"].isin(classification_keys)
        ].copy()
        unknowns["重复记录数"] = pd.to_numeric(
            unknowns["重复记录数"], errors="coerce"
        ).fillna(0)
        unknowns = unknowns.sort_values("重复记录数", ascending=False, kind="stable")
        review = frame.loc[
            frame["处理状态"].isin(REVIEW_STATUSES) & frame["分类键"].ne("")
        ].drop_duplicates(subset=["分类键"])
        conflict_count = int(review["复核原因"].str.contains("冲突", na=False).sum())
        unknown_count = int(unknowns["重复记录数"].sum())
        return {
            "metrics": {
                "review_comments": len(review),
                "conflicts": conflict_count,
                "unknown_records": unknown_count,
            },
            "listing_quality": self._listing_quality(frame),
            "statuses": self._records(
                status_summary(frame),
                {
                    "处理状态": "code",
                    "状态名称": "name",
                    "退货记录数": "records",
                    "占比": "share",
                },
            ),
            "review_reasons": self._records(
                review_reason_summary(frame),
                {"复核原因": "name", "去重评论数": "records"},
            ),
            "claims": self._records(
                claim_relation_summary(frame),
                {"承诺关系": "name", "退货记录数": "records"},
            ),
            "unknowns": self._records(
                unknowns.head(30),
                {
                    "重复记录数": "records",
                    "Amazon原因": "reason",
                    "标准化评论": "comment",
                    "标准化观点": "opinion",
                    "证据原文": "evidence",
                    "未映射原因": "unmapped_reason",
                },
            ),
        }

    def _details(
        self, frame: pd.DataFrame, page: int, page_size: int
    ) -> dict[str, Any]:
        page_size = min(max(page_size, 10), 100)
        pages = max((len(frame) + page_size - 1) // page_size, 1)
        page = min(max(page, 1), pages)
        start = (page - 1) * page_size
        rows = frame.iloc[start : start + page_size]
        columns = {
            "return-date": "return_date",
            "order-id": "order_id",
            "sku": "sku",
            "asin": "asin",
            "品类A": "category_a",
            "品类B": "category_b",
            "Listing": "listing",
            "款式": "style",
            "颜色": "color",
            "尺码": "size",
            "Amazon原因": "reason",
            "问题标签": "problem_labels",
            "主因标签": "primary_labels",
            "部位": "parts",
            "处理状态": "status",
            "标准化评论": "comment",
            "证据原文": "evidence",
            "复核原因": "review_reason",
        }
        return {
            "total": len(frame),
            "page": page,
            "page_size": page_size,
            "pages": pages,
            "records": self._records(rows, columns),
        }

    @staticmethod
    def _focus_code(priorities: pd.DataFrame, requested: str | None) -> str | None:
        if priorities.empty:
            return None
        codes = set(priorities["标签编码"].astype(str))
        return requested if requested in codes else str(priorities.iloc[0]["标签编码"])
