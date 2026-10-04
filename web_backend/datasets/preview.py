from __future__ import annotations

from collections.abc import Callable, Hashable
from pathlib import Path
from typing import Any

import pandas as pd

from return_semantics.data import read_return_file
from web_backend.common import json_value
from web_backend.database import Database

PREVIEW_VERSION_QUERY = """
SELECT d.kind, d.current_version, v.version AS selected_version,
       v.file_path, v.sha256, v.row_count, v.quality_json
FROM datasets d
JOIN dataset_versions v
  ON v.dataset_id = d.id
 AND v.version = COALESCE(?, d.current_version)
WHERE d.id = ? AND d.archived_at IS NULL
"""


def _preview_records(
    frame: pd.DataFrame, offset: int, limit: int
) -> list[dict[Hashable, Any]]:
    selected = frame.iloc[offset : offset + limit].copy()
    records = selected.astype(str).to_dict(orient="records")
    for row_index, record in zip(selected.index, records, strict=True):
        record["_row_index"] = int(row_index)
    return records


def _unfiltered_return_preview(
    row: Any, offset: int, limit: int, query: str
) -> dict[str, Any]:
    frame = read_return_file(
        Path(str(row["file_path"])),
        nrows=offset + limit,
    ).fillna("")
    records = _preview_records(frame, offset, limit)
    quality = json_value(row["quality_json"], {}) or {}
    return {
        "records": records,
        "offset": offset,
        "limit": limit,
        "total": int(row["row_count"]),
        "source_total": int(row["row_count"]),
        "query": query,
        "version": int(row["selected_version"]),
        "facets": {
            "stores": quality.get("stores", []),
            "categories": [],
        },
    }


def _preview_stores(frame: pd.DataFrame) -> list[str]:
    return (
        sorted(
            value
            for value in frame["店铺/站点"].astype(str).str.strip().unique().tolist()
            if value
        )
        if "店铺/站点" in frame.columns
        else []
    )


def _preview_categories(frame: pd.DataFrame) -> tuple[pd.Series, list[str]]:
    if {"品类A", "品类B"}.issubset(frame.columns):
        category_a = frame["品类A"].astype(str).str.strip()
        category_b = frame["品类B"].astype(str).str.strip()
        category_labels = category_a.where(
            category_b.eq(""),
            category_a + " > " + category_b,
        )
        category_labels = category_labels.where(category_a.ne(""), category_b)
        categories = sorted(
            value for value in category_labels.unique().tolist() if value
        )
    else:
        category_labels = pd.Series("", index=frame.index, dtype=str)
        categories = []
    return category_labels, categories


def _filter_preview(
    frame: pd.DataFrame,
    category_labels: pd.Series,
    query: str,
    store: str,
    category: str,
) -> pd.DataFrame:
    clean_store = store.strip()
    if clean_store and "店铺/站点" in frame.columns:
        frame = frame.loc[frame["店铺/站点"].astype(str).str.strip().eq(clean_store)]
        category_labels = category_labels.loc[frame.index]
    clean_category = category.strip()
    if clean_category:
        frame = frame.loc[category_labels.eq(clean_category)]
    clean_query = query.strip().lower()
    if clean_query:
        searchable = frame.astype(str).apply(
            lambda column: column.str.lower().str.contains(
                clean_query,
                regex=False,
            )
        )
        frame = frame.loc[searchable.any(axis=1)]
    return frame


class _DatasetPreview:
    database: Database
    _ensure_product_preview: Callable[..., Path]

    def preview_rows(
        self,
        dataset_id: str,
        offset: int = 0,
        limit: int = 50,
        query: str = "",
        store: str = "",
        category: str = "",
        version: int | None = None,
    ) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                PREVIEW_VERSION_QUERY,
                (version, dataset_id),
            ).fetchone()
        if row is None:
            raise ValueError("数据集或数据版本不存在")
        if row["kind"] == "products":
            preview_path = self._ensure_product_preview(
                Path(str(row["file_path"])),
                str(row["sha256"]),
            )
            frame = pd.read_csv(preview_path, dtype=str).fillna("")
        else:
            if not query.strip() and not store.strip() and not category.strip():
                return _unfiltered_return_preview(row, offset, limit, query)
            frame = read_return_file(Path(str(row["file_path"]))).fillna("")
        source_total = len(frame)
        stores = _preview_stores(frame)
        category_labels, categories = _preview_categories(frame)
        frame = _filter_preview(frame, category_labels, query, store, category)
        records = _preview_records(frame, offset, limit)
        return {
            "records": records,
            "offset": offset,
            "limit": limit,
            "total": len(frame),
            "source_total": source_total,
            "query": query,
            "version": int(row["selected_version"]),
            "facets": {"stores": stores, "categories": categories},
        }
