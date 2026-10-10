from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class RegisteredSqlMigration:
    migration_id: str
    checksum: str
    sql: str


def apply_sql_migration(
    connection: sqlite3.Connection,
    migration: RegisteredSqlMigration,
    *,
    savepoint: str,
    checksum_error: str,
) -> None:
    """按既有校验和与保存点执行迁移，由调用方结束外层事务。"""
    registered = connection.execute(
        "SELECT checksum FROM app_migrations WHERE migration_id = ?",
        (migration.migration_id,),
    ).fetchone()
    if registered is not None:
        if registered["checksum"] != migration.checksum:
            raise RuntimeError(checksum_error)
        return

    connection.execute(f"SAVEPOINT {savepoint}")
    try:
        for statement in migration.sql.split(";"):
            if statement.strip():
                connection.execute(statement)
        connection.execute(
            """
            INSERT INTO app_migrations(
                migration_id, checksum, status, applied_at
            ) VALUES (?, ?, 'applied', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            """,
            (migration.migration_id, migration.checksum),
        )
        connection.execute(f"RELEASE {savepoint}")
    except Exception:
        connection.execute(f"ROLLBACK TO {savepoint}")
        connection.execute(f"RELEASE {savepoint}")
        raise
