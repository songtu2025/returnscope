from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from web_backend.classification_result_queries import system_rerun_counts
from web_backend.database import Database
from web_backend.database_migrations import (
    AUTH_ACTION_TOKEN_MIGRATION_SQL,
    CLASSIFICATION_UNIT_RERUN_MIGRATION,
    CLASSIFICATION_UNIT_RERUN_MIGRATION_CHECKSUM,
    RESULT_SOURCE_ORIGIN_MIGRATION,
    RESULT_SOURCE_ORIGIN_MIGRATION_CHECKSUM,
)


def test_result_source_origin_migration_keeps_existing_rows(tmp_path: Path) -> None:
    connection = sqlite3.connect(tmp_path / "legacy-origin.db")
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE app_migrations (
            migration_id TEXT PRIMARY KEY,
            checksum TEXT NOT NULL,
            status TEXT NOT NULL,
            applied_at TEXT NOT NULL
        );
        CREATE TABLE classification_result_records (
            id TEXT PRIMARY KEY,
            source_record_id TEXT NOT NULL
        );
        INSERT INTO classification_result_records(id, source_record_id)
        VALUES ('record-1', 'version:2');
        """
    )
    Database._migrate_result_source_origin(connection)
    Database._migrate_result_source_origin(connection)
    record = connection.execute(
        "SELECT source_record_id, source_origin_id "
        "FROM classification_result_records WHERE id = 'record-1'"
    ).fetchone()
    migration = connection.execute(
        "SELECT checksum FROM app_migrations WHERE migration_id = ?",
        (RESULT_SOURCE_ORIGIN_MIGRATION,),
    ).fetchone()
    assert tuple(record) == ("version:2", None)
    assert migration["checksum"] == RESULT_SOURCE_ORIGIN_MIGRATION_CHECKSUM
    connection.close()


@pytest.mark.parametrize("kind", ["auth", "email"])
@pytest.mark.parametrize(
    "failure_statement", ["CREATE TABLE", "INSERT INTO app_migrations", "RELEASE"]
)
@pytest.mark.parametrize("outer_transaction", [False, True])
def test_token_migration_failure_preserves_schema_rows_and_transaction(
    kind: str, failure_statement: str, outer_transaction: bool
) -> None:
    class FailingConnection(sqlite3.Connection):
        failed = False

        def execute(self, sql, parameters=()):
            if " ".join(sql.split()).startswith(failure_statement) and not self.failed:
                self.failed = True
                raise RuntimeError("合成迁移故障")
            return super().execute(sql, parameters)

    connection = sqlite3.connect(":memory:", factory=FailingConnection)
    connection.row_factory = sqlite3.Row
    try:
        connection.executescript(
            """
            CREATE TABLE users(id TEXT PRIMARY KEY);
            CREATE TABLE app_migrations(
                migration_id TEXT PRIMARY KEY, checksum TEXT NOT NULL,
                status TEXT NOT NULL, applied_at TEXT NOT NULL
            );
            """
        )
        if kind == "email":
            connection.executescript(AUTH_ACTION_TOKEN_MIGRATION_SQL)
            connection.execute(
                """
                INSERT INTO auth_action_tokens(
                    id, email, purpose, token_hash, expires_at, created_at
                ) VALUES (
                    'synthetic-token', 'qa@example.invalid', 'invitation',
                    'synthetic-hash', '2099-01-01', '2000-01-01'
                );
                """
            )
        connection.commit()
        if outer_transaction:
            connection.execute("BEGIN")
        before_schema = connection.execute(
            "SELECT name, sql FROM sqlite_master ORDER BY name"
        ).fetchall()
        before_tokens = (
            connection.execute("SELECT * FROM auth_action_tokens").fetchall()
            if kind == "email"
            else []
        )
        migration = (
            Database._migrate_auth_action_tokens
            if kind == "auth"
            else Database._migrate_email_change_tokens
        )

        with pytest.raises(RuntimeError, match="合成迁移故障"):
            migration(connection)

        assert connection.failed
        assert (
            connection.execute(
                "SELECT name, sql FROM sqlite_master ORDER BY name"
            ).fetchall()
            == before_schema
        )
        assert connection.execute("SELECT * FROM app_migrations").fetchall() == []
        assert connection.in_transaction is outer_transaction
        if kind == "email":
            assert (
                connection.execute("SELECT * FROM auth_action_tokens").fetchall()
                == before_tokens
            )
    finally:
        connection.close()


def test_classification_unit_rerun_migration_backfills_and_indexes(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "legacy.db"
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE app_migrations (
            migration_id TEXT PRIMARY KEY,
            checksum TEXT NOT NULL,
            status TEXT NOT NULL,
            applied_at TEXT NOT NULL
        );
        CREATE TABLE classification_units (
            id TEXT PRIMARY KEY,
            result_version_id TEXT NOT NULL,
            classification_json TEXT NOT NULL,
            processing_status TEXT NOT NULL,
            comment TEXT
        );
        """
    )
    system_failure = {
        "status": "MANUAL_REVIEW",
        "review_diagnostics": [
            {
                "code": "SECONDARY_MODEL_TIMEOUT",
                "detail": "请求超时",
                "action": "SYSTEM_RERUN",
            }
        ],
    }
    connection.executemany(
        """
        INSERT INTO classification_units(
            id, result_version_id, classification_json,
            processing_status, comment
        ) VALUES (?, 'version-1', ?, ?, ?)
        """,
        (
            (
                "unit-rerun",
                json.dumps(system_failure, ensure_ascii=False),
                "MANUAL_REVIEW",
                "could be either",
            ),
            ("unit-ready", "{}", "AUTO_APPROVED", "Too small"),
        ),
    )

    Database._migrate_classification_unit_rerun_state(connection)

    columns = {
        row["name"]
        for row in connection.execute(
            "PRAGMA table_info(classification_units)"
        ).fetchall()
    }
    states = connection.execute(
        """
        SELECT id, system_rerun_required
        FROM classification_units
        ORDER BY id
        """
    ).fetchall()
    indexes = {
        row["name"]
        for row in connection.execute(
            "PRAGMA index_list(classification_units)"
        ).fetchall()
    }
    migration = connection.execute(
        """
        SELECT checksum, status FROM app_migrations
        WHERE migration_id = ?
        """,
        (CLASSIFICATION_UNIT_RERUN_MIGRATION,),
    ).fetchone()

    assert "system_rerun_required" in columns
    assert [(row["id"], row["system_rerun_required"]) for row in states] == [
        ("unit-ready", 0),
        ("unit-rerun", 1),
    ]
    assert "idx_classification_units_system_rerun" in indexes
    assert migration is not None
    assert migration["checksum"] == CLASSIFICATION_UNIT_RERUN_MIGRATION_CHECKSUM
    assert migration["status"] == "applied"
    connection.execute(
        """
        UPDATE classification_units
        SET classification_json = 'invalid-json'
        WHERE id = 'unit-rerun'
        """
    )
    assert system_rerun_counts(connection, ["version-1"]) == {"version-1": 1}

    Database._migrate_classification_unit_rerun_state(connection)
    connection.close()
