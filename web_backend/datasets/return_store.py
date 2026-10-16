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
    row_count INTEGER NOT NULL
);
CREATE TABLE return_rows (
    version_id TEXT NOT NULL REFERENCES return_rowsets(version_id) ON DELETE CASCADE,
    row_index INTEGER NOT NULL,
    store_site TEXT NOT NULL,
    category TEXT NOT NULL,
    values_json TEXT NOT NULL,
    search_values_json TEXT NOT NULL,
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
        "INSERT INTO return_rowsets VALUES (?, ?, ?)",
        (version_id, json.dumps(columns, ensure_ascii=False), len(frame)),
    )

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
            yield (
                version_id,
                index,
                record.get("店铺/站点", "").strip(),
                category,
                json.dumps(values, ensure_ascii=False),
                # 预先转小写，复用 JSON 查询避免每次逐字段执行 Python 文本转换。
                json.dumps([value.lower() for value in values], ensure_ascii=False),
            )

    connection.executemany(
        "INSERT INTO return_rows VALUES (?, ?, ?, ?, ?, ?)", records()
    )


def return_preview(
    connection: sqlite3.Connection,
    version: Any,
    pagination: tuple[int, int],
    filters: dict[str, str],
) -> dict[str, Any]:
    source = connection.execute(
        "SELECT columns_json, row_count FROM return_rowsets WHERE version_id=?",
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
        where.append(
            "EXISTS (SELECT 1 FROM json_each(r.search_values_json) "
            "WHERE instr(value, ?) > 0)"
        )
        parameters.append(filters["query"].strip().lower())
    condition = " AND ".join(where)
    total = connection.execute(
        f"SELECT count(*) FROM return_rows r WHERE {condition}", parameters
    ).fetchone()[0]
    offset, limit = pagination
    rows = connection.execute(
        f"SELECT row_index, values_json FROM return_rows r WHERE {condition} "
        "ORDER BY row_index LIMIT ? OFFSET ?",
        (*parameters, limit, offset),
    ).fetchall()
    facets = {
        key: [
            row[0]
            for row in connection.execute(
                f"SELECT DISTINCT {column} FROM return_rows "
                f"WHERE version_id=? AND {column}<>'' ORDER BY {column}",
                (version["id"],),
            )
        ]
        for key, column in (("stores", "store_site"), ("categories", "category"))
    }
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
