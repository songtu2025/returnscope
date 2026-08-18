from __future__ import annotations

import hashlib
import json
from typing import Any

from return_semantics.data import (
    PRODUCT_CATEGORY_COLUMNS,
    PRODUCT_COLUMNS,
    PRODUCT_DETAIL_COLUMNS,
    RETURN_COLUMNS,
    RETURN_STORE_COLUMN,
)
from web_backend.dataset_service import ALLOWED_EXTENSIONS, PRODUCT_WORKSHEET


def list_import_rules() -> dict[str, list[dict[str, Any]]]:
    rules = [
        {
            "id": "returns-standard-v1",
            "kind": "returns",
            "name": "标准退货数据",
            "version": 1,
            "status": "active",
            "source": "system",
            "file_extensions": sorted(ALLOWED_EXTENSIONS["returns"]),
            "worksheet": None,
            "required_columns": list(RETURN_COLUMNS),
            "optional_columns": [RETURN_STORE_COLUMN],
            "match_key": [RETURN_STORE_COLUMN, "sku"],
            "notes": [
                "店铺/站点为可选字段，上传时可统一补充空值",
            ],
        },
        {
            "id": "products-standard-v1",
            "kind": "products",
            "name": "标准商品信息",
            "version": 1,
            "status": "active",
            "source": "system",
            "file_extensions": sorted(ALLOWED_EXTENSIONS["products"]),
            "worksheet": PRODUCT_WORKSHEET,
            "required_columns": list(PRODUCT_COLUMNS),
            "optional_columns": list(
                PRODUCT_CATEGORY_COLUMNS + PRODUCT_DETAIL_COLUMNS
            ),
            "match_key": [RETURN_STORE_COLUMN, "MSKU"],
            "notes": [
                "品类字段影响分类路由",
                "产品名称和产品 SKU 影响结果展示",
            ],
        },
    ]
    for rule in rules:
        rule["content_hash"] = hashlib.sha256(
            json.dumps(
                rule,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
    return {"items": rules}
