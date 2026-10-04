from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Any, Iterator

import pymysql

from return_semantics.data import (
    RETURN_STORE_COLUMN,
)
from web_backend.api_contracts.datasets import (
    MySQLReturnImportRequest,
)
from web_backend.dataset_service import DatasetService
from web_backend.mysql_returns.common import (
    FIELD_LABELS as FIELD_LABELS,
)
from web_backend.mysql_returns.common import (
    MARKET_STORE_COLUMN,
    _quote_identifier,
)
from web_backend.mysql_returns.common import (
    MySQLSourceError as MySQLSourceError,
)
from web_backend.mysql_returns.import_flow import import_returns, preview
from web_backend.mysql_returns.metadata import _columns, _metadata_rows, schema
from web_backend.mysql_returns.query import _MySQLQueryBuilder, _validate_query_payload
from web_backend.settings import Settings


class MySQLReturnService:
    preview = preview
    import_returns = import_returns
    _metadata_rows = _metadata_rows
    _columns = _columns
    schema = schema

    def __init__(self, datasets: DatasetService, settings: Settings) -> None:
        self.datasets = datasets
        self.settings = settings
        self._metadata_lock = threading.RLock()
        self._metadata: dict[str, tuple[float, list[dict[str, Any]]]] = {}

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
