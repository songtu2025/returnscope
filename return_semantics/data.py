from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from return_semantics.analysis_context import (
    RETURNS_CONTEXT,
    USER_FEEDBACK_CONTEXT,
    AnalysisContext,
)
from return_semantics.data_files import RETURN_COLUMNS as RETURN_COLUMNS
from return_semantics.data_files import RETURN_STORE_COLUMN as RETURN_STORE_COLUMN
from return_semantics.data_files import SOURCE_ORIGIN_COLUMN as SOURCE_ORIGIN_COLUMN
from return_semantics.data_files import _looks_like_gb18030 as _looks_like_gb18030
from return_semantics.data_files import _return_column_score as _return_column_score
from return_semantics.data_files import _select_columns as _select_columns
from return_semantics.data_files import read_return_csv as read_return_csv
from return_semantics.data_files import read_return_xlsx as read_return_xlsx
from return_semantics.dataset_grouping import (
    _assign_classification_keys,
    _dataset_scopes,
    _unique_comments,
)
from return_semantics.product_matching import (
    PRODUCT_CATEGORY_COLUMNS as PRODUCT_CATEGORY_COLUMNS,
)
from return_semantics.product_matching import PRODUCT_COLUMNS as PRODUCT_COLUMNS
from return_semantics.product_matching import (
    PRODUCT_DETAIL_COLUMNS as PRODUCT_DETAIL_COLUMNS,
)
from return_semantics.product_matching import _primary_store, _product_scope_lookup
from return_semantics.product_matching import (
    _product_category_lookup as _product_category_lookup,
)
from return_semantics.product_matching import (
    _read_product_dimensions as _read_product_dimensions,
)
from return_semantics.product_matching import resolve_sku_aliases as resolve_sku_aliases


@dataclass(frozen=True)
class ReturnDataset:
    records: pd.DataFrame
    unique_comments: pd.DataFrame
    mskus: frozenset[str]
    scopes: tuple[dict[str, object], ...] = ()
    primary_store: str = ""
    scope_mode: str = "manual"


def normalize_comment(value: Any) -> str:
    if pd.isna(value):
        return ""
    text = html.unescape(str(value))
    text = text.replace("\u00a0", " ")
    return re.sub(r"\s+", " ", text).strip()


def read_return_file(
    path: Path,
    usecols: list[str] | None = None,
    nrows: int | None = None,
) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return read_return_csv(path, usecols=usecols, nrows=nrows)
    if suffix == ".xlsx":
        return read_return_xlsx(path, usecols=usecols, nrows=nrows)
    raise ValueError("用户反馈数据仅支持 .csv、.xlsx 文件")


def load_mskus(
    product_path: Path,
    store: str,
    listing: str | None = None,
) -> frozenset[str]:
    products = load_product_dimensions(product_path, store, listing)
    selected = products["MSKU"]
    mskus = frozenset(value for value in selected if value)
    if not mskus:
        scope = f"{store} + {listing}" if listing is not None else store
        raise ValueError(f"没有找到 {scope} 的 MSKU")
    return mskus


def load_product_dimensions(
    product_path: Path,
    store: str,
    listing: str | None = None,
) -> pd.DataFrame:
    products = _read_product_dimensions(product_path)
    listing_mask = products["Listing"].eq(listing) if listing is not None else True
    return products.loc[products["店铺/站点"].eq(store) & listing_mask].reset_index(
        drop=True
    )


def _prepare_return_records(return_path: Path) -> pd.DataFrame:
    records = read_return_file(return_path)
    missing = [column for column in RETURN_COLUMNS if column not in records.columns]
    if missing:
        raise ValueError(f"用户反馈数据缺少字段: {', '.join(missing)}")
    selected_columns = RETURN_COLUMNS + [
        column
        for column in (RETURN_STORE_COLUMN, SOURCE_ORIGIN_COLUMN)
        if column in records.columns
    ]
    records = records[selected_columns].copy()
    records.insert(0, "source_row", records.index + 2)
    records[SOURCE_ORIGIN_COLUMN] = (
        records[SOURCE_ORIGIN_COLUMN].fillna("").astype(str).str.strip()
        if SOURCE_ORIGIN_COLUMN in records.columns
        else ""
    )
    records["sku"] = records["sku"].fillna("").str.strip()
    records["sku_raw"] = records["sku"]
    records["source_sku"] = records["sku"]
    records["sku"] = records["sku"].map(html.unescape).str.strip()
    records["asin"] = records["asin"].fillna("").str.strip()
    records["input_store"] = (
        records[RETURN_STORE_COLUMN].fillna("").astype(str).str.strip()
        if RETURN_STORE_COLUMN in records.columns
        else ""
    )
    return records


def _finalize_return_dataset(
    records: pd.DataFrame,
    mskus: frozenset[str],
    *,
    primary_store: str,
    scope_mode: str,
    analysis_context: AnalysisContext,
) -> ReturnDataset:
    for column in ("store", "listing", "category_a", "category_b"):
        records[column] = records[column].fillna("").astype(str).str.strip()

    records["comment_raw"] = records["customer-comments"].fillna("")
    records["comment_normalized"] = records["customer-comments"].map(normalize_comment)
    records["comment_dedupe"] = records["comment_normalized"].str.lower()
    records["has_text_evidence"] = records["comment_normalized"].ne("")
    records["reason"] = records["reason"].fillna("").str.strip()
    records["feedback_title"] = (
        records["reason"] if analysis_context == USER_FEEDBACK_CONTEXT else ""
    )
    _assign_classification_keys(records, scope_mode, analysis_context)
    unique_comments = _unique_comments(records)
    scopes = _dataset_scopes(records)
    return ReturnDataset(
        records=records.reset_index(drop=True),
        unique_comments=unique_comments,
        mskus=mskus,
        scopes=scopes,
        primary_store=primary_store,
        scope_mode=scope_mode,
    )


def load_return_dataset(
    return_path: Path,
    product_path: Path,
    store: str,
    listing: str | None = None,
    analysis_context: AnalysisContext = RETURNS_CONTEXT,
) -> ReturnDataset:
    products = load_product_dimensions(product_path, store=store, listing=listing)
    mskus = frozenset(value for value in products["MSKU"] if value)
    if not mskus:
        scope = f"{store} + {listing}" if listing is not None else store
        raise ValueError(f"没有找到 {scope} 的 MSKU")
    records = _prepare_return_records(return_path)
    if records["input_store"].ne("").any():
        records = records.loc[records["input_store"].eq(store)].copy()
        records["store"] = records["input_store"]
    else:
        records["store"] = store
    valid_pairs = frozenset(zip(products["店铺/站点"], products["MSKU"], strict=True))
    records = resolve_sku_aliases(records, valid_pairs)
    if listing is not None:
        records = records.loc[records["sku"].isin(mskus)].copy()
    lookup_rows = _product_scope_lookup(
        products, "MSKU", "同一店铺内 MSKU 对应多个商品信息"
    )
    records = records.merge(
        lookup_rows,
        left_on="sku",
        right_on="matched_msku",
        how="left",
        validate="many_to_one",
    )
    records["product_match_status"] = (
        records["matched_msku"].notna().map({True: "matched", False: "unmatched"})
    )
    return _finalize_return_dataset(
        records,
        mskus,
        primary_store=store,
        scope_mode="manual",
        analysis_context=analysis_context,
    )


def load_return_dataset_auto(
    return_path: Path,
    product_path: Path,
    analysis_context: AnalysisContext = RETURNS_CONTEXT,
) -> ReturnDataset:
    products = _read_product_dimensions(product_path)
    products = products.loc[products["MSKU"].ne("")].copy()
    if products.empty:
        raise ValueError("商品目录中没有可用于自动匹配的 MSKU")
    records = _prepare_return_records(return_path)

    primary_store = _primary_store(records)

    records["store"] = records["input_store"]
    valid_pairs = frozenset(zip(products["店铺/站点"], products["MSKU"], strict=True))
    records = resolve_sku_aliases(records, valid_pairs)
    lookup_rows = _product_scope_lookup(
        products, ["店铺/站点", "MSKU"], "同一店铺内 MSKU 对应多个商品范围或品类"
    )
    records = records.merge(
        lookup_rows,
        left_on=["store", "sku"],
        right_on=["store", "matched_msku"],
        how="left",
        validate="many_to_one",
    )
    records["product_match_status"] = (
        records["matched_msku"].notna().map({True: "matched", False: "unmatched"})
    )
    return _finalize_return_dataset(
        records,
        frozenset(products["MSKU"]),
        primary_store=primary_store,
        scope_mode="auto",
        analysis_context=analysis_context,
    )


_looks_like_gb18030.__module__ = __name__
_return_column_score.__module__ = __name__
_select_columns.__module__ = __name__
read_return_csv.__module__ = __name__
read_return_xlsx.__module__ = __name__

_product_category_lookup.__module__ = __name__
_read_product_dimensions.__module__ = __name__
resolve_sku_aliases.__module__ = __name__
