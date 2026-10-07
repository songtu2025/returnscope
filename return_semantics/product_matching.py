from __future__ import annotations

from pathlib import Path

import pandas as pd

PRODUCT_COLUMNS = ["MSKU", "店铺/站点", "Listing"]

PRODUCT_CATEGORY_COLUMNS = ["品类A", "品类B"]

PRODUCT_DETAIL_COLUMNS = ["产品名称", "SKU"]


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


def _product_scope_lookup(
    products: pd.DataFrame,
    group_by: str | list[str],
    conflict_message: str,
) -> pd.DataFrame:
    scope_columns = [group_by] if isinstance(group_by, str) else group_by
    detail_columns = ["Listing", "产品名称", "SKU", "品类A", "品类B"]
    lookup_rows = products[[*scope_columns, *detail_columns]].drop_duplicates()
    conflicts = lookup_rows.groupby(group_by)[detail_columns].nunique()
    if not conflicts.loc[conflicts.max(axis=1).gt(1)].empty:
        raise ValueError(conflict_message)
    columns = {
        "MSKU": "matched_msku",
        "Listing": "listing",
        "产品名称": "product_name",
        "SKU": "product_sku",
        "品类A": "category_a",
        "品类B": "category_b",
    }
    if not isinstance(group_by, str):
        columns = {"店铺/站点": "store", **columns}
    return lookup_rows.drop_duplicates(group_by).rename(columns=columns)


def _primary_store(records: pd.DataFrame) -> str:
    store_scores: dict[str, int] = {}
    for explicit_store, count in (
        records.loc[records["input_store"].ne(""), "input_store"].value_counts().items()
    ):
        store_scores[str(explicit_store)] = int(count)
    ordered_scores = sorted(store_scores.items(), key=lambda item: (-item[1], item[0]))
    if ordered_scores and (
        len(ordered_scores) == 1 or ordered_scores[0][1] > ordered_scores[1][1]
    ):
        return ordered_scores[0][0]
    return ""
