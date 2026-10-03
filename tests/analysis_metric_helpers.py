import pandas as pd


def details() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "分类键": "key-1",
                "return_date": pd.Timestamp("2026-07-01", tz="UTC"),
                "sku": "SKU-1",
                "asin": "ASIN-1",
                "品类A": "水鞋",
                "品类B": "薄底水鞋",
                "Listing": "SK001",
                "款式": "731",
                "尺码": "38-39",
                "Amazon原因": "TOO_SMALL",
                "问题标签": "FIT_TOO_SMALL:偏小 | COMFORT_GENERAL:不舒适",
                "主因标签": "FIT_TOO_SMALL:偏小",
                "部位": "TOE | TOE | WHOLE_SHOE",
                "Listing承诺关系": "NONE",
                "处理状态": "AUTO_APPROVED",
                "复核原因": "",
                "has_text": True,
            },
            {
                "分类键": "key-2",
                "return_date": pd.Timestamp("2026-07-02", tz="UTC"),
                "sku": "SKU-1",
                "asin": "ASIN-1",
                "品类A": "水鞋",
                "品类B": "薄底水鞋",
                "Listing": "SK001",
                "款式": "731",
                "尺码": "38-39",
                "Amazon原因": "TOO_SMALL",
                "问题标签": "FIT_TOO_SMALL:偏小",
                "主因标签": "FIT_TOO_SMALL:偏小",
                "部位": "TOE",
                "Listing承诺关系": "CONTRADICTS",
                "处理状态": "MANUAL_REVIEW",
                "复核原因": "Amazon 原因与评论方向冲突",
                "has_text": True,
            },
            {
                "分类键": "",
                "return_date": pd.Timestamp("2026-08-01", tz="UTC"),
                "sku": "SKU-2",
                "asin": "ASIN-2",
                "品类A": "水鞋",
                "品类B": "厚底水鞋",
                "Listing": "SK002",
                "款式": "782",
                "尺码": "40-41",
                "Amazon原因": "UNWANTED",
                "问题标签": "",
                "主因标签": "",
                "部位": "",
                "Listing承诺关系": "",
                "处理状态": "NO_TEXT_EVIDENCE",
                "复核原因": "",
                "has_text": False,
            },
        ]
    )


def catalog() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "标签编码": "FIT_TOO_SMALL",
                "标签名称": "偏小",
                "一级分类": "尺码与合脚",
            },
            {
                "标签编码": "COMFORT_GENERAL",
                "标签名称": "不舒适",
                "一级分类": "体感",
            },
        ]
    )
