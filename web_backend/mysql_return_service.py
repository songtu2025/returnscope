from __future__ import annotations

import csv
import re
import threading
import time
from contextlib import contextmanager
from typing import Any, Iterator

import pymysql

from return_semantics.data import (
    RETURN_COLUMNS,
    RETURN_STORE_COLUMN,
    SOURCE_ORIGIN_COLUMN,
)
from web_backend.api_contracts.datasets import (
    MySQLReturnImportRequest,
)
from web_backend.common import add_audit, new_id, utc_now
from web_backend.dataset_service import DatasetService
from web_backend.mysql_returns.common import (
    FIELD_LABELS as FIELD_LABELS,
)
from web_backend.mysql_returns.common import (
    MARKET_STORE_COLUMN,
    OPTIONAL_FIELDS,
    RAW_COMMENT_COLUMN,
    _quote_identifier,
)
from web_backend.mysql_returns.common import (
    MySQLSourceError as MySQLSourceError,
)
from web_backend.mysql_returns.query import _MySQLQueryBuilder, _validate_query_payload
from web_backend.settings import Settings

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


class MySQLReturnService:
    def __init__(self, datasets: DatasetService, settings: Settings) -> None:
        self.datasets = datasets
        self.settings = settings
        self._metadata_lock = threading.RLock()
        self._metadata: dict[str, tuple[float, list[dict[str, Any]]]] = {}

    def _metadata_rows(self, connection: Any, key: str) -> list[dict[str, Any]]:
        with self._metadata_lock:
            cached = self._metadata.get(key)
            if cached and time.monotonic() - cached[0] < 300:
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

    @contextmanager
    def _connection(self) -> Iterator[Any]:
        if not self.settings.mysql_user:
            raise MySQLSourceError("MySQL 数据源尚未配置，请联系维护人员完成连接配置")
        try:
            with pymysql.connect(
                host=self.settings.mysql_host,
                port=self.settings.mysql_port,
                user=self.settings.mysql_user,
                password=self.settings.mysql_password,
                database=self.settings.mysql_database,
                charset="utf8mb4",
                connect_timeout=5,
                read_timeout=60,
                write_timeout=10,
                cursorclass=pymysql.cursors.DictCursor,
            ) as connection:
                # 数据源仅用于读取，每次请求结束后关闭连接。
                with connection.cursor() as cursor:
                    cursor.execute("SET TRANSACTION READ ONLY")
                    cursor.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT")
                yield connection
        except pymysql.MySQLError as exc:
            code = exc.args[0] if exc.args else "未知"
            raise MySQLSourceError(
                f"MySQL 读取失败（错误码 {code}），请检查连接配置、表名和读取权限"
            ) from exc

    def _columns(self, connection: Any) -> list[dict[str, str]]:
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

    def schema(self, refresh: bool = False) -> dict[str, Any]:
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

    def _query(
        self,
        connection: Any,
        payload: MySQLReturnImportRequest,
        *,
        count_only: bool = False,
        market_rows: list[dict[str, Any]] | None = None,
    ) -> tuple[str, list[Any]]:
        columns = {item["name"] for item in self._metadata_rows(connection, "columns")}
        _validate_query_payload(payload, columns)
        automatic_store = (
            payload.mapping.get(RETURN_STORE_COLUMN) == MARKET_STORE_COLUMN
        )
        if automatic_store and market_rows is None:
            market_rows = self._metadata_rows(connection, "markets")
        builder = _MySQLQueryBuilder(
            payload=payload,
            columns=columns,
            count_only=count_only,
            market_rows=market_rows or [],
            table=_quote_identifier(self.settings.mysql_table),
        )
        return builder.build()

    def preview(self, payload: MySQLReturnImportRequest) -> dict[str, Any]:
        with self._connection() as connection:
            market_rows = (
                self._metadata_rows(connection, "markets")
                if payload.mapping.get(RETURN_STORE_COLUMN) == MARKET_STORE_COLUMN
                else None
            )
            query, values = self._query(
                connection, payload, count_only=True, market_rows=market_rows
            )
            with connection.cursor() as cursor:
                # 有界计数避免为预览扫描并返回无限量的数据。
                cursor.execute(
                    "SELECT COUNT(*) AS total, "
                    "COALESCE(SUM(TRIM(COALESCE(`店铺/站点`, '')) = ''), 0) AS missing_store_rows "
                    f"FROM ({query} LIMIT %s) AS preview_rows",
                    (*values, self.settings.mysql_max_rows + 1),
                )
                counts = cursor.fetchone()
                count = int(counts["total"])
                query, values = self._query(
                    connection, payload, market_rows=market_rows
                )
                cursor.execute(query + " LIMIT %s", (*values, 20))
                rows = list(cursor.fetchall())
        return {
            "row_count": count,
            "over_limit": count > self.settings.mysql_max_rows,
            "missing_store_rows": int(counts.get("missing_store_rows", 0)),
            "rows": [
                {
                    key: value
                    for key, value in row.items()
                    if key != SOURCE_ORIGIN_COLUMN
                }
                for row in rows
            ],
        }

    def import_returns(
        self, payload: MySQLReturnImportRequest, actor_id: str
    ) -> dict[str, Any]:
        path = self.settings.data_dir / "tmp" / f"{new_id('mysql')}.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._connection() as connection:
                query, values = self._query(connection, payload)
                with connection.cursor(pymysql.cursors.SSDictCursor) as cursor:
                    cursor.execute(
                        query + " LIMIT %s", (*values, self.settings.mysql_max_rows + 1)
                    )
                    with path.open("w", encoding="utf-8-sig", newline="") as output:
                        writer = csv.DictWriter(
                            output,
                            fieldnames=[
                                *RETURN_COLUMNS,
                                RETURN_STORE_COLUMN,
                                SOURCE_ORIGIN_COLUMN,
                            ],
                        )
                        writer.writeheader()
                        count = 0
                        for row in cursor:
                            count += 1
                            if count > self.settings.mysql_max_rows:
                                raise ValueError(
                                    "查询结果超过单次导入上限，请缩小筛选范围"
                                )
                            if not str(row.get(RETURN_STORE_COLUMN) or "").strip():
                                raise ValueError(
                                    "查询结果中存在空的店铺/站点，请修正字段映射或源数据"
                                )
                            writer.writerow(row)
            if count == 0:
                raise ValueError("当前筛选条件下没有退货数据")
            fetched_at = utc_now()
            result = self.datasets.import_returns(
                source_path=path,
                original_name=f"{self.settings.mysql_table}.csv",
                content_type="text/csv",
                mode="analyze_only",
                actor_id=actor_id,
                change_note=f"从 MySQL {self.settings.mysql_database}.{self.settings.mysql_table} 拉取",
            )
            add_audit(
                self.datasets.database,
                "dataset",
                result["dataset"]["id"],
                "import_mysql_returns",
                actor_id,
                after={
                    "database": self.settings.mysql_database,
                    "table": self.settings.mysql_table,
                    "query": payload.model_dump(mode="json"),
                    "fetched_at": fetched_at,
                    "row_count": count,
                    "version_id": result["version_id"],
                },
            )
            return result
        finally:
            path.unlink(missing_ok=True)
