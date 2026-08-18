from pathlib import Path

import pandas as pd

from return_analysis.data import (
    load_analysis_data,
    load_product_dimensions,
)


def test_load_analysis_data_normalizes_fields(
    monkeypatch,
    tmp_path: Path,
) -> None:
    workbook = tmp_path / "result.xlsx"
    workbook.touch()
    sheets = {
        "分类明细": pd.DataFrame(
            [
                {
                    "分类键": "key-1",
                    "return-date": "2026-08-01T00:00:00+00:00",
                    "sku": " SKU-1 ",
                    "asin": "ASIN-1",
                    "Amazon原因": "TOO_SMALL",
                    "标准化评论": "Too small",
                    "问题标签": "FIT_TOO_SMALL:偏小",
                    "主因标签": "FIT_TOO_SMALL:偏小",
                    "部位": "WHOLE_SHOE",
                    "Listing承诺关系": "NONE",
                    "处理状态": "AUTO_APPROVED",
                    "复核原因": "",
                }
            ]
        ),
        "语义单元": pd.DataFrame(
            [
                {
                    "分类键": "key-1",
                    "标签编码": "FIT_TOO_SMALL",
                    "标签名称": "偏小",
                    "一级分类": "尺码与合脚",
                }
            ]
        ),
        "未知语义": pd.DataFrame(
            columns=[
                "分类键",
                "重复记录数",
                "Amazon原因",
                "标准化评论",
                "标准化观点",
                "证据原文",
                "未映射原因",
            ]
        ),
    }

    monkeypatch.setattr(pd, "read_excel", lambda *args, **kwargs: sheets)

    result = load_analysis_data(workbook)

    assert result.details.loc[0, "sku"] == "SKU-1"
    assert bool(result.details.loc[0, "has_text"]) is True
    assert result.details.loc[0, "return_date"].year == 2026
    assert result.label_catalog.loc[0, "标签编码"] == "FIT_TOO_SMALL"
    assert result.details.loc[0, "款式"] == ""


def test_load_product_dimensions_deduplicates_msku_and_parses_sku(
    monkeypatch,
    tmp_path: Path,
) -> None:
    workbook = tmp_path / "products.xlsx"
    workbook.touch()
    products = pd.DataFrame(
        [
            {
                "MSKU": " SK001-731 Black 38-39 ",
                "店铺/站点": "SEEKWAY:US",
                "Listing": "SK001",
                "产品名称": "SK001-731 黑",
                "SKU": "SK001-731 Black 38-39",
                "品类A": "水鞋",
                "品类B": "薄底水鞋",
            },
            {
                "MSKU": "SK001-731 Black 38-39",
                "店铺/站点": "SEEKWAY:US",
                "Listing": "SK001",
                "产品名称": "SK001-731 黑",
                "SKU": "SK001-731 Black 38-39",
                "品类A": "水鞋",
                "品类B": "薄底水鞋",
            },
        ]
    )
    monkeypatch.setattr(pd, "read_excel", lambda *args, **kwargs: products)

    result = load_product_dimensions(workbook)

    assert len(result) == 1
    assert result.loc[0, "sku"] == "SK001-731 Black 38-39"
    assert result.loc[0, "店铺/站点"] == "SEEKWAY:US"
    assert result.loc[0, "Listing"] == "SK001"
    assert result.loc[0, "款式"] == "731"
    assert result.loc[0, "颜色"] == "Black"
    assert result.loc[0, "尺码"] == "38-39"
    assert result.loc[0, "品类B"] == "薄底水鞋"


def test_load_product_dimensions_filters_store(
    monkeypatch,
    tmp_path: Path,
) -> None:
    workbook = tmp_path / "products.xlsx"
    workbook.touch()
    products = pd.DataFrame(
        [
            {
                "MSKU": "SKU-1",
                "店铺/站点": "SEEKWAY:US",
                "Listing": "SK001",
                "产品名称": "美国商品",
                "SKU": "SK001-731 Black 38-39",
                "品类A": "水鞋",
                "品类B": "薄底水鞋",
            },
            {
                "MSKU": "SKU-1",
                "店铺/站点": "SEEKWAY:CA",
                "Listing": "SK002",
                "产品名称": "加拿大商品",
                "SKU": "SK002-731 Black 38-39",
                "品类A": "水鞋",
                "品类B": "薄底水鞋",
            },
        ]
    )
    monkeypatch.setattr(pd, "read_excel", lambda *args, **kwargs: products)

    result = load_product_dimensions(workbook, store="SEEKWAY:US")

    assert len(result) == 1
    assert result.loc[0, "Listing"] == "SK001"
    assert result.loc[0, "产品名称"] == "美国商品"


def test_load_analysis_data_rejects_missing_columns(
    monkeypatch,
    tmp_path: Path,
) -> None:
    workbook = tmp_path / "result.xlsx"
    workbook.touch()
    sheets = {
        "分类明细": pd.DataFrame([{"分类键": "key-1"}]),
        "语义单元": pd.DataFrame(),
        "未知语义": pd.DataFrame(),
    }
    monkeypatch.setattr(pd, "read_excel", lambda *args, **kwargs: sheets)

    try:
        load_analysis_data(workbook)
    except ValueError as exc:
        assert "分类明细 缺少字段" in str(exc)
    else:
        raise AssertionError("缺失字段时应拒绝加载")
