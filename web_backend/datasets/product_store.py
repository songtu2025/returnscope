"""按不可变资料摘要存储产品行；Excel 仅作为输入和导出产物。"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from return_semantics.product_identity import validate_product_identities
from web_backend.database_sql_migrations import (
    RegisteredSqlMigration,
    apply_sql_migration,
)

if TYPE_CHECKING:
    from web_backend.database import Database

PRODUCT_SHEET = "产品信息汇总表"
PRODUCT_STORE_SQL = """
CREATE TABLE product_workbooks (
    sha256 TEXT PRIMARY KEY,
    columns_json TEXT NOT NULL,
    other_sheets_json TEXT NOT NULL
);
CREATE TABLE product_rows (
    sha256 TEXT NOT NULL REFERENCES product_workbooks(sha256) ON DELETE CASCADE,
    row_index INTEGER NOT NULL,
    store_site TEXT NOT NULL,
    msku TEXT NOT NULL,
    values_json TEXT NOT NULL,
    PRIMARY KEY (sha256, row_index),
    UNIQUE (sha256, store_site, msku)
);
"""


def migrate_product_store(connection: sqlite3.Connection) -> None:
    apply_sql_migration(
        connection,
        RegisteredSqlMigration(
            "20261017_product_rows",
            hashlib.sha256(PRODUCT_STORE_SQL.encode()).hexdigest(),
            PRODUCT_STORE_SQL,
        ),
        savepoint="product_rows",
        checksum_error="产品明细迁移校验失败",
    )


def save_product_workbook(
    connection: sqlite3.Connection,
    digest: str,
    workbook: dict[str, pd.DataFrame],
) -> None:
    frame = workbook[PRODUCT_SHEET].fillna("").astype(str)
    validate_product_identities(frame)
    if connection.execute(
        "SELECT 1 FROM product_workbooks WHERE sha256 = ?", (digest,)
    ).fetchone():
        return
    others = {
        name: None
        if name == PRODUCT_SHEET
        else {
            "columns": list(sheet.columns),
            "data": sheet.fillna("").astype(str).values.tolist(),
        }
        for name, sheet in workbook.items()
    }
    connection.execute(
        "INSERT INTO product_workbooks VALUES (?, ?, ?)",
        (
            digest,
            json.dumps(list(frame.columns), ensure_ascii=False),
            json.dumps(others, ensure_ascii=False),
        ),
    )
    connection.executemany(
        "INSERT INTO product_rows VALUES (?, ?, ?, ?, ?)",
        (
            (
                digest,
                index,
                str(row[frame.columns.get_loc("店铺/站点")]).strip(),
                str(row[frame.columns.get_loc("MSKU")]).strip(),
                json.dumps(row, ensure_ascii=False),
            )
            for index, row in enumerate(frame.itertuples(index=False, name=None))
        ),
    )


def _source_digest(connection: sqlite3.Connection, path: Path) -> str:
    row = connection.execute(
        "SELECT sha256 FROM dataset_versions WHERE file_path = ?", (str(path),)
    ).fetchone()
    return str(row[0]) if row else path.stem


def product_frame(connection: sqlite3.Connection, path: Path) -> pd.DataFrame:
    digest = _source_digest(connection, path)
    source = connection.execute(
        "SELECT columns_json FROM product_workbooks WHERE sha256 = ?", (digest,)
    ).fetchone()
    if source is None:
        raise ValueError("产品资料尚未入库，请由部署负责人执行产品资料迁移")
    rows = connection.execute(
        "SELECT values_json FROM product_rows WHERE sha256 = ? ORDER BY row_index",
        (digest,),
    ).fetchall()
    return pd.DataFrame(
        [json.loads(row[0]) for row in rows], columns=json.loads(source[0])
    )


def load_product_frame(database: Database, path: Path) -> pd.DataFrame:
    with database.connect() as connection:
        return product_frame(connection, path)


def load_product_workbook(database: Database, path: Path) -> dict[str, pd.DataFrame]:
    with database.connect() as connection:
        return product_workbook(connection, path)


def product_workbook(
    connection: sqlite3.Connection, path: Path
) -> dict[str, pd.DataFrame]:
    frame = product_frame(connection, path)
    row = connection.execute(
        "SELECT other_sheets_json FROM product_workbooks WHERE sha256 = ?",
        (_source_digest(connection, path),),
    ).fetchone()
    return {
        name: frame if sheet is None else pd.DataFrame(**sheet)
        for name, sheet in json.loads(row[0]).items()
    }
