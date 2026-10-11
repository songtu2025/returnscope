from __future__ import annotations

import hashlib
import sqlite3

from web_backend.database_sql_migrations import (
    RegisteredSqlMigration,
    apply_sql_migration,
)

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


def migrate_auth_action_tokens(connection: sqlite3.Connection) -> None:
    apply_sql_migration(
        connection,
        RegisteredSqlMigration(
            AUTH_ACTION_TOKEN_MIGRATION,
            AUTH_ACTION_TOKEN_MIGRATION_CHECKSUM,
            AUTH_ACTION_TOKEN_MIGRATION_SQL,
        ),
        savepoint="migrate_auth_action_tokens",
        checksum_error="身份操作令牌迁移校验失败",
    )


def migrate_email_change_tokens(connection: sqlite3.Connection) -> None:
    apply_sql_migration(
        connection,
        RegisteredSqlMigration(
            EMAIL_CHANGE_TOKEN_MIGRATION,
            EMAIL_CHANGE_TOKEN_MIGRATION_CHECKSUM,
            EMAIL_CHANGE_TOKEN_MIGRATION_SQL,
        ),
        savepoint="migrate_email_change_tokens",
        checksum_error="邮箱变更令牌迁移校验失败",
    )


def require_result_source_origin(connection: sqlite3.Connection) -> None:
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


def migrate_result_source_origin(connection: sqlite3.Connection) -> None:
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
