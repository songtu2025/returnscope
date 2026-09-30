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


def _table_columns(
    connection: sqlite3.Connection, table: str
) -> dict[str, tuple[str, int]]:
    return {
        row["name"]: (row["type"].upper(), row["pk"])
        for row in connection.execute(f'PRAGMA table_info("{table}")')
    }


def _index_keys(
    connection: sqlite3.Connection, index: str
) -> tuple[tuple[int, str | None, int, str | None], ...]:
    return tuple(
        (row["cid"], row["name"], row["desc"], row["coll"])
        for row in connection.execute(f'PRAGMA index_xinfo("{index}")')
        if row["key"]
    )


def _validate_table_columns(
    connection: sqlite3.Connection,
    table: str,
    required_columns: dict[str, tuple[str, int]],
) -> None:
    actual_columns = _table_columns(connection, table)
    if missing := required_columns.keys() - actual_columns.keys():
        raise RuntimeError(
            f"生产数据库表 {table} 缺少字段 {min(missing)}，请停服执行数据库升级"
        )
    for column, definition in required_columns.items():
        if actual_columns[column] != definition:
            raise RuntimeError(
                f"生产数据库表 {table} 字段 {column} 定义不一致，请停服检查数据库结构"
            )


@cache
def _required_schema() -> tuple[
    dict[str, dict[str, tuple[str, int]]],
    dict[str, tuple[tuple[int, str | None, int, str | None], ...]],
    dict[str, str],
]:
    """从当前迁移结果生成生产数据库的只读校验基准。"""
    with closing(sqlite3.connect(":memory:")) as reference:
        reference.row_factory = sqlite3.Row
        reference.execute("PRAGMA foreign_keys = ON")
        DatabaseMigrations().apply_startup_migrations(
            reference, migrate_result_source_origin=True
        )
        tables = {
            row["name"]: _table_columns(reference, row["name"])
            for row in reference.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        indexes = {
            row["name"]: _index_keys(reference, row["name"])
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
                _validate_table_columns(connection, table, required_columns)
            for index, required_keys in required_indexes.items():
                if ("index", index) not in actual_objects:
                    raise RuntimeError(
                        f"生产数据库缺少索引 {index}，请停服执行数据库升级"
                    )
                if _index_keys(connection, index) != required_keys:
                    raise RuntimeError(
                        f"生产数据库索引 {index} 定义不一致，请停服检查数据库结构"
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
            # 表重建需要在事务开始前关闭外键，提交前统一检查。
            connection.execute("PRAGMA foreign_keys = OFF")
            self.apply_startup_migrations(connection, migrate_result_source_origin=True)
            sync_api_models(connection)
            if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise RuntimeError("数据库外键完整性检查失败")
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
