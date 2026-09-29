from __future__ import annotations

import sqlite3
from contextlib import contextmanager
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

    def initialize(self, *, require_result_source_origin: bool = False) -> None:
        new_database = not self.path.exists()
        with self.connect() as connection:
            if require_result_source_origin and not new_database:
                self._require_result_source_origin(connection)
            connection.execute("PRAGMA journal_mode = WAL")
            self.apply_startup_migrations(
                connection,
                migrate_result_source_origin=(
                    not require_result_source_origin or new_database
                ),
            )
            recover_interrupted_result_publishing(connection)
            sync_api_models(connection)
            connection.execute("PRAGMA optimize")

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
