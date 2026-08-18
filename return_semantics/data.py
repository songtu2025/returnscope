from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

RETURN_COLUMNS = [
    "return-date",
    "order-id",
    "sku",
    "asin",
    "fnsku",
    "product-name",
    "quantity",
    "reason",
    "customer-comments",
]
PRODUCT_COLUMNS = ["MSKU", "店铺/站点", "Listing"]
PRODUCT_CATEGORY_COLUMNS = ["品类A", "品类B"]
PRODUCT_DETAIL_COLUMNS = ["产品名称", "SKU"]
RETURN_STORE_COLUMN = "店铺/站点"


@dataclass(frozen=True)
class ReturnDataset:
    records: pd.DataFrame
    unique_comments: pd.DataFrame
    mskus: frozenset[str]
    scopes: tuple[dict[str, object], ...] = ()
    primary_store: str = ""
    scope_mode: str = "manual"


def normalize_comment(value: object) -> str:
    if pd.isna(value):
        return ""
    text = html.unescape(str(value))
    text = text.replace("\u00a0", " ")
    return re.sub(r"\s+", " ", text).strip()


def _looks_like_gb18030(frame: pd.DataFrame) -> bool:
    sample = "".join(
        frame.head(1000).fillna("").astype(str).to_numpy().ravel().tolist()
    )
    compact = re.sub(r"\s+", "", sample)
    cjk_count = len(re.findall(r"[\u4e00-\u9fff]", compact))
    mixed_count = len(
        re.findall(
            r"(?:[A-Za-z][\u4e00-\u9fff]|[\u4e00-\u9fff][A-Za-z])",
            compact,
        )
    )
    return (
        cjk_count >= 4
        and cjk_count / max(len(compact), 1) >= 0.02
        and mixed_count <= max(1, cjk_count // 4)
    )


def read_return_csv(
    path: Path,
    usecols: list[str] | None = None,
) -> pd.DataFrame:
    try:
        return pd.read_csv(
            path,
            encoding="utf-8-sig",
            dtype=str,
            usecols=usecols,
        )
    except UnicodeDecodeError:
        pass

    decoded: dict[str, pd.DataFrame] = {}
    last_error: UnicodeDecodeError | None = None
    for encoding in ("cp1252", "gb18030"):
        try:
            decoded[encoding] = pd.read_csv(
                path,
                encoding=encoding,
                dtype=str,
                usecols=usecols,
            )
        except UnicodeDecodeError as exc:
            last_error = exc
    if "gb18030" in decoded and (
        "cp1252" not in decoded or _looks_like_gb18030(decoded["gb18030"])
    ):
        return decoded["gb18030"]
    if "cp1252" in decoded:
        return decoded["cp1252"]
    assert last_error is not None
    raise last_error


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


def _read_product_dimensions(product_path: Path) -> pd.DataFrame:
    products = pd.read_excel(
        product_path,
        sheet_name="产品信息汇总表",
        dtype=str,
    ).fillna("")
    missing = [column for column in PRODUCT_COLUMNS if column not in products.columns]
    if missing:
        raise ValueError(f"商品维度缺少字段: {', '.join(missing)}")
    for column in PRODUCT_CATEGORY_COLUMNS:
        if column not in products.columns:
            products[column] = ""
    for column in PRODUCT_DETAIL_COLUMNS:
        if column not in products.columns:
            products[column] = ""
    selected_columns = (
        PRODUCT_COLUMNS + PRODUCT_DETAIL_COLUMNS + PRODUCT_CATEGORY_COLUMNS
    )
    products = products[selected_columns].copy()
    for column in selected_columns:
        products[column] = products[column].astype(str).str.strip()
    return products


def _product_category_lookup(products: pd.DataFrame) -> pd.DataFrame:
    category_rows = products.loc[
        products["MSKU"].ne(""),
        ["MSKU", "品类A", "品类B"],
    ].drop_duplicates()
    conflicts = category_rows.groupby("MSKU")[["品类A", "品类B"]].nunique()
    conflicts = conflicts.loc[conflicts.max(axis=1).gt(1)]
    if not conflicts.empty:
        raise ValueError(f"MSKU 对应多个品类: {conflicts.index.tolist()[:10]}")
    return category_rows.drop_duplicates(subset=["MSKU"]).set_index("MSKU")


def resolve_sku_aliases(
    records: pd.DataFrame,
    valid_pairs: frozenset[tuple[str, str]],
) -> pd.DataFrame:
    known_product = pd.Series(
        [
            (store, sku) in valid_pairs
            for store, sku in zip(
                records["store"],
                records["sku"],
                strict=True,
            )
        ],
        index=records.index,
    )
    known_pairs = records.loc[
        known_product & records["asin"].ne(""),
        ["store", "asin", "sku"],
    ].drop_duplicates()
    sku_counts = known_pairs.groupby(["store", "asin"])["sku"].nunique()
    ambiguous_keys = set(sku_counts.loc[sku_counts.gt(1)].index.tolist())
    if ambiguous_keys:
        known_pairs = known_pairs.loc[
            [
                (store, asin) not in ambiguous_keys
                for store, asin in zip(
                    known_pairs["store"],
                    known_pairs["asin"],
                    strict=True,
                )
            ]
        ]

    alias_lookup = known_pairs.set_index(["store", "asin"])["sku"].to_dict()
    resolved = records.copy()
    unresolved = [
        (store, sku) not in valid_pairs
        for store, sku in zip(
            resolved["store"],
            resolved["sku"],
            strict=True,
        )
    ]
    unresolved_rows = resolved.loc[unresolved, ["store", "asin", "sku"]]
    resolved.loc[unresolved, "sku"] = [
        alias_lookup.get((store, asin), sku)
        for store, asin, sku in unresolved_rows.itertuples(index=False, name=None)
    ]
    return resolved


def _prepare_return_records(return_path: Path) -> pd.DataFrame:
    records = read_return_csv(return_path)
    missing = [column for column in RETURN_COLUMNS if column not in records.columns]
    if missing:
        raise ValueError(f"退货数据缺少字段: {', '.join(missing)}")
    selected_columns = RETURN_COLUMNS + (
        [RETURN_STORE_COLUMN] if RETURN_STORE_COLUMN in records.columns else []
    )
    records = records[selected_columns].copy()
    records.insert(0, "source_row", records.index + 2)
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
) -> ReturnDataset:
    for column in ("store", "listing", "category_a", "category_b"):
        records[column] = records[column].fillna("").astype(str).str.strip()

    records["comment_raw"] = records["customer-comments"].fillna("")
    records["comment_normalized"] = records["customer-comments"].map(normalize_comment)
    records["comment_dedupe"] = records["comment_normalized"].str.lower()
    records["has_text_evidence"] = records["comment_normalized"].ne("")
    records["reason"] = records["reason"].fillna("").str.strip()
    records["classification_key"] = ""

    has_text = records["has_text_evidence"]
    category_scope = records["category_a"] + "\x1e" + records["category_b"]
    missing_category = records["category_a"].eq("") & records["category_b"].eq("")
    category_scope = category_scope.mask(
        missing_category,
        "SKU=" + records["sku"],
    )
    classification_scope = category_scope
    if scope_mode == "auto":
        classification_scope = (
            records["store"] + "\x1d" + records["listing"] + "\x1d" + category_scope
        )
    records.loc[has_text, "classification_key"] = (
        classification_scope.loc[has_text]
        + "\x1f"
        + records.loc[has_text, "reason"]
        + "\x1f"
        + records.loc[has_text, "comment_dedupe"]
    )

    unique_comments = (
        records.loc[
            has_text,
            [
                "classification_key",
                "reason",
                "comment_normalized",
                "category_a",
                "category_b",
                "store",
                "listing",
                "product_match_status",
            ],
        ]
        .drop_duplicates(subset=["classification_key"])
        .reset_index(drop=True)
    )
    counts = records.loc[has_text, "classification_key"].value_counts()
    unique_comments["record_count"] = unique_comments["classification_key"].map(counts)

    scoped = records.loc[has_text & records["store"].ne("")]
    scopes = tuple(
        {
            "store": str(store),
            "listing": str(listing),
            "record_count": len(rows),
            "unique_comments": int(rows["classification_key"].nunique()),
        }
        for (store, listing), rows in scoped.groupby(
            ["store", "listing"],
            sort=True,
            dropna=False,
        )
    )
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
    lookup_rows = products[
        ["MSKU", "Listing", "产品名称", "SKU", "品类A", "品类B"]
    ].drop_duplicates()
    conflicts = lookup_rows.groupby("MSKU")[
        ["Listing", "产品名称", "SKU", "品类A", "品类B"]
    ].nunique()
    if not conflicts.loc[conflicts.max(axis=1).gt(1)].empty:
        raise ValueError("同一店铺内 MSKU 对应多个商品信息")
    lookup_rows = lookup_rows.drop_duplicates("MSKU").rename(
        columns={
            "MSKU": "matched_msku",
            "Listing": "listing",
            "产品名称": "product_name",
            "SKU": "product_sku",
            "品类A": "category_a",
            "品类B": "category_b",
        }
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
    )


def load_return_dataset_auto(
    return_path: Path,
    product_path: Path,
) -> ReturnDataset:
    products = _read_product_dimensions(product_path)
    products = products.loc[products["MSKU"].ne("")].copy()
    if products.empty:
        raise ValueError("商品目录中没有可用于自动匹配的 MSKU")
    records = _prepare_return_records(return_path)

    store_scores: dict[str, int] = {}
    for explicit_store, count in (
        records.loc[records["input_store"].ne(""), "input_store"].value_counts().items()
    ):
        store_scores[str(explicit_store)] = int(count)
    ordered_scores = sorted(store_scores.items(), key=lambda item: (-item[1], item[0]))
    primary_store = ""
    if ordered_scores and (
        len(ordered_scores) == 1 or ordered_scores[0][1] > ordered_scores[1][1]
    ):
        primary_store = ordered_scores[0][0]

    records["store"] = records["input_store"]
    valid_pairs = frozenset(zip(products["店铺/站点"], products["MSKU"], strict=True))
    records = resolve_sku_aliases(records, valid_pairs)
    lookup_rows = products[
        [
            "店铺/站点",
            "MSKU",
            "Listing",
            "产品名称",
            "SKU",
            "品类A",
            "品类B",
        ]
    ].drop_duplicates()
    conflicts = lookup_rows.groupby(["店铺/站点", "MSKU"])[
        ["Listing", "产品名称", "SKU", "品类A", "品类B"]
    ].nunique()
    if not conflicts.loc[conflicts.max(axis=1).gt(1)].empty:
        raise ValueError("同一店铺内 MSKU 对应多个商品范围或品类")
    lookup_rows = lookup_rows.drop_duplicates(["店铺/站点", "MSKU"]).rename(
        columns={
            "店铺/站点": "store",
            "MSKU": "matched_msku",
            "Listing": "listing",
            "产品名称": "product_name",
            "SKU": "product_sku",
            "品类A": "category_a",
            "品类B": "category_b",
        }
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
    )
