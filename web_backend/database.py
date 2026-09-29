from __future__ import annotations

import sqlite3
from contextlib import closing, contextmanager
from functools import cache
from pathlib import Path
from typing import Iterator

from web_backend.database_migrations import DatabaseMigrations
from web_backend.database_recovery import (
    recover_interrupted_result_publishing,
    sync_api_models,
)


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


@cache
def _required_schema() -> tuple[dict[str, set[str]], set[str], dict[str, str]]:
    """从当前迁移结果生成生产数据库的只读校验基准。"""
    with closing(sqlite3.connect(":memory:")) as reference:
        reference.row_factory = sqlite3.Row
        reference.execute("PRAGMA foreign_keys = ON")
        DatabaseMigrations().apply_startup_migrations(
            reference, migrate_result_source_origin=True
        )
        tables = {
            row["name"]: {
                column["name"]
                for column in reference.execute(f'PRAGMA table_info("{row["name"]}")')
            }
            for row in reference.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        indexes = {
            row["name"]
            for row in reference.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index' "
                "AND name NOT LIKE 'sqlite_autoindex_%'"
            )
        }
        migrations = {
            row["migration_id"]: row["checksum"]
            for row in reference.execute(
                "SELECT migration_id, checksum FROM app_migrations"
            )
        }
        return tables, indexes, migrations


class Database(DatabaseMigrations):
    def __init__(self, path: Path) -> None:
        self.path = path

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path,
            timeout=30,
            isolation_level=None,
            factory=ClosingConnection,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def validate_production_schema(self) -> None:
        """生产启动前以只读连接检查结构和迁移记录。"""
        if not self.path.is_file():
            raise RuntimeError("生产数据库不存在，请先停服执行数据库升级")
        required_tables, required_indexes, required_migrations = _required_schema()
        with closing(
            sqlite3.connect(f"{self.path.resolve().as_uri()}?mode=ro", uri=True)
        ) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only = ON")
            actual_objects = {
                (row["type"], row["name"])
                for row in connection.execute(
                    "SELECT type, name FROM sqlite_master "
                    "WHERE type IN ('table', 'index')"
                )
            }
            for table, required_columns in required_tables.items():
                if ("table", table) not in actual_objects:
                    raise RuntimeError(
                        f"生产数据库缺少表 {table}，请停服执行数据库升级"
                    )
                actual_columns = {
                    row["name"]
                    for row in connection.execute(f'PRAGMA table_info("{table}")')
                }
                if missing := required_columns - actual_columns:
                    raise RuntimeError(
                        f"生产数据库表 {table} 缺少字段 {min(missing)}，"
                        "请停服执行数据库升级"
                    )
            for index in required_indexes:
                if ("index", index) not in actual_objects:
                    raise RuntimeError(
                        f"生产数据库缺少索引 {index}，请停服执行数据库升级"
                    )
            migrations = {
                row["migration_id"]: (row["checksum"], row["status"])
                for row in connection.execute(
                    "SELECT migration_id, checksum, status FROM app_migrations"
                )
            }
            for migration_id, checksum in required_migrations.items():
                if migrations.get(migration_id) != (checksum, "applied"):
                    raise RuntimeError(
                        f"生产数据库迁移记录 {migration_id} 缺失或校验失败，"
                        "请停服执行数据库升级"
                    )

    def upgrade_schema(self) -> None:
        """供停服升级命令复用既有迁移和历史模型同步。"""
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            self.apply_startup_migrations(connection, migrate_result_source_origin=True)
            sync_api_models(connection)
            connection.execute("PRAGMA optimize")

    def initialize(self, *, production: bool = False) -> None:
        if production:
            self.validate_production_schema()
        else:
            self.upgrade_schema()
        with self.connect() as connection:
            recover_interrupted_result_publishing(connection)

    @contextmanager
    def transaction(self, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
