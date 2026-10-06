from collections.abc import Mapping

import pandas as pd

ISSUE_REASONS = {
    "missing_store": "缺少店铺/站点",
    "missing_source_sku": "缺少退货 SKU",
    "unmatched_product": "店铺/站点 + 退货 SKU 未匹配商品",
    "missing_category": "已匹配商品缺少品类",
    "missing_product_name": "已匹配商品缺少产品名称",
}


def quality_masks(
    values: Mapping[str, pd.Series], matched: pd.Series
) -> dict[str, pd.Series]:
    return {
        "missing_store": values["store_site"].eq(""),
        "missing_source_sku": values["source_sku"].eq(""),
        "unmatched_product": ~matched,
        "missing_category": (
            matched & values["category_a"].eq("") & values["category_b"].eq("")
        ),
        "missing_product_name": matched & values["product_name"].eq(""),
    }
