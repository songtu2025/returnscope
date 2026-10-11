"""商品标识变更的持久关联；不改变任务的原始匹配证据。"""

from __future__ import annotations

import hashlib
import sqlite3
from collections import Counter

from web_backend.database_sql_migrations import (
    RegisteredSqlMigration,
    apply_sql_migration,
)

PRODUCT_ALIAS_MIGRATION = "20261011_product_identity_aliases"
PRODUCT_ALIAS_SQL = """
CREATE TABLE product_identity_aliases (
    dataset_id TEXT NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    store_site TEXT NOT NULL,
    msku TEXT NOT NULL,
    current_store TEXT NOT NULL,
    current_msku TEXT NOT NULL,
    PRIMARY KEY(dataset_id, store_site, msku)
);
CREATE INDEX idx_product_identity_aliases_current
ON product_identity_aliases(dataset_id, current_store, current_msku);
"""


def migrate_product_aliases(connection: sqlite3.Connection) -> None:
    apply_sql_migration(
        connection,
        RegisteredSqlMigration(
            PRODUCT_ALIAS_MIGRATION,
            hashlib.sha256(PRODUCT_ALIAS_SQL.encode()).hexdigest(),
            PRODUCT_ALIAS_SQL,
        ),
        savepoint="migrate_product_aliases",
        checksum_error="商品标识关联迁移校验失败",
    )


def save_product_aliases(
    connection: sqlite3.Connection,
    dataset_id: str,
    previous: list[tuple[str, str]],
    current: list[tuple[str, str]],
) -> None:
    """只有明确的一对一行编辑才允许建立标识关系。"""
    old_counts, new_counts = Counter(previous), Counter(current)
    changes = [
        (old, new) for old, new in zip(previous, current, strict=False) if old != new
    ]
    for old, new in changes:
        if old_counts[old] != 1 or new_counts[new] != 1 or old in new_counts:
            raise ValueError("商品标识存在重复，无法确定关联，请先核对店铺和 MSKU")
        occupied = connection.execute(
            "SELECT current_store, current_msku FROM product_identity_aliases WHERE dataset_id = ? "
            "AND store_site = ? AND msku = ?",
            (dataset_id, *new),
        ).fetchone()
        if (occupied and tuple(occupied) != old) or new in old_counts:
            raise ValueError("该商品标识已被使用，请核对店铺和 MSKU")
    for old, new in changes:
        # 同一商品改回旧标识时移除终点别名，避免形成环。
        connection.execute(
            "DELETE FROM product_identity_aliases WHERE dataset_id = ? AND store_site = ? AND msku = ?",
            (dataset_id, *new),
        )
        connection.execute(
            "UPDATE product_identity_aliases SET current_store = ?, current_msku = ? "
            "WHERE dataset_id = ? AND current_store = ? AND current_msku = ?",
            (*new, dataset_id, *old),
        )
        connection.execute(
            "INSERT INTO product_identity_aliases VALUES (?, ?, ?, ?, ?)",
            (dataset_id, *old, *new),
        )


def product_aliases(
    connection: sqlite3.Connection, dataset_id: str
) -> dict[tuple[str, str], tuple[str, str]]:
    return {
        (row["store_site"], row["msku"]): (row["current_store"], row["current_msku"])
        for row in connection.execute(
            "SELECT * FROM product_identity_aliases WHERE dataset_id = ?", (dataset_id,)
        )
    }
