from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from web_backend.database_migrations import (
    DatabaseMigrations,
    repair_missing_empty_checkpoint_references,
)
from web_backend.database_schema import SCHEMA


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
            connection.executescript(SCHEMA)
            self._migrate_auth_action_tokens(connection)
            self._migrate_email_change_tokens(connection)
            self._migrate_user_columns(connection)
            self._migrate_dataset_columns(connection)
            self._migrate_api_config_version_columns(connection)
            self._migrate_task_segment_columns(connection)
            repair_missing_empty_checkpoint_references(connection)
            self._migrate_result_version_columns(connection)
            self._migrate_classification_result_columns(connection)
            self._migrate_validation_run_columns(connection)
            self._migrate_review_records(connection)
            self._repair_draft_review_batches(connection)
            self._migrate_excluded_quality_status(connection)
            self._migrate_classification_unit_rerun_state(connection)
            if not require_result_source_origin or new_database:
                self._migrate_result_source_origin(connection)
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_review_records_batch
                ON review_records(batch_id, updated_at DESC, id)
                """
            )
            self._migrate_task_columns(connection)
            self._migrate_ai_insight_reports(connection)
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_task_segments_status_order
                ON task_segments(status, execution_order, created_at)
                """
            )
            self._recover_interrupted_result_publishing(connection)
            self._migrate_api_models(connection)
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
