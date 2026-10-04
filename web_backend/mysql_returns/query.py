from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from return_semantics.data import RETURN_STORE_COLUMN, SOURCE_ORIGIN_COLUMN
from web_backend.api_contracts.datasets import MySQLReturnImportRequest
from web_backend.mysql_returns.common import (
    FIELD_LABELS,
    MARKET_STORE_COLUMN,
    OPTIONAL_FIELDS,
    RAW_COMMENT_COLUMN,
    _quote_identifier,
)


def _validate_query_payload(
    payload: MySQLReturnImportRequest, columns: set[str]
) -> None:
    if set(payload.mapping) - FIELD_LABELS.keys():
        raise ValueError("字段映射包含未知的目标字段")
    for key, label in FIELD_LABELS.items():
        source = payload.mapping.get(key, "")
        if source and source not in columns:
            raise ValueError(f"{label}对应的数据库字段不存在，请重新读取字段")
        if not source and key not in OPTIONAL_FIELDS:
            raise ValueError(f"请选择{label}对应的数据库字段")
    if (
        not payload.mapping.get(RETURN_STORE_COLUMN)
        and not payload.default_store.strip()
    ):
        raise ValueError("请选择店铺/站点字段，或填写本批数据的固定店铺/站点")
    if (
        MARKET_STORE_COLUMN in columns
        and payload.mapping.get(RETURN_STORE_COLUMN) != MARKET_STORE_COLUMN
    ):
        raise ValueError("当前退货表请使用自动关联的店铺/站点，避免混淆不同市场")
    if payload.date_from and payload.date_to and payload.date_from > payload.date_to:
        raise ValueError("开始日期不能晚于结束日期")
    if payload.date_to == date.max:
        raise ValueError("结束日期超出支持范围")


@dataclass
class _MySQLQueryBuilder:
    payload: MySQLReturnImportRequest
    columns: set[str]
    count_only: bool
    market_rows: list[dict[str, Any]]
    table: str
    selected_store: str = field(init=False)
    automatic_store: bool = field(init=False)
    used_sources: set[str] = field(default_factory=set)
    selection_values: list[Any] = field(default_factory=list)
    filter_values: list[Any] = field(default_factory=list)
    join_values: list[Any] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.selected_store = self.payload.store.strip()
        self.automatic_store = (
            self.payload.mapping.get(RETURN_STORE_COLUMN) == MARKET_STORE_COLUMN
        )

    def _market_store_sql(self, values: list[Any]) -> str:
        if self.selected_store:
            values.append(self.selected_store)
            return "%s"
        if not self.count_only:
            return "markets.store"

        by_account: dict[int, list[int]] = {}
        for row in self.market_rows:
            by_account.setdefault(row["jijia_account_id"], []).append(row["market_id"])
        clauses = []
        for account, markets in by_account.items():
            placeholders = ", ".join("%s" for _ in markets)
            clauses.append(
                "(source.jijia_account_id = %s AND source.market_id IN ("
                f"{placeholders}))"
            )
            values.extend((account, *markets))
        matched = " OR ".join(clauses) or "0 = 1"
        return f"CASE WHEN {matched} THEN 'mapped' ELSE '' END"

    def _column_sql(self, source: str, values: list[Any]) -> str:
        self.used_sources.add(source)
        if source == MARKET_STORE_COLUMN:
            return self._market_store_sql(values)
        if source == RAW_COMMENT_COLUMN:
            return (
                "NULLIF(JSON_UNQUOTE(JSON_EXTRACT("
                "raw.raw_json, '$.customerComments')), 'null')"
            )
        return f"source.{_quote_identifier(source)}"

    def _selections(self) -> list[str]:
        selections = []
        keys = (RETURN_STORE_COLUMN,) if self.count_only else tuple(FIELD_LABELS)
        for key in keys:
            mapped_source = self.payload.mapping.get(key)
            if mapped_source:
                expression = self._column_sql(mapped_source, self.selection_values)
            else:
                expression = "%s"
                self.selection_values.append(
                    self.payload.default_store.strip()
                    if key == RETURN_STORE_COLUMN
                    else ""
                )
            selections.append(f"{expression} AS {_quote_identifier(key)}")
        if not self.count_only and "id" in self.columns:
            selections.append(f"source.id AS {_quote_identifier(SOURCE_ORIGIN_COLUMN)}")
        return selections

    def _automatic_store_condition(self) -> str | None:
        if not self.automatic_store or not self.selected_store:
            return None
        pairs = [row for row in self.market_rows if row["store"] == self.selected_store]
        for row in pairs:
            self.filter_values.extend((row["jijia_account_id"], row["market_id"]))
        if not pairs:
            return "0 = 1"
        pair_sql = " OR ".join(
            "(source.jijia_account_id = %s AND source.market_id = %s)" for _ in pairs
        )
        return f"({pair_sql})"

    def _conditions(self) -> list[str]:
        conditions = []
        automatic_store_condition = self._automatic_store_condition()
        if automatic_store_condition:
            conditions.append(automatic_store_condition)
        filters = (
            ("return-date", ">=", self.payload.date_from),
            (
                "return-date",
                "<",
                self.payload.date_to + timedelta(days=1)
                if self.payload.date_to
                else None,
            ),
            (RETURN_STORE_COLUMN, "=", self.selected_store),
            ("sku", "=", self.payload.sku.strip()),
        )
        for key, operator, value in filters:
            if value is None or value == "":
                continue
            if key == RETURN_STORE_COLUMN and self.automatic_store:
                continue
            mapped_source = self.payload.mapping.get(key)
            if mapped_source:
                conditions.append(
                    f"{self._column_sql(mapped_source, self.filter_values)} "
                    f"{operator} %s"
                )
            else:
                conditions.append(f"%s {operator} %s")
                self.filter_values.append(self.payload.default_store.strip())
            self.filter_values.append(value)
        return conditions

    def _joins(self) -> str:
        joins = ""
        if RAW_COMMENT_COLUMN in self.used_sources:
            joins += (
                " LEFT JOIN raw_api_data AS raw ON raw.id = source.raw_data_id"
                " AND raw.jijia_account_id = source.jijia_account_id"
            )
        if (
            MARKET_STORE_COLUMN in self.used_sources
            and not self.selected_store
            and not self.count_only
        ):
            joins += (
                " LEFT JOIN JSON_TABLE(%s, '$[*]' COLUMNS("
                "jijia_account_id BIGINT PATH '$.jijia_account_id', "
                "market_id BIGINT PATH '$.market_id', "
                "store VARCHAR(100) PATH '$.store')) AS markets"
                " ON markets.jijia_account_id = source.jijia_account_id"
                " AND markets.market_id = source.market_id"
            )
            self.join_values.append(json.dumps(self.market_rows, ensure_ascii=False))
        return joins

    def _order_by(self) -> str:
        if self.count_only or "id" not in self.columns:
            return ""
        date_column = self.payload.mapping["return-date"]
        if date_column in {MARKET_STORE_COLUMN, RAW_COMMENT_COLUMN}:
            return ""
        return f" ORDER BY source.{_quote_identifier(date_column)}, source.id"

    def build(self) -> tuple[str, list[Any]]:
        selections = self._selections()
        conditions = self._conditions()
        query = f"SELECT {', '.join(selections)} FROM {self.table} AS source"
        query += self._joins()
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += self._order_by()
        values = [*self.selection_values, *self.join_values, *self.filter_values]
        return query, values
