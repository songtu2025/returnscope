from __future__ import annotations

import io
import json
import pickle
import tempfile
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any

import pandas as pd

from return_analysis.data import (
    PRODUCT_DIMENSION_COLUMNS,
    AnalysisData,
    load_analysis_data,
    load_product_dimensions,
)
from return_analysis.metrics import (
    REVIEW_STATUSES,
    category_summary,
    claim_relation_summary,
    dimension_problem_over_index,
    filter_details,
    listing_problem_summary,
    listing_quality_summary,
    multi_value_summary,
    overview_metrics,
    problem_pair_summary,
    problem_priority_summary,
    product_label_matrix,
    product_summary,
    review_reason_summary,
    size_direction_summary,
    specific_part_summary,
    split_values,
    status_summary,
)
from web_backend.database import Database

DIMENSIONS = {
    "listing": "Listing",
    "category_b": "品类B",
    "sku": "sku",
    "asin": "asin",
}

ANALYSIS_CACHE_VERSION = 1
ANALYSIS_CACHE_LOCK = Lock()
ANALYSIS_VIEWS = {"all", "overview", "diagnosis", "products", "quality", "details"}


@dataclass(frozen=True)
class AnalysisFilters:
    start_date: date | None = None
    end_date: date | None = None
    category_a: str | None = None
    category_b: str | None = None
    listing: str | None = None
    sku: str | None = None
    asin: str | None = None
    reason: str | None = None
    status: str | None = None
    problem_code: str | None = None
    claim_relation: str | None = None
    dimension: str = "listing"
    focus_problem: str | None = None
    page: int = 1
    page_size: int = 50
    view: str = "all"


class AnalysisService:
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
        data = self._load_task_data(task)
        details = self._apply_task_scope(data.details, task)
        filtered = self._filter(details, filters)
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
        data = self._load_task_data(task)
        details = self._apply_task_scope(data.details, task)
        filtered = self._filter(details, filters)
        export = filtered.drop(columns=["return_date", "has_text"], errors="ignore")
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            export.to_excel(writer, sheet_name="筛选明细", index=False)
        filename = f"{task_id}-filtered-analysis-v{task['result_version']}.xlsx"
        return output.getvalue(), filename

    def _task_source(
        self,
        task_id: str,
        listing: str | None = None,
    ) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT t.id, t.title, t.status, t.store, t.listing,
                       t.result_version, t.result_file_path, t.completed_at,
                       t.revision,
                       rd.name AS dataset_name,
                       rv.version AS dataset_version,
                       cv.primary_model,
                       u.display_name AS owner_name,
                       pv.file_path AS product_file_path
                FROM tasks t
                JOIN users u ON u.id = t.owner_id
                JOIN dataset_versions rv ON rv.id = t.dataset_version_id
                JOIN datasets rd ON rd.id = rv.dataset_id
                JOIN dataset_versions pv ON pv.id = t.product_version_id
                JOIN api_config_versions cv ON cv.id = t.config_version_id
                WHERE t.id = ?
                """,
                (task_id,),
            ).fetchone()
            segment_rows = connection.execute(
                """
                SELECT id, status, result_version, result_file_path,
                       completed_at, scope_json
                FROM task_segments
                WHERE task_id = ?
                  AND status IN ('completed', 'completed_with_errors')
                ORDER BY execution_order, id
                """,
                (task_id,),
            ).fetchall()
        if row is None:
            raise ValueError("任务不存在")
        task = dict(row)
        result_path = task.get("result_file_path")
        if task["status"] not in {"completed", "cancelled"} or not result_path:
            segment = self._completed_listing_segment(segment_rows, listing)
            if segment is None:
                raise ValueError("该 Listing 尚未生成可分析结果")
            task.update(
                {
                    "listing": listing,
                    "result_version": segment["result_version"],
                    "result_file_path": segment["result_file_path"],
                    "completed_at": segment["completed_at"],
                    "delivery_scope": "segment",
                }
            )
            result_path = segment["result_file_path"]
        if not result_path or not Path(str(result_path)).exists():
            raise ValueError("任务结果文件不存在")
        return task

    @staticmethod
    def _completed_listing_segment(
        segment_rows: list[Any],
        listing: str | None,
    ) -> dict[str, Any] | None:
        if not listing:
            return None
        for row in segment_rows:
            segment = dict(row)
            try:
                scope = json.loads(str(segment.get("scope_json") or "{}"))
            except (TypeError, ValueError):
                scope = {}
            if scope.get("listing") == listing and segment.get("result_file_path"):
                return segment
        return None

    def _load_task_data(self, task: dict[str, Any]) -> AnalysisData:
        result_path = Path(str(task["result_file_path"]))
        product_path = Path(str(task["product_file_path"]))
        return self._cached_load(
            str(result_path),
            result_path.stat().st_mtime_ns,
            str(product_path),
            product_path.stat().st_mtime_ns,
            str(task["store"]),
        )

    @staticmethod
    @lru_cache(maxsize=4)
    def _cached_load(
        result_path: str,
        result_mtime: int,
        product_path: str,
        product_mtime: int,
        store: str,
    ) -> AnalysisData:
        result = Path(result_path)
        product = Path(product_path)
        cache_path = result.with_suffix(".web-cache.pkl")
        cache_key = (
            ANALYSIS_CACHE_VERSION,
            result_mtime,
            str(product.resolve()),
            product_mtime,
            store,
        )
        with ANALYSIS_CACHE_LOCK:
            try:
                with cache_path.open("rb") as cache_file:
                    stored_key, cached_data = pickle.load(cache_file)
                if stored_key == cache_key and isinstance(cached_data, AnalysisData):
                    return cached_data
            except (OSError, EOFError, pickle.PickleError, ValueError, TypeError):
                pass

            data = load_analysis_data(result)
            try:
                products = load_product_dimensions(
                    product,
                    data.details["sku"].unique(),
                    store=store,
                )
            except (KeyError, ValueError):
                products = pd.DataFrame()
            if not products.empty:
                dimensions = set(PRODUCT_DIMENSION_COLUMNS[1:])
                details = data.details.drop(
                    columns=[
                        column for column in dimensions if column in data.details
                    ],
                ).merge(products, on="sku", how="left", validate="many_to_one")
                for column in dimensions:
                    details[column] = (
                        details[column].fillna("").astype(str).str.strip()
                    )
                data = AnalysisData(
                    details=details,
                    semantics=data.semantics,
                    unknowns=data.unknowns,
                    label_catalog=data.label_catalog,
                    products=products,
                )

            temp_path: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="wb",
                    dir=cache_path.parent,
                    prefix=f"{cache_path.name}.",
                    suffix=".tmp",
                    delete=False,
                ) as cache_file:
                    temp_path = Path(cache_file.name)
                    pickle.dump(
                        (cache_key, data),
                        cache_file,
                        protocol=pickle.HIGHEST_PROTOCOL,
                    )
                temp_path.replace(cache_path)
            except (OSError, pickle.PickleError):
                if temp_path is not None:
                    temp_path.unlink(missing_ok=True)
            return data

    @staticmethod
    def _apply_task_scope(
        details: pd.DataFrame,
        task: dict[str, Any],
    ) -> pd.DataFrame:
        scoped = details.copy()
        if task.get("listing") and not scoped["Listing"].ne("").any():
            scoped["Listing"] = str(task["listing"])
        if task.get("store") and not scoped["店铺/站点"].ne("").any():
            scoped["店铺/站点"] = str(task["store"])
        return scoped

    @staticmethod
    def _filter(frame: pd.DataFrame, filters: AnalysisFilters) -> pd.DataFrame:
        return filter_details(
            frame,
            start_date=filters.start_date,
            end_date=filters.end_date,
            skus=[filters.sku] if filters.sku else (),
            asins=[filters.asin] if filters.asin else (),
            category_as=[filters.category_a] if filters.category_a else (),
            category_bs=[filters.category_b] if filters.category_b else (),
            listings=[filters.listing] if filters.listing else (),
            reasons=[filters.reason] if filters.reason else (),
            statuses=[filters.status] if filters.status else (),
            problem_codes=[filters.problem_code] if filters.problem_code else (),
            claim_relations=(
                [filters.claim_relation] if filters.claim_relation else ()
            ),
        )

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

    @staticmethod
    def _quality_gate(frame: pd.DataFrame) -> dict[str, Any]:
        text_records = int(frame["has_text"].sum())
        labeled_records = int(
            frame["问题标签"].fillna("").str.strip().ne("").sum()
        )
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
        unknowns = unknowns.sort_values(
            "重复记录数", ascending=False, kind="stable"
        )
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
