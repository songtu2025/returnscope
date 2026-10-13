from __future__ import annotations

import hashlib
import sqlite3

from web_backend.classification_unit_semantics import migrate_unit_semantics
from web_backend.database_column_migrations import (
    migrate_api_config_version_columns,
    migrate_classification_result_columns,
    migrate_dataset_columns,
    migrate_result_version_columns,
    migrate_task_columns,
    migrate_task_segment_columns,
    migrate_user_columns,
    migrate_validation_run_columns,
)
from web_backend.database_history_repairs import (
    migrate_ai_insight_reports,
    repair_draft_review_batches,
)
from web_backend.database_history_repairs import (
    repair_missing_empty_checkpoint_references as repair_empty_checkpoints,
)
from web_backend.database_registered_migrations import (
    AUTH_ACTION_TOKEN_MIGRATION as AUTH_ACTION_TOKEN_MIGRATION,
)
from web_backend.database_registered_migrations import (
    AUTH_ACTION_TOKEN_MIGRATION_CHECKSUM as AUTH_ACTION_TOKEN_MIGRATION_CHECKSUM,
)
from web_backend.database_registered_migrations import (
    AUTH_ACTION_TOKEN_MIGRATION_SQL as AUTH_ACTION_TOKEN_MIGRATION_SQL,
)
from web_backend.database_registered_migrations import (
    EMAIL_CHANGE_TOKEN_MIGRATION as EMAIL_CHANGE_TOKEN_MIGRATION,
)
from web_backend.database_registered_migrations import (
    EMAIL_CHANGE_TOKEN_MIGRATION_CHECKSUM as EMAIL_CHANGE_TOKEN_MIGRATION_CHECKSUM,
)
from web_backend.database_registered_migrations import (
    EMAIL_CHANGE_TOKEN_MIGRATION_SQL as EMAIL_CHANGE_TOKEN_MIGRATION_SQL,
)
from web_backend.database_registered_migrations import (
    RESULT_SOURCE_ORIGIN_MIGRATION as RESULT_SOURCE_ORIGIN_MIGRATION,
)
from web_backend.database_registered_migrations import (
    RESULT_SOURCE_ORIGIN_MIGRATION_CHECKSUM as RESULT_SOURCE_ORIGIN_MIGRATION_CHECKSUM,
)
from web_backend.database_registered_migrations import (
    migrate_auth_action_tokens,
    migrate_delivery_lifecycle,
    migrate_email_change_tokens,
    migrate_result_source_origin,
    migrate_segment_removal,
    require_result_source_origin,
)
from web_backend.database_schema import SCHEMA
from web_backend.database_table_rebuilds import DatabaseTableRebuilds
from web_backend.datasets.product_aliases import migrate_product_aliases

CLASSIFICATION_UNIT_RERUN_MIGRATION = "20260919_classification_unit_rerun_state"
CLASSIFICATION_UNIT_RERUN_MIGRATION_CHECKSUM = hashlib.sha256(
    b"classification_units.system_rerun_required:v1"
).hexdigest()


def _backfill_classification_unit_rerun_state(
    connection: sqlite3.Connection,
) -> None:
    from return_semantics.semantic_review import requires_system_rerun
    from web_backend.common import json_value

    rows = connection.execute(
        """
        SELECT id, classification_json, processing_status, comment
        FROM classification_units
        """
    ).fetchall()
    connection.executemany(
        """
        UPDATE classification_units
        SET system_rerun_required = ?
        WHERE id = ?
        """,
        (
            (
                int(
                    requires_system_rerun(
                        json_value(row["classification_json"], {}),
                        str(row["comment"] or ""),
                        processing_status=str(row["processing_status"] or ""),
                    )
                ),
                row["id"],
            )
            for row in rows
        ),
    )


def _apply_classification_unit_rerun_migration(
    connection: sqlite3.Connection,
) -> None:
    columns = {
        row["name"]
        for row in connection.execute(
            "PRAGMA table_info(classification_units)"
        ).fetchall()
    }
    if "system_rerun_required" not in columns:
        connection.execute(
            """
            ALTER TABLE classification_units
            ADD COLUMN system_rerun_required INTEGER NOT NULL DEFAULT 0
            CHECK(system_rerun_required IN (0, 1))
            """
        )
    _backfill_classification_unit_rerun_state(connection)
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_classification_units_system_rerun
        ON classification_units(result_version_id, system_rerun_required)
        """
    )


def repair_missing_empty_checkpoint_references(
    connection: sqlite3.Connection,
) -> int:
    return repair_empty_checkpoints(connection)


class DatabaseMigrations(DatabaseTableRebuilds):
    def apply_startup_migrations(
        self,
        connection: sqlite3.Connection,
        *,
        migrate_result_source_origin: bool,
    ) -> None:
        """开启事务，按既有顺序更新结构和历史数据，由调用方结束事务。"""
        connection.executescript("BEGIN IMMEDIATE;\n" + SCHEMA)
        migrate_product_aliases(connection)
        self._migrate_auth_action_tokens(connection)
        self._migrate_email_change_tokens(connection)
        self._migrate_user_columns(connection)
        self._migrate_dataset_columns(connection)
        self._migrate_api_config_version_columns(connection)
        self._migrate_task_segment_columns(connection)
        migrate_segment_removal(connection)
        migrate_delivery_lifecycle(connection)
        repair_missing_empty_checkpoint_references(connection)
        self._migrate_result_version_columns(connection)
        self._migrate_classification_result_columns(connection)
        self._migrate_validation_run_columns(connection)
        self._migrate_review_records(connection)
        self._repair_draft_review_batches(connection)
        self._migrate_excluded_quality_status(connection)
        self._migrate_classification_unit_rerun_state(connection)
        migrate_unit_semantics(connection)
        if migrate_result_source_origin:
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

    @staticmethod
    def _migrate_auth_action_tokens(connection: sqlite3.Connection) -> None:
        migrate_auth_action_tokens(connection)

    @staticmethod
    def _migrate_email_change_tokens(connection: sqlite3.Connection) -> None:
        migrate_email_change_tokens(connection)

    @staticmethod
    def _migrate_user_columns(connection: sqlite3.Connection) -> None:
        migrate_user_columns(connection)

    @staticmethod
    def _migrate_dataset_columns(connection: sqlite3.Connection) -> None:
        migrate_dataset_columns(connection)

    @staticmethod
    def _migrate_api_config_version_columns(
        connection: sqlite3.Connection,
    ) -> None:
        migrate_api_config_version_columns(connection)

    @staticmethod
    def _migrate_task_segment_columns(connection: sqlite3.Connection) -> None:
        migrate_task_segment_columns(connection)

    @staticmethod
    def _migrate_result_version_columns(connection: sqlite3.Connection) -> None:
        migrate_result_version_columns(connection)

    @staticmethod
    def _migrate_classification_result_columns(
        connection: sqlite3.Connection,
    ) -> None:
        migrate_classification_result_columns(connection)

    @staticmethod
    def _migrate_validation_run_columns(
        connection: sqlite3.Connection,
    ) -> None:
        migrate_validation_run_columns(connection)

    @staticmethod
    def _migrate_task_columns(connection: sqlite3.Connection) -> None:
        migrate_task_columns(connection)

    @staticmethod
    def _migrate_ai_insight_reports(connection: sqlite3.Connection) -> None:
        migrate_ai_insight_reports(connection)

    @staticmethod
    def _repair_draft_review_batches(connection: sqlite3.Connection) -> None:
        repair_draft_review_batches(connection)

    @staticmethod
    def _migrate_classification_unit_rerun_state(
        connection: sqlite3.Connection,
    ) -> None:
        migration = connection.execute(
            """
            SELECT checksum FROM app_migrations
            WHERE migration_id = ?
            """,
            (CLASSIFICATION_UNIT_RERUN_MIGRATION,),
        ).fetchone()
        if migration is not None:
            if migration["checksum"] != CLASSIFICATION_UNIT_RERUN_MIGRATION_CHECKSUM:
                raise RuntimeError("分类单元系统重跑迁移校验失败")
            return

        connection.execute("SAVEPOINT migrate_classification_unit_rerun_state")
        try:
            _apply_classification_unit_rerun_migration(connection)
            connection.execute(
                """
                INSERT INTO app_migrations(
                    migration_id, checksum, status, applied_at
                ) VALUES (?, ?, 'applied', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                """,
                (
                    CLASSIFICATION_UNIT_RERUN_MIGRATION,
                    CLASSIFICATION_UNIT_RERUN_MIGRATION_CHECKSUM,
                ),
            )
            connection.execute("RELEASE migrate_classification_unit_rerun_state")
        except Exception:
            connection.execute("ROLLBACK TO migrate_classification_unit_rerun_state")
            connection.execute("RELEASE migrate_classification_unit_rerun_state")
            raise

    @staticmethod
    def _require_result_source_origin(connection: sqlite3.Connection) -> None:
        require_result_source_origin(connection)

    @staticmethod
    def _migrate_result_source_origin(connection: sqlite3.Connection) -> None:
        migrate_result_source_origin(connection)
