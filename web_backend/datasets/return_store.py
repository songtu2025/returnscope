"""不可变反馈版本的查询投影；原文件继续用于溯源和任务执行。"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any

import pandas as pd

from web_backend.database_sql_migrations import (
    RegisteredSqlMigration,
    apply_sql_migration,
)

RETURN_STORE_SQL = """
CREATE TABLE return_rowsets (
    version_id TEXT PRIMARY KEY REFERENCES dataset_versions(id) ON DELETE CASCADE,
    columns_json TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    facets_json TEXT NOT NULL
);
CREATE TABLE return_rows (
    version_id TEXT NOT NULL REFERENCES return_rowsets(version_id) ON DELETE CASCADE,
    row_index INTEGER NOT NULL,
    store_site TEXT NOT NULL,
    category TEXT NOT NULL,
    values_json TEXT NOT NULL,
    search_text TEXT NOT NULL,
    PRIMARY KEY (version_id, row_index)
);
CREATE INDEX idx_return_rows_store ON return_rows(version_id, store_site, row_index);
CREATE INDEX idx_return_rows_category ON return_rows(version_id, category, row_index);
"""


def migrate_return_store(connection: sqlite3.Connection) -> None:
    apply_sql_migration(
        connection,
        RegisteredSqlMigration(
            "20261017_return_query_rows",
            hashlib.sha256(RETURN_STORE_SQL.encode()).hexdigest(),
            RETURN_STORE_SQL,
        ),
        savepoint="return_query_rows",
        checksum_error="反馈查询明细迁移校验失败",
    )


def save_return_frame(
    connection: sqlite3.Connection, version_id: str, frame: pd.DataFrame
) -> None:
    if connection.execute(
        "SELECT 1 FROM return_rowsets WHERE version_id=?", (version_id,)
    ).fetchone():
        return
    frame = frame.fillna("").astype(str)
    columns = list(frame.columns)
    connection.execute(
        "INSERT INTO return_rowsets VALUES (?, ?, ?, '{}')",
        (version_id, json.dumps(columns, ensure_ascii=False), len(frame)),
    )
    stores: set[str] = set()
    categories: set[str] = set()

    def records():
        for index, values in enumerate(frame.itertuples(index=False, name=None)):
            record = dict(zip(columns, values, strict=True))
            category = ""
            if {"品类A", "品类B"}.issubset(record):
                category = " > ".join(
                    value
                    for key in ("品类A", "品类B")
                    if (value := record[key].strip())
                )
            store = record.get("店铺/站点", "").strip()
            if store:
                stores.add(store)
            if category:
                categories.add(category)
            yield (
                version_id,
                index,
                store,
                category,
                json.dumps(values, ensure_ascii=False),
                # 空字符隔开字段，使普通子串搜索不会跨字段匹配。
                "\0".join(value.lower() for value in values),
            )

    connection.executemany(
        "INSERT INTO return_rows VALUES (?, ?, ?, ?, ?, ?)", records()
    )
    connection.execute(
        "UPDATE return_rowsets SET facets_json=? WHERE version_id=?",
        (
            json.dumps(
                {"stores": sorted(stores), "categories": sorted(categories)},
                ensure_ascii=False,
            ),
            version_id,
        ),
    )


def return_preview(
    connection: sqlite3.Connection,
    version: Any,
    pagination: tuple[int, int],
    filters: dict[str, str],
) -> dict[str, Any]:
    source = connection.execute(
        "SELECT columns_json, row_count, facets_json FROM return_rowsets WHERE version_id=?",
        (version["id"],),
    ).fetchone()
    if source is None:
        raise ValueError("反馈查询明细尚未入库，请由部署负责人执行数据库升级")
    columns = json.loads(source[0])
    where = ["r.version_id=?"]
    parameters: list[Any] = [version["id"]]
    for key, column in (("store", "store_site"), ("category", "category")):
        if filters[key].strip() and (key != "store" or "店铺/站点" in columns):
            where.append(f"r.{column}=?")
            parameters.append(filters[key].strip())
    if filters["query"].strip():
        query = filters["query"].strip().lower()
        where.append("instr(r.search_text, ?) > 0")
        parameters.append(query)
        if "\0" in query:
            connection.create_function(
                "feedback_contains",
                2,
                lambda values, text: any(
                    text in value.lower() for value in json.loads(values)
                ),
            )
            where.append("feedback_contains(r.values_json, ?)")
            parameters.append(query)
    condition = " AND ".join(where)
    total = (
        source[1]
        if len(where) == 1
        else connection.execute(
            f"SELECT count(*) FROM return_rows r WHERE {condition}", parameters
        ).fetchone()[0]
    )
    offset, limit = pagination
    rows = connection.execute(
        f"SELECT row_index, values_json FROM return_rows r WHERE {condition} "
        "ORDER BY row_index LIMIT ? OFFSET ?",
        (*parameters, limit, offset),
    ).fetchall()
    facets = json.loads(source[2])
    if not any(value.strip() for value in filters.values()):
        facets["categories"] = []
    return {
        "records": [
            {
                **dict(zip(columns, json.loads(row[1]), strict=True)),
                "_row_index": row[0],
            }
            for row in rows
        ],
        "offset": offset,
        "limit": limit,
        "total": total,
        "source_total": source[1],
        "query": filters["query"],
        "version": int(version["selected_version"]),
        "facets": facets,
    }
