from __future__ import annotations

import hashlib
import json
import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from return_semantics.data import load_return_dataset_auto
from web_backend.database import Database

ISSUE_REASONS = {
    "missing_store": "缺少店铺/站点",
    "missing_source_sku": "缺少退货 SKU",
    "unmatched_product": "店铺/站点 + 退货 SKU 未匹配商品",
    "missing_category": "已匹配商品缺少品类",
    "missing_product_name": "已匹配商品缺少产品名称",
}


@dataclass(frozen=True)
class _QualityCacheEntry:
    returns: dict[str, Any]
    products: dict[str, Any]
    records: pd.DataFrame
    counts: dict[str, int]
    issue_frame: pd.DataFrame


class DataQualityService:
    def __init__(self, database: Database) -> None:
        self.database = database
        self._cache: OrderedDict[
            tuple[str, str, str, str],
            _QualityCacheEntry,
        ] = OrderedDict()
        self._cache_lock = threading.RLock()

    def preflight(
        self,
        returns_version_id: str,
        products_version_id: str,
    ) -> dict[str, Any]:
        entry = self._pair_entry(
            returns_version_id,
            products_version_id,
        )
        payload = {
            "returns_version": self._public_version(entry.returns),
            "products_version": self._public_version(entry.products),
            "match_key": {
                "returns": ["店铺/站点", "sku"],
                "products": ["店铺/站点", "MSKU"],
                "normalized": ["store_site", "source_sku"],
            },
            "counts": dict(entry.counts),
        }
        payload["quality_hash"] = hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        return payload

    def issues(
        self,
        returns_version_id: str,
        products_version_id: str,
        *,
        issue_type: str | None = None,
        q: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        if issue_type and issue_type not in ISSUE_REASONS:
            raise ValueError("issue_type 不合法")
        entry = self._pair_entry(returns_version_id, products_version_id)
        issue_frame = entry.issue_frame.copy(deep=True)
        if issue_type:
            issue_frame = issue_frame.loc[issue_frame["issue_type"].eq(issue_type)]
        clean_query = (q or "").strip().casefold()
        if clean_query and not issue_frame.empty:
            searchable = issue_frame[
                [
                    "store_site",
                    "source_sku",
                    "listing",
                    "product_name",
                    "category_a",
                    "category_b",
                    "reason",
                ]
            ].apply(
                lambda column: column.astype(str).str.casefold().str.contains(
                    clean_query,
                    regex=False,
                )
            )
            issue_frame = issue_frame.loc[searchable.any(axis=1)]
        issue_frame = issue_frame.sort_values(
            ["issue_type", "record_count", "store_site", "source_sku"],
            ascending=[True, False, True, True],
            kind="stable",
        )
        total = len(issue_frame)
        offset = (page - 1) * page_size
        items = issue_frame.iloc[offset : offset + page_size].to_dict(orient="records")
        for item in items:
            item["record_count"] = int(item["record_count"])
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def _pair_entry(
        self,
        returns_version_id: str,
        products_version_id: str,
    ) -> _QualityCacheEntry:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT v.id, v.dataset_id, v.version, v.file_path, v.sha256,
                       d.name AS dataset_name, d.kind
                FROM dataset_versions v
                JOIN datasets d ON d.id = v.dataset_id
                WHERE v.id IN (?, ?)
                """,
                (returns_version_id, products_version_id),
            ).fetchall()
        by_id = {str(row["id"]): dict(row) for row in rows}
        returns = by_id.get(returns_version_id)
        products = by_id.get(products_version_id)
        if returns is None or returns["kind"] != "returns":
            raise ValueError("退货数据版本不存在或类型不正确")
        if products is None or products["kind"] != "products":
            raise ValueError("商品数据版本不存在或类型不正确")
        cache_key = (
            str(returns["id"]),
            str(returns["sha256"]),
            str(products["id"]),
            str(products["sha256"]),
        )
        with self._cache_lock:
            cached = self._cache.get(cache_key)
            if cached is not None:
                self._cache.move_to_end(cache_key)
                return cached
            dataset = load_return_dataset_auto(
                Path(str(returns["file_path"])),
                Path(str(products["file_path"])),
            )
            records = dataset.records.copy(deep=True)
            entry = _QualityCacheEntry(
                returns=dict(returns),
                products=dict(products),
                records=records,
                counts=self._counts(records),
                issue_frame=self._issue_frame(records),
            )
            self._cache[cache_key] = entry
            self._cache.move_to_end(cache_key)
            while len(self._cache) > 2:
                self._cache.popitem(last=False)
            return entry

    @staticmethod
    def _counts(records: pd.DataFrame) -> dict[str, int]:
        store = DataQualityService._text(records, "store")
        source_sku = DataQualityService._text(records, "source_sku")
        product_name = DataQualityService._text(records, "product_name")
        category_a = DataQualityService._text(records, "category_a")
        category_b = DataQualityService._text(records, "category_b")
        matched = records["product_match_status"].eq("matched")
        key_ready = store.ne("") & source_sku.ne("")
        key_count = int(
            records.loc[key_ready, ["store", "source_sku"]]
            .fillna("")
            .drop_duplicates()
            .shape[0]
        )
        return {
            "total_records": int(len(records)),
            "match_key_ready_records": int(key_ready.sum()),
            "match_key_ready_keys": key_count,
            "matched_records": int(matched.sum()),
            "unmatched_records": int((~matched).sum()),
            "missing_store_records": int(store.eq("").sum()),
            "missing_source_sku_records": int(source_sku.eq("").sum()),
            "missing_category_records": int(
                (matched & category_a.eq("") & category_b.eq("")).sum()
            ),
            "missing_product_name_records": int(
                (matched & product_name.eq("")).sum()
            ),
        }

    @staticmethod
    def _issue_frame(records: pd.DataFrame) -> pd.DataFrame:
        normalized = pd.DataFrame(index=records.index)
        normalized["store_site"] = DataQualityService._text(records, "store")
        for source, target in (
            ("source_sku", "source_sku"),
            ("listing", "listing"),
            ("product_name", "product_name"),
            ("category_a", "category_a"),
            ("category_b", "category_b"),
        ):
            normalized[target] = DataQualityService._text(records, source)
        matched = records["product_match_status"].eq("matched")
        masks = {
            "missing_store": normalized["store_site"].eq(""),
            "missing_source_sku": normalized["source_sku"].eq(""),
            "unmatched_product": ~matched,
            "missing_category": (
                matched
                & normalized["category_a"].eq("")
                & normalized["category_b"].eq("")
            ),
            "missing_product_name": matched & normalized["product_name"].eq(""),
        }
        frames = []
        for name, mask in masks.items():
            selected = normalized.loc[mask].copy()
            if selected.empty:
                continue
            selected["issue_type"] = name
            selected["reason"] = ISSUE_REASONS[name]
            frames.append(selected)
        columns = [
            "issue_type",
            "store_site",
            "source_sku",
            "listing",
            "product_name",
            "category_a",
            "category_b",
            "reason",
            "record_count",
        ]
        if not frames:
            return pd.DataFrame(columns=columns)
        combined = pd.concat(frames, ignore_index=True)
        group_columns = columns[:-1]
        return (
            combined.groupby(group_columns, dropna=False, sort=False)
            .size()
            .rename("record_count")
            .reset_index()
        )

    @staticmethod
    def _text(records: pd.DataFrame, column: str) -> pd.Series:
        if column not in records.columns:
            return pd.Series("", index=records.index, dtype=str)
        return records[column].fillna("").astype(str).str.strip()

    @staticmethod
    def _public_version(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": item["id"],
            "dataset_id": item["dataset_id"],
            "name": item["dataset_name"],
            "version": int(item["version"]),
            "sha256": item["sha256"],
        }
