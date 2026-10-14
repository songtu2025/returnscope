"""Listing 回收站使用独立的记录生命周期，不改写历史执行结论。"""

import hashlib
import sqlite3

from web_backend.database_sql_migrations import (
    RegisteredSqlMigration,
    apply_sql_migration,
)


def migrate_segment_recycle(connection: sqlite3.Connection) -> None:
    sql = """
    ALTER TABLE task_segments ADD COLUMN removal_requested_at TEXT;
    ALTER TABLE task_segments ADD COLUMN deleted_by TEXT REFERENCES users(id);
    ALTER TABLE task_segments ADD COLUMN purged_at TEXT;
    CREATE INDEX idx_task_segments_recycle ON task_segments(deleted_at, purged_at);
    """
    apply_sql_migration(
        connection,
        RegisteredSqlMigration(
            "20261014_listing_recycle",
            hashlib.sha256(sql.encode()).hexdigest(),
            sql,
        ),
        savepoint="listing_recycle",
        checksum_error="Listing 回收站迁移校验失败",
    )
