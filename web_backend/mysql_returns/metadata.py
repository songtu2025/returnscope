from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING, Any

from return_semantics.data import RETURN_STORE_COLUMN
from web_backend.mysql_returns.common import (
    FIELD_LABELS,
    MARKET_STORE_COLUMN,
    OPTIONAL_FIELDS,
    RAW_COMMENT_COLUMN,
    MySQLSourceError,
    _quote_identifier,
)

if TYPE_CHECKING:
    from web_backend.mysql_return_service import MySQLReturnService

METADATA_TTL_SECONDS = 300

MARKET_STORES_SQL = """
SELECT records.jijia_account_id, shops.market_id, MAX(shops.market_name) AS store
FROM (
    SELECT DISTINCT jijia_account_id
    FROM {return_table}
    WHERE jijia_account_id IS NOT NULL
) AS accounts
JOIN raw_api_data AS records
  ON records.jijia_account_id = accounts.jijia_account_id
 AND records.api_code = 'amazon_shop_page'
JOIN JSON_TABLE(
    records.raw_json, '$.marketListVos[*]' COLUMNS(
        market_id INT PATH '$.marketId',
        market_name VARCHAR(100) PATH '$.marketName'
    )
) AS shops
WHERE shops.market_id IS NOT NULL
  AND TRIM(COALESCE(shops.market_name, '')) <> ''
GROUP BY records.jijia_account_id, shops.market_id
HAVING COUNT(DISTINCT shops.market_name) = 1
"""


def _metadata_rows(
    self: MySQLReturnService, connection: Any, key: str
) -> list[dict[str, Any]]:
    with self._metadata_lock:
        cached = self._metadata.get(key)
        if cached and time.monotonic() - cached[0] < METADATA_TTL_SECONDS:
            return cached[1]
        if key == "columns":
            rows = self._columns(connection)
        else:
            with connection.cursor() as cursor:
                cursor.execute(
                    MARKET_STORES_SQL.format(
                        return_table=_quote_identifier(self.settings.mysql_table)
                    )
                )
                rows = list(cursor.fetchall())
        self._metadata[key] = (time.monotonic(), rows)
        return rows


def _columns(self: MySQLReturnService, connection: Any) -> list[dict[str, str]]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COLUMN_NAME AS name, DATA_TYPE AS type "
            "FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s "
            "ORDER BY ORDINAL_POSITION",
            (self.settings.mysql_database, self.settings.mysql_table),
        )
        columns = list(cursor.fetchall())
    if not columns:
        raise MySQLSourceError("找不到配置的退货数据表，或当前账号没有读取权限")
    names = {column["name"] for column in columns}
    if (
        self.settings.mysql_table == "sale_return_order"
        and {"raw_data_id", "jijia_account_id"} <= names
    ):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COLUMN_NAME AS name FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'raw_api_data'",
                (self.settings.mysql_database,),
            )
            raw_columns = {column["name"] for column in cursor.fetchall()}
        if {"id", "jijia_account_id", "raw_json"} <= raw_columns:
            columns.append(
                {
                    "name": RAW_COMMENT_COLUMN,
                    "type": "text",
                    "label": "客户评论（原始记录）",
                }
            )
            if "market_id" in names:
                columns.append(
                    {
                        "name": MARKET_STORE_COLUMN,
                        "type": "varchar",
                        "label": "店铺/站点（自动关联）",
                    }
                )
    return columns


def schema(self: MySQLReturnService, refresh: bool = False) -> dict[str, Any]:
    if refresh:
        with self._metadata_lock:
            self._metadata.clear()
    result: dict[str, Any] = {
        "configured": bool(self.settings.mysql_user),
        "database": self.settings.mysql_database,
        "table": self.settings.mysql_table,
        "max_rows": self.settings.mysql_max_rows,
    }
    if not result["configured"]:
        return result
    with self._connection() as connection:
        columns = self._metadata_rows(connection, "columns")
        if any(column["name"] == MARKET_STORE_COLUMN for column in columns):
            result["stores"] = sorted(
                {row["store"] for row in self._metadata_rows(connection, "markets")}
            )
    normalized = {
        re.sub(r"[-_\s]", "", column["name"]).lower(): column["name"]
        for column in columns
    }
    result["columns"] = columns
    result["fields"] = [
        {"name": key, "label": label, "required": key not in OPTIONAL_FIELDS}
        for key, label in FIELD_LABELS.items()
    ]
    result["mapping"] = {
        key: normalized.get(re.sub(r"[-_\s]", "", key).lower(), "")
        for key in FIELD_LABELS
    }
    # 分析流程通过退货记录的 MSKU 匹配产品信息，不能误用内部 SKU。
    if "msku" in normalized:
        result["mapping"]["sku"] = normalized["msku"]
    for key, source in (
        ("return-date", "returndatetime"),
        ("customer-comments", "rawcustomercomments"),
        (RETURN_STORE_COLUMN, "marketstore"),
    ):
        if not result["mapping"][key]:
            result["mapping"][key] = normalized.get(source, "")
    return result
