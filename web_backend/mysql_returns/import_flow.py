from __future__ import annotations

import csv
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pymysql

from return_semantics.data import (
    RETURN_COLUMNS,
    RETURN_STORE_COLUMN,
    SOURCE_ORIGIN_COLUMN,
)
from web_backend.api_contracts.datasets import MySQLReturnImportRequest
from web_backend.common import add_audit, new_id, utc_now
from web_backend.mysql_returns.common import MARKET_STORE_COLUMN

if TYPE_CHECKING:
    from web_backend.mysql_return_service import MySQLReturnService


def preview(
    self: MySQLReturnService, payload: MySQLReturnImportRequest
) -> dict[str, Any]:
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
            query, values = self._query(connection, payload, market_rows=market_rows)
            cursor.execute(query + " LIMIT %s", (*values, 20))
            rows = list(cursor.fetchall())
    return {
        "row_count": count,
        "over_limit": count > self.settings.mysql_max_rows,
        "missing_store_rows": int(counts.get("missing_store_rows", 0)),
        "rows": [
            {key: value for key, value in row.items() if key != SOURCE_ORIGIN_COLUMN}
            for row in rows
        ],
    }


def _write_snapshot(
    self: MySQLReturnService,
    connection: Any,
    path: Path,
    payload: MySQLReturnImportRequest,
) -> int:
    query, values = self._query(connection, payload)
    with connection.cursor(pymysql.cursors.SSDictCursor) as cursor:
        cursor.execute(query + " LIMIT %s", (*values, self.settings.mysql_max_rows + 1))
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
                    raise ValueError("查询结果超过单次导入上限，请缩小筛选范围")
                if not str(row.get(RETURN_STORE_COLUMN) or "").strip():
                    raise ValueError(
                        "查询结果中存在空的店铺/站点，请修正字段映射或源数据"
                    )
                writer.writerow(row)
    return count


def import_returns(
    self: MySQLReturnService, payload: MySQLReturnImportRequest, actor_id: str
) -> dict[str, Any]:
    path = self.settings.data_dir / "tmp" / f"{new_id('mysql')}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with self._connection() as connection:
            count = _write_snapshot(self, connection, path, payload)
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
