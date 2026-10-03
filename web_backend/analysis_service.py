from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from return_analysis.data import (
    AnalysisData,
)
from return_analysis.metrics import (
    REVIEW_STATUSES,
    filter_details,
    problem_priority_summary,
    review_reason_summary,
    split_values,
)
from web_backend.analysis_services.diagnosis import _AnalysisDiagnosis
from web_backend.analysis_services.filters import AnalysisFilters
from web_backend.analysis_services.overview import _AnalysisOverview
from web_backend.analysis_services.task_data import _AnalysisTaskData
from web_backend.database import Database

ANALYSIS_VIEWS = {"all", "overview", "diagnosis", "products", "quality", "details"}


class AnalysisService(_AnalysisTaskData, _AnalysisOverview, _AnalysisDiagnosis):
    def __init__(self, database: Database) -> None:
        self.database = database
        self._cached_response = lru_cache(maxsize=64)(self._build_response)

    def get(self, task_id: str, filters: AnalysisFilters) -> dict[str, Any]:
        task = self._task_source(task_id, filters.listing)
        result_path = Path(str(task["result_file_path"]))
        product_path = Path(str(task["product_file_path"]))
        return self._cached_response(
            task_id,
            int(task["revision"]),
            result_path.stat().st_mtime_ns,
            product_path.stat().st_mtime_ns,
            filters,
        )

    def _build_response(
        self,
        task_id: str,
        _task_revision: int,
        _result_mtime: int,
        _product_mtime: int,
        filters: AnalysisFilters,
    ) -> dict[str, Any]:
        task = self._task_source(task_id, filters.listing)
        data, details, filtered = self._prepare_filtered(task, filters)
        view = filters.view if filters.view in ANALYSIS_VIEWS else "all"
        metrics = self._metric_summary(filtered)
        payload = {
            "task": self._task_payload(task),
            "filters": self._filter_payload(details, data),
            "scope": {
                "total_records": len(details),
                "filtered_records": len(filtered),
            },
            "overview": {"metrics": metrics},
            "quality_gate": self._quality_gate(filtered),
            "view": view,
        }

        priorities = pd.DataFrame()
        if view in {"all", "overview", "diagnosis"}:
            priorities = problem_priority_summary(filtered, data.label_catalog)
        if view in {"all", "overview"}:
            payload["overview"] = self._overview(
                filtered,
                data,
                priorities,
                metrics,
            )
        if view in {"all", "diagnosis"}:
            focus_code = self._focus_code(priorities, filters.focus_problem)
            focus_details = (
                filter_details(filtered, problem_codes=[focus_code])
                if focus_code
                else filtered.iloc[0:0].copy()
            )
            payload["diagnosis"] = self._diagnosis(
                filtered,
                focus_details,
                priorities,
                focus_code,
            )
        if view in {"all", "products"}:
            payload["products"] = self._products(filtered, filters.dimension)
        if view in {"all", "quality"}:
            payload["quality"] = self._quality(filtered, data)
        if view in {"all", "details"}:
            payload["details"] = self._details(
                filtered,
                filters.page,
                filters.page_size,
            )
        return payload

    def export_filtered(
        self, task_id: str, filters: AnalysisFilters
    ) -> tuple[bytes, str]:
        task = self._task_source(task_id, filters.listing)
        data, _, filtered = self._prepare_filtered(task, filters)
        export = filtered.drop(columns=["return_date", "has_text"], errors="ignore")
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            export.to_excel(writer, sheet_name="筛选明细", index=False)
            semantics = data.semantics.loc[
                data.semantics["分类键"].isin(filtered["分类键"])
            ].copy()
            semantics["重复记录数"] = semantics["分类键"].map(
                filtered["分类键"].value_counts()
            )
            semantics.to_excel(writer, sheet_name="语义层级", index=False)
        filename = f"{task_id}-filtered-analysis-v{task['result_version']}.xlsx"
        return output.getvalue(), filename

    def _prepare_filtered(
        self, task: dict[str, Any], filters: AnalysisFilters
    ) -> tuple[AnalysisData, pd.DataFrame, pd.DataFrame]:
        data = self._load_task_data(task)
        details = self._apply_task_scope(data.details, task)
        filtered = self._filter(details, filters, data.semantics)
        return data, details, filtered

    @staticmethod
    def _task_payload(task: dict[str, Any]) -> dict[str, Any]:
        return {
            key: task.get(key)
            for key in (
                "id",
                "title",
                "store",
                "listing",
                "result_version",
                "completed_at",
                "dataset_name",
                "dataset_version",
                "primary_model",
                "owner_name",
                "delivery_scope",
            )
        }

    def _filter_payload(
        self,
        frame: pd.DataFrame,
        data: AnalysisData,
    ) -> dict[str, Any]:
        valid_dates = frame["return_date"].dropna()
        labels = data.label_catalog.rename(
            columns={
                "标签编码": "code",
                "标签名称": "name",
                "一级分类": "group",
            }
        )
        if "完整路径" in data.semantics:
            paths = data.semantics.drop_duplicates("标签编码").set_index("标签编码")[
                "完整路径"
            ]
            labels = labels.copy()
            labels["label_path"] = (
                labels["code"]
                .map(paths)
                .fillna("")
                .map(lambda value: str(value).split(" → ") if value else [])
            )
        relations = sorted(
            {
                value
                for item in frame["Listing承诺关系"]
                for value in split_values(item)
                if value and value != "NONE"
            }
        )
        return {
            "date_min": valid_dates.min().date().isoformat()
            if not valid_dates.empty
            else None,
            "date_max": valid_dates.max().date().isoformat()
            if not valid_dates.empty
            else None,
            "category_as": self._options(frame, "品类A"),
            "category_bs": self._options(frame, "品类B"),
            "listings": self._options(frame, "Listing"),
            "skus": self._options(frame, "sku"),
            "asins": self._options(frame, "asin"),
            "reasons": self._options(frame, "Amazon原因"),
            "statuses": self._options(frame, "处理状态"),
            "claim_relations": relations,
            "problem_labels": self._records(labels),
        }

    @staticmethod
    def _quality_gate(frame: pd.DataFrame) -> dict[str, Any]:
        text_records = int(frame["has_text"].sum())
        labeled_records = int(frame["问题标签"].fillna("").str.strip().ne("").sum())
        review_records = int(frame["处理状态"].isin(REVIEW_STATUSES).sum())
        review = frame.loc[
            frame["处理状态"].isin(REVIEW_STATUSES) & frame["分类键"].ne("")
        ].drop_duplicates(subset=["分类键"])
        reasons = AnalysisService._records(
            review_reason_summary(review).head(5),
            {"复核原因": "name", "去重评论数": "records"},
        )
        unusable = text_records > 0 and labeled_records == 0
        return {
            "status": "unusable" if unusable else "ready",
            "text_records": text_records,
            "labeled_records": labeled_records,
            "label_coverage": labeled_records / text_records if text_records else 0.0,
            "review_records": review_records,
            "review_rate": review_records / text_records if text_records else 0.0,
            "review_reasons": reasons,
        }
