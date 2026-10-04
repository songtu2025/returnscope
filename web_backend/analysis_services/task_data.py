from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any

import pandas as pd

from return_analysis.data import AnalysisData
from return_analysis.metrics import (
    filter_details,
)
from web_backend.analysis_services.cache import (
    _load_product_data,
    _read_cached_data,
    _write_cached_data,
)
from web_backend.analysis_services.filters import AnalysisFilters
from web_backend.database import Database

TASK_SOURCE_QUERY = """
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
"""

COMPLETED_SEGMENTS_QUERY = """
SELECT id, status, result_version, result_file_path,
       completed_at, scope_json
FROM task_segments
WHERE task_id = ?
  AND status IN ('completed', 'completed_with_errors')
ORDER BY execution_order, id
"""

ANALYSIS_CACHE_VERSION = 1
ANALYSIS_CACHE_LOCK = Lock()


class _AnalysisTaskData:
    database: Database

    def _task_source(
        self,
        task_id: str,
        listing: str | None = None,
    ) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                TASK_SOURCE_QUERY,
                (task_id,),
            ).fetchone()
            segment_rows = connection.execute(
                COMPLETED_SEGMENTS_QUERY,
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
            cached = _read_cached_data(cache_path, cache_key)
            if cached is not None:
                return cached
            data = _load_product_data(result, product, store)
            _write_cached_data(cache_path, cache_key, data)
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
    def _filter(
        frame: pd.DataFrame,
        filters: AnalysisFilters,
        semantics: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        codes = [filters.problem_code] if filters.problem_code else []
        if codes and semantics is not None and "标签编码路径" in semantics:
            matching = (
                semantics["标签编码路径"]
                .fillna("")
                .map(lambda value: filters.problem_code in str(value).split(" → "))
            )
            codes = sorted(set(semantics.loc[matching, "标签编码"])) or codes
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
            problem_codes=codes,
            claim_relations=(
                [filters.claim_relation] if filters.claim_relation else ()
            ),
        )
