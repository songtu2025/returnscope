from __future__ import annotations

import hashlib
import secrets
import sqlite3
from pathlib import Path

from web_backend.database_table_rebuilds import DatabaseTableRebuilds

CLASSIFICATION_UNIT_RERUN_MIGRATION = "20260919_classification_unit_rerun_state"
CLASSIFICATION_UNIT_RERUN_MIGRATION_CHECKSUM = hashlib.sha256(
    b"classification_units.system_rerun_required:v1"
).hexdigest()
RESULT_SOURCE_ORIGIN_MIGRATION = "20260921_result_source_origin"
RESULT_SOURCE_ORIGIN_MIGRATION_CHECKSUM = hashlib.sha256(
    b"classification_result_records.source_origin_id:TEXT:v1"
).hexdigest()
AUTH_ACTION_TOKEN_MIGRATION = "20260920_auth_action_tokens"
AUTH_ACTION_TOKEN_MIGRATION_SQL = """
CREATE TABLE IF NOT EXISTS auth_action_tokens (
    id TEXT PRIMARY KEY,
    user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    purpose TEXT NOT NULL CHECK(purpose IN ('invitation', 'password_reset')),
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    revoked_at TEXT,
    created_by TEXT REFERENCES users(id),
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_auth_action_tokens_email_purpose
ON auth_action_tokens(email, purpose, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_auth_action_tokens_user_purpose
ON auth_action_tokens(user_id, purpose, created_at DESC);
"""
AUTH_ACTION_TOKEN_MIGRATION_CHECKSUM = hashlib.sha256(
    AUTH_ACTION_TOKEN_MIGRATION_SQL.encode("utf-8")
).hexdigest()
EMAIL_CHANGE_TOKEN_MIGRATION = "20260920_email_change_tokens"
EMAIL_CHANGE_TOKEN_MIGRATION_SQL = """
ALTER TABLE auth_action_tokens RENAME TO auth_action_tokens_v1;
CREATE TABLE auth_action_tokens (
    id TEXT PRIMARY KEY,
    user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    purpose TEXT NOT NULL
        CHECK(purpose IN ('invitation', 'password_reset', 'email_change')),
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    revoked_at TEXT,
    created_by TEXT REFERENCES users(id),
    created_at TEXT NOT NULL
);
INSERT INTO auth_action_tokens(
    id, user_id, email, purpose, token_hash, expires_at,
    used_at, revoked_at, created_by, created_at
)
SELECT
    id, user_id, email, purpose, token_hash, expires_at,
    used_at, revoked_at, created_by, created_at
FROM auth_action_tokens_v1;
DROP TABLE auth_action_tokens_v1;
CREATE INDEX idx_auth_action_tokens_email_purpose
ON auth_action_tokens(email, purpose, created_at DESC);
CREATE INDEX idx_auth_action_tokens_user_purpose
ON auth_action_tokens(user_id, purpose, created_at DESC);
"""
EMAIL_CHANGE_TOKEN_MIGRATION_CHECKSUM = hashlib.sha256(
    EMAIL_CHANGE_TOKEN_MIGRATION_SQL.encode("utf-8")
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
    """清理从未产生结果且检查点文件不存在的历史路径。"""
    rows = connection.execute(
        """
        SELECT id, result_json_path
        FROM task_segments
        WHERE result_json_path IS NOT NULL
          AND TRIM(result_json_path) <> ''
          AND result_version = 0
          AND progress_current = 0
          AND model_calls = 0
          AND cache_hits = 0
          AND model_failures = 0
          AND result_publish_status IS NULL
          AND status IN ('cancelled', 'paused', 'failed', 'retry_pending')
        """
    ).fetchall()
    stale_ids = [
        str(row["id"])
        for row in rows
        if not Path(str(row["result_json_path"])).is_file()
    ]
    if stale_ids:
        connection.executemany(
            "UPDATE task_segments SET result_json_path = NULL WHERE id = ?",
            ((segment_id,) for segment_id in stale_ids),
        )
    return len(stale_ids)


class DatabaseMigrations(DatabaseTableRebuilds):
    @staticmethod
    def _migrate_auth_action_tokens(connection: sqlite3.Connection) -> None:
        migration = connection.execute(
            "SELECT checksum FROM app_migrations WHERE migration_id = ?",
            (AUTH_ACTION_TOKEN_MIGRATION,),
        ).fetchone()
        if migration is not None:
            if migration["checksum"] != AUTH_ACTION_TOKEN_MIGRATION_CHECKSUM:
                raise RuntimeError("身份操作令牌迁移校验失败")
            return

        connection.execute("SAVEPOINT migrate_auth_action_tokens")
        try:
            for statement in AUTH_ACTION_TOKEN_MIGRATION_SQL.split(";"):
                if statement.strip():
                    connection.execute(statement)
            connection.execute(
                """
                INSERT INTO app_migrations(
                    migration_id, checksum, status, applied_at
                ) VALUES (?, ?, 'applied', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                """,
                (
                    AUTH_ACTION_TOKEN_MIGRATION,
                    AUTH_ACTION_TOKEN_MIGRATION_CHECKSUM,
                ),
            )
            connection.execute("RELEASE migrate_auth_action_tokens")
        except Exception:
            connection.execute("ROLLBACK TO migrate_auth_action_tokens")
            connection.execute("RELEASE migrate_auth_action_tokens")
            raise

    @staticmethod
    def _migrate_email_change_tokens(connection: sqlite3.Connection) -> None:
        migration = connection.execute(
            "SELECT checksum FROM app_migrations WHERE migration_id = ?",
            (EMAIL_CHANGE_TOKEN_MIGRATION,),
        ).fetchone()
        if migration is not None:
            if migration["checksum"] != EMAIL_CHANGE_TOKEN_MIGRATION_CHECKSUM:
                raise RuntimeError("邮箱变更令牌迁移校验失败")
            return

        connection.execute("SAVEPOINT migrate_email_change_tokens")
        try:
            for statement in EMAIL_CHANGE_TOKEN_MIGRATION_SQL.split(";"):
                if statement.strip():
                    connection.execute(statement)
            connection.execute(
                """
                INSERT INTO app_migrations(
                    migration_id, checksum, status, applied_at
                ) VALUES (?, ?, 'applied', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                """,
                (
                    EMAIL_CHANGE_TOKEN_MIGRATION,
                    EMAIL_CHANGE_TOKEN_MIGRATION_CHECKSUM,
                ),
            )
            connection.execute("RELEASE migrate_email_change_tokens")
        except Exception:
            connection.execute("ROLLBACK TO migrate_email_change_tokens")
            connection.execute("RELEASE migrate_email_change_tokens")
            raise

    @staticmethod
    def _migrate_user_columns(connection: sqlite3.Connection) -> None:
        user_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(users)").fetchall()
        }
        if "is_admin" not in user_columns:
            connection.execute(
                "ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0"
            )

    @staticmethod
    def _migrate_dataset_columns(connection: sqlite3.Connection) -> None:
        dataset_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(datasets)").fetchall()
        }
        dataset_column_definitions = {
            "source_key": "TEXT",
            "usage_scope": "TEXT NOT NULL DEFAULT 'managed'",
        }
        for column_name, definition in dataset_column_definitions.items():
            if column_name not in dataset_columns:
                connection.execute(
                    f"ALTER TABLE datasets ADD COLUMN {column_name} {definition}"
                )

    @staticmethod
    def _migrate_api_config_version_columns(
        connection: sqlite3.Connection,
    ) -> None:
        config_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(api_config_versions)"
            ).fetchall()
        }
        if "change_note" not in config_columns:
            connection.execute(
                """
                ALTER TABLE api_config_versions
                ADD COLUMN change_note TEXT NOT NULL DEFAULT ''
                """
            )

    @staticmethod
    def _migrate_task_segment_columns(connection: sqlite3.Connection) -> None:
        segment_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(task_segments)").fetchall()
        }
        if "classification_keys_json" not in segment_columns:
            connection.execute(
                """
                ALTER TABLE task_segments
                ADD COLUMN classification_keys_json TEXT NOT NULL DEFAULT '[]'
                """
            )
        if "execution_order" not in segment_columns:
            connection.execute(
                """
                ALTER TABLE task_segments
                ADD COLUMN execution_order INTEGER NOT NULL DEFAULT 0
                """
            )
            rows = connection.execute(
                """
                SELECT id, task_id FROM task_segments
                ORDER BY task_id, created_at, segment_key
                """
            ).fetchall()
            task_positions: dict[str, int] = {}
            for row in rows:
                task_id = str(row["task_id"])
                position = task_positions.get(task_id, 0) + 1
                task_positions[task_id] = position
                connection.execute(
                    "UPDATE task_segments SET execution_order = ? WHERE id = ?",
                    (position, row["id"]),
                )
        for column_name in (
            "model_policy_version",
            "model_policy_json",
            "claims_version",
            "scope_json",
        ):
            if column_name not in segment_columns:
                connection.execute(
                    f"ALTER TABLE task_segments ADD COLUMN {column_name} TEXT"
                )
        if "standard_version_id" not in segment_columns:
            connection.execute(
                "ALTER TABLE task_segments ADD COLUMN standard_version_id TEXT"
            )
        segment_column_definitions = {
            "requested_action": "TEXT",
            "revision": "INTEGER NOT NULL DEFAULT 1",
            "retry_count": "INTEGER NOT NULL DEFAULT 0",
            "model_failures": "INTEGER NOT NULL DEFAULT 0",
            "heartbeat_at": "TEXT",
            "result_file_path": "TEXT",
            "result_json_path": "TEXT",
            "result_version": "INTEGER NOT NULL DEFAULT 0",
            "result_version_id": "TEXT",
            "result_publish_status": "TEXT",
            "result_quality_status": "TEXT",
            "result_published_at": "TEXT",
            "result_publish_error": "TEXT",
        }
        for column_name, definition in segment_column_definitions.items():
            if column_name not in segment_columns:
                connection.execute(
                    f"ALTER TABLE task_segments ADD COLUMN {column_name} {definition}"
                )

    @staticmethod
    def _migrate_result_version_columns(connection: sqlite3.Connection) -> None:
        version_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(classification_result_versions)"
            ).fetchall()
        }
        version_column_definitions = {
            "parent_version_id": "TEXT REFERENCES classification_result_versions(id)",
            "version_reason": "TEXT NOT NULL DEFAULT ''",
            "created_by": "TEXT REFERENCES users(id)",
        }
        for column_name, definition in version_column_definitions.items():
            if column_name not in version_columns:
                connection.execute(
                    "ALTER TABLE classification_result_versions "
                    f"ADD COLUMN {column_name} {definition}"
                )

    @staticmethod
    def _migrate_classification_result_columns(
        connection: sqlite3.Connection,
    ) -> None:
        result_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(classification_results)"
            ).fetchall()
        }
        if "standard_version_id" not in result_columns:
            connection.execute(
                "ALTER TABLE classification_results ADD COLUMN standard_version_id TEXT"
            )

    @staticmethod
    def _migrate_validation_run_columns(
        connection: sqlite3.Connection,
    ) -> None:
        validation_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(classification_standard_validation_runs)"
            ).fetchall()
        }
        validation_column_definitions = {
            "approved_by": "TEXT REFERENCES users(id)",
            "approved_at": "TEXT",
            "approval_note": "TEXT NOT NULL DEFAULT ''",
        }
        for column_name, definition in validation_column_definitions.items():
            if column_name not in validation_columns:
                connection.execute(
                    "ALTER TABLE classification_standard_validation_runs "
                    f"ADD COLUMN {column_name} {definition}"
                )

    @staticmethod
    def _migrate_task_columns(connection: sqlite3.Connection) -> None:
        task_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(tasks)").fetchall()
        }
        task_column_definitions = {
            "pause_requested": "INTEGER NOT NULL DEFAULT 0",
            "max_parallel_segments": "INTEGER NOT NULL DEFAULT 3",
            "last_scheduled_at": "TEXT",
            "archived_at": "TEXT",
            "archived_by": "TEXT REFERENCES users(id)",
        }
        for column_name, definition in task_column_definitions.items():
            if column_name not in task_columns:
                connection.execute(
                    f"ALTER TABLE tasks ADD COLUMN {column_name} {definition}"
                )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_tasks_archive_created
            ON tasks(archived_at, created_at DESC)
            """
        )

    @staticmethod
    def _recover_interrupted_result_publishing(
        connection: sqlite3.Connection,
    ) -> None:
        connection.execute(
            """
            UPDATE classification_result_versions
            SET publish_status = 'failed'
            WHERE publish_status = 'publishing'
            """
        )
        connection.execute(
            """
            UPDATE task_segments
            SET result_publish_status = 'failed',
                result_publish_error = COALESCE(
                    result_publish_error,
                    '服务重启时发现结果发布未完成，请重试发布'
                )
            WHERE result_publish_status = 'publishing'
              AND NOT EXISTS (
                  SELECT 1 FROM classification_result_versions v
                  WHERE v.source_segment_id = task_segments.id
                    AND v.publish_status = 'published'
              )
            """
        )

    @staticmethod
    def _migrate_api_models(connection: sqlite3.Connection) -> None:
        model_rows = connection.execute(
            """
            SELECT connection_id, primary_model AS model_key,
                   validation_status, validation_message, validated_at,
                   created_by, created_at
            FROM api_config_versions
            UNION ALL
            SELECT connection_id, cheap_model AS model_key,
                   validation_status, validation_message, validated_at,
                   created_by, created_at
            FROM api_config_versions
            WHERE cheap_model IS NOT NULL
            UNION ALL
            SELECT connection_id, secondary_model AS model_key,
                   validation_status, validation_message, validated_at,
                   created_by, created_at
            FROM api_config_versions
            WHERE secondary_model IS NOT NULL
            ORDER BY created_at
            """
        ).fetchall()
        for row in model_rows:
            model_id = f"model_{secrets.token_hex(8)}"
            connection.execute(
                """
                INSERT INTO api_models(
                    id, connection_id, model_key, display_name,
                    supported_efforts_json, active, validation_status,
                    validation_message, validated_at, created_by,
                    created_at, updated_by, updated_at
                ) VALUES (?, ?, ?, ?, '["low","medium","high"]', 1,
                          ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(connection_id, model_key) DO UPDATE SET
                    validation_status = CASE
                        WHEN excluded.validation_status = 'validated'
                        THEN 'validated'
                        ELSE api_models.validation_status
                    END,
                    validation_message = CASE
                        WHEN excluded.validation_status = 'validated'
                        THEN excluded.validation_message
                        ELSE api_models.validation_message
                    END,
                    validated_at = CASE
                        WHEN excluded.validation_status = 'validated'
                        THEN excluded.validated_at
                        ELSE api_models.validated_at
                    END
                """,
                (
                    model_id,
                    row["connection_id"],
                    row["model_key"],
                    row["model_key"],
                    row["validation_status"],
                    row["validation_message"],
                    row["validated_at"],
                    row["created_by"],
                    row["created_at"],
                    row["created_by"],
                    row["created_at"],
                ),
            )

    @staticmethod
    def _migrate_ai_insight_reports(connection: sqlite3.Connection) -> None:
        columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(ai_insight_reports)"
            ).fetchall()
        }
        definitions = {
            "stage": "TEXT NOT NULL DEFAULT 'queued'",
            "technical_error": "TEXT",
            "parent_job_id": "TEXT REFERENCES ai_insight_reports(id)",
        }
        for column_name, definition in definitions.items():
            if column_name not in columns:
                connection.execute(
                    f"ALTER TABLE ai_insight_reports "
                    f"ADD COLUMN {column_name} {definition}"
                )
        connection.execute(
            """
            UPDATE ai_insight_reports
            SET stage = CASE status
                WHEN 'queued' THEN 'queued'
                WHEN 'running' THEN 'preparing_evidence'
                WHEN 'completed' THEN 'completed'
                WHEN 'failed' THEN 'failed'
                ELSE stage
            END
            WHERE stage IS NULL OR stage = ''
               OR (stage = 'queued' AND status != 'queued')
            """
        )
        connection.execute(
            """
            UPDATE ai_insight_reports
            SET technical_error = COALESCE(technical_error, error),
                error = '报告生成未完成，请稍后重试。失败尝试已保留，且不会占用报告版本号。'
            WHERE status = 'failed'
              AND error IS NOT NULL
              AND error != '报告生成未完成，请稍后重试。失败尝试已保留，且不会占用报告版本号。'
            """
        )
        completed_rows = connection.execute(
            """
            SELECT report.id, report.dashboard_id,
                   report.dashboard_version_id, report.completed_at,
                   report.created_at
            FROM ai_insight_reports report
            LEFT JOIN ai_insight_report_versions version
              ON version.job_id = report.id
            WHERE report.status = 'completed' AND version.id IS NULL
            ORDER BY report.dashboard_id,
                     COALESCE(report.completed_at, report.created_at),
                     report.id
            """
        ).fetchall()
        next_versions: dict[str, int] = {}
        for row in completed_rows:
            dashboard_id = str(row["dashboard_id"])
            if dashboard_id not in next_versions:
                next_versions[dashboard_id] = int(
                    connection.execute(
                        """
                        SELECT COALESCE(MAX(version_no), 0) + 1
                        FROM ai_insight_report_versions
                        WHERE dashboard_id = ?
                        """,
                        (dashboard_id,),
                    ).fetchone()[0]
                )
            version_no = next_versions[dashboard_id]
            next_versions[dashboard_id] += 1
            connection.execute(
                """
                INSERT INTO ai_insight_report_versions(
                    id, job_id, dashboard_id, dashboard_version_id,
                    version_no, published_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    f"insight_report_version_{secrets.token_hex(8)}",
                    row["id"],
                    dashboard_id,
                    row["dashboard_version_id"],
                    version_no,
                    row["completed_at"] or row["created_at"],
                ),
            )

    @staticmethod
    def _repair_draft_review_batches(connection: sqlite3.Connection) -> None:
        missing_records = connection.execute(
            """
            SELECT b.id AS batch_id, b.base_result_version_id,
                   b.updated_at, result.source_task_id,
                   unit.classification_key, unit.comment,
                   unit.classification_json
            FROM review_batches b
            JOIN classification_results result ON result.id = b.result_id
            JOIN classification_units unit
              ON unit.result_version_id = b.base_result_version_id
            LEFT JOIN review_records review
              ON review.batch_id = b.id
             AND review.classification_key = unit.classification_key
            WHERE b.status = 'draft'
              AND unit.quality_status != 'ready'
              AND review.id IS NULL
            ORDER BY b.id, unit.classification_key
            """
        ).fetchall()
        if not missing_records:
            return
        connection.executemany(
            """
            INSERT INTO review_records(
                id, task_id, batch_id, base_result_version_id,
                classification_key, comment, workflow_status,
                classification_json, revision, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, 1, ?)
            """,
            [
                (
                    f"review_{secrets.token_hex(8)}",
                    row["source_task_id"],
                    row["batch_id"],
                    row["base_result_version_id"],
                    row["classification_key"],
                    str(row["comment"] or ""),
                    row["classification_json"],
                    row["updated_at"],
                )
                for row in missing_records
            ],
        )

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
        try:
            migration = connection.execute(
                "SELECT checksum FROM app_migrations WHERE migration_id = ?",
                (RESULT_SOURCE_ORIGIN_MIGRATION,),
            ).fetchone()
            columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(classification_result_records)"
                ).fetchall()
            }
        except sqlite3.OperationalError as exc:
            raise RuntimeError("生产数据库尚未完成源明细追溯迁移") from exc
        if (
            migration is None
            or migration["checksum"] != RESULT_SOURCE_ORIGIN_MIGRATION_CHECKSUM
            or "source_origin_id" not in columns
        ):
            raise RuntimeError("生产数据库尚未完成源明细追溯迁移")

    @staticmethod
    def _migrate_result_source_origin(connection: sqlite3.Connection) -> None:
        migration = connection.execute(
            "SELECT checksum FROM app_migrations WHERE migration_id = ?",
            (RESULT_SOURCE_ORIGIN_MIGRATION,),
        ).fetchone()
        if migration is not None:
            if migration["checksum"] != RESULT_SOURCE_ORIGIN_MIGRATION_CHECKSUM:
                raise RuntimeError("源明细追溯迁移校验失败")
            return
        connection.execute("SAVEPOINT migrate_result_source_origin")
        try:
            columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(classification_result_records)"
                ).fetchall()
            }
            if "source_origin_id" not in columns:
                connection.execute(
                    "ALTER TABLE classification_result_records "
                    "ADD COLUMN source_origin_id TEXT"
                )
            connection.execute(
                """
                INSERT INTO app_migrations(migration_id, checksum, status, applied_at)
                VALUES (?, ?, 'applied', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                """,
                (
                    RESULT_SOURCE_ORIGIN_MIGRATION,
                    RESULT_SOURCE_ORIGIN_MIGRATION_CHECKSUM,
                ),
            )
            connection.execute("RELEASE migrate_result_source_origin")
        except Exception:
            connection.execute("ROLLBACK TO migrate_result_source_origin")
            connection.execute("RELEASE migrate_result_source_origin")
            raise
