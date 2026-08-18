from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

DETAIL_SHEET = "分类明细"
SEMANTIC_SHEET = "语义单元"
UNKNOWN_SHEET = "未知语义"
PRODUCT_SHEET = "产品信息汇总表"

PRODUCT_SOURCE_COLUMNS = [
    "MSKU",
    "店铺/站点",
    "Listing",
    "产品名称",
    "SKU",
    "品类A",
    "品类B",
]
PRODUCT_REQUIRED_COLUMNS = ["MSKU", "店铺/站点", "Listing", "产品名称"]
PRODUCT_DIMENSION_COLUMNS = [
    "sku",
    "店铺/站点",
    "Listing",
    "产品名称",
    "标准SKU",
    "款式",
    "颜色",
    "尺码",
    "品类A",
    "品类B",
]

DETAIL_COLUMNS = {
    "分类键",
    "return-date",
    "sku",
    "asin",
    "Amazon原因",
    "标准化评论",
    "问题标签",
    "主因标签",
    "部位",
    "Listing承诺关系",
    "处理状态",
    "复核原因",
}
SEMANTIC_COLUMNS = {
    "分类键",
    "标签编码",
    "标签名称",
    "一级分类",
}
UNKNOWN_COLUMNS = {
    "分类键",
    "重复记录数",
    "Amazon原因",
    "标准化评论",
    "标准化观点",
    "证据原文",
    "未映射原因",
}

DETAIL_TEXT_COLUMNS = [
    "分类键",
    "sku",
    "asin",
    "Amazon原因",
    "评论原文",
    "标准化评论",
    "问题标签",
    "正面标签",
    "主因标签",
    "部位",
    "证据原文",
    "Listing承诺关系",
    "Listing承诺编号",
    "处理状态",
    "复核原因",
]


@dataclass(frozen=True)
class AnalysisData:
    details: pd.DataFrame
    semantics: pd.DataFrame
    unknowns: pd.DataFrame
    label_catalog: pd.DataFrame
    products: pd.DataFrame


def _validate_columns(
    frame: pd.DataFrame,
    required: set[str],
    sheet_name: str,
) -> None:
    missing = required.difference(frame.columns)
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise ValueError(f"{sheet_name} 缺少字段: {missing_text}")


def _clean_text_columns(frame: pd.DataFrame, columns: list[str]) -> None:
    for column in columns:
        if column in frame.columns:
            frame[column] = frame[column].fillna("").astype(str).str.strip()


def _first_text(values: pd.Series) -> str:
    cleaned = values.fillna("").astype(str).str.strip()
    return next((value for value in cleaned if value), "")


def _parse_standard_sku(value: object) -> tuple[str, str, str]:
    text = "" if pd.isna(value) else str(value).strip()
    style_match = re.search(r"^[^-]+-([^\s]+)", text)
    size_match = re.search(r"\s(\d+(?:\.\d+)?(?:-\d+(?:\.\d+)?)?)$", text)
    style = style_match.group(1) if style_match else ""
    size = size_match.group(1) if size_match else ""
    color_start = style_match.end() if style_match else 0
    color_end = size_match.start() if size_match else len(text)
    color = text[color_start:color_end].strip(" -")
    return style, color, size


def load_product_dimensions(
    workbook_path: Path,
    skus: Iterable[str] = (),
    store: str | None = None,
) -> pd.DataFrame:
    if not workbook_path.exists():
        raise FileNotFoundError(f"产品信息不存在: {workbook_path}")

    products = pd.read_excel(
        workbook_path,
        sheet_name=PRODUCT_SHEET,
        dtype=str,
    ).fillna("")
    _validate_columns(products, set(PRODUCT_REQUIRED_COLUMNS), PRODUCT_SHEET)
    for column in PRODUCT_SOURCE_COLUMNS:
        if column not in products:
            products[column] = ""
    products = products[PRODUCT_SOURCE_COLUMNS]
    _clean_text_columns(products, PRODUCT_SOURCE_COLUMNS)
    products = products.loc[products["MSKU"].ne("")].copy()
    if store is not None:
        products = products.loc[products["店铺/站点"].eq(store)].copy()
    selected_skus = set(skus)
    if selected_skus:
        products = products.loc[products["MSKU"].isin(selected_skus)]

    dimensions = products.groupby("MSKU", as_index=False, sort=False).agg(
        {
            "店铺/站点": _first_text,
            "Listing": _first_text,
            "产品名称": _first_text,
            "SKU": _first_text,
            "品类A": _first_text,
            "品类B": _first_text,
        }
    )
    dimensions = dimensions.rename(columns={"MSKU": "sku", "SKU": "标准SKU"})
    parsed = dimensions["标准SKU"].map(_parse_standard_sku)
    dimensions[["款式", "颜色", "尺码"]] = pd.DataFrame(
        parsed.tolist(),
        index=dimensions.index,
    )
    return dimensions[PRODUCT_DIMENSION_COLUMNS]


def load_analysis_data(
    workbook_path: Path,
    product_path: Path | None = None,
    store: str | None = None,
) -> AnalysisData:
    if not workbook_path.exists():
        raise FileNotFoundError(f"分类结果不存在: {workbook_path}")

    sheets = pd.read_excel(
        workbook_path,
        sheet_name=[DETAIL_SHEET, SEMANTIC_SHEET, UNKNOWN_SHEET],
    )
    details = sheets[DETAIL_SHEET].copy()
    semantics = sheets[SEMANTIC_SHEET].copy()
    unknowns = sheets[UNKNOWN_SHEET].copy()

    if semantics.empty:
        semantics = semantics.reindex(columns=sorted(SEMANTIC_COLUMNS))
    if unknowns.empty:
        unknowns = unknowns.reindex(columns=sorted(UNKNOWN_COLUMNS))

    _validate_columns(details, DETAIL_COLUMNS, DETAIL_SHEET)
    _validate_columns(semantics, SEMANTIC_COLUMNS, SEMANTIC_SHEET)
    _validate_columns(unknowns, UNKNOWN_COLUMNS, UNKNOWN_SHEET)

    _clean_text_columns(details, DETAIL_TEXT_COLUMNS)
    _clean_text_columns(
        semantics,
        ["分类键", "标签编码", "标签名称", "一级分类"],
    )
    _clean_text_columns(
        unknowns,
        [
            "分类键",
            "Amazon原因",
            "标准化评论",
            "标准化观点",
            "证据原文",
            "未映射原因",
        ],
    )

    details["return_date"] = pd.to_datetime(
        details["return-date"],
        errors="coerce",
        utc=True,
    )
    details["has_text"] = details["标准化评论"].ne("")

    if product_path is None:
        products = pd.DataFrame(columns=PRODUCT_DIMENSION_COLUMNS)
        for column in PRODUCT_DIMENSION_COLUMNS[1:]:
            if column not in details.columns:
                details[column] = ""
    else:
        products = load_product_dimensions(
            product_path,
            details["sku"].unique(),
            store=store,
        )
    if not products.empty:
        details = details.merge(
            products,
            on="sku",
            how="left",
            validate="many_to_one",
        )
        _clean_text_columns(details, PRODUCT_DIMENSION_COLUMNS[1:])

    label_catalog = (
        semantics.loc[
            semantics["标签编码"].ne(""),
            ["标签编码", "标签名称", "一级分类"],
        ]
        .drop_duplicates(subset=["标签编码"])
        .sort_values(["一级分类", "标签名称"])
        .reset_index(drop=True)
    )

    return AnalysisData(
        details=details,
        semantics=semantics,
        unknowns=unknowns,
        label_catalog=label_catalog,
        products=products,
    )
