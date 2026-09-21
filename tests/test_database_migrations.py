from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from web_backend.backup import restore_backup
from web_backend.classification_result_queries import system_rerun_counts
from web_backend.database import (
    CLASSIFICATION_UNIT_RERUN_MIGRATION,
    CLASSIFICATION_UNIT_RERUN_MIGRATION_CHECKSUM,
    RESULT_SOURCE_ORIGIN_MIGRATION,
    RESULT_SOURCE_ORIGIN_MIGRATION_CHECKSUM,
    Database,
)
from web_backend.migrate_result_source_origin import migrate_result_source_origin
from web_backend.settings import Settings


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


def test_production_requires_explicit_result_origin_migration(tmp_path: Path) -> None:
    database_path = tmp_path / "app.db"
    database = Database(database_path)
    database.initialize()
    with database.transaction() as connection:
        connection.execute(
            "DELETE FROM app_migrations WHERE migration_id = ?",
            (RESULT_SOURCE_ORIGIN_MIGRATION,),
        )
    settings = Settings(
        data_dir=tmp_path,
        database_path=database_path,
        session_days=14,
        task_workers=1,
        bootstrap_email="test@example.com",
        bootstrap_name="测试用户",
        bootstrap_password="test-password-only",
        encryption_key="test-key-only",
        secure_cookies=False,
    )

    with pytest.raises(RuntimeError, match="尚未完成源明细追溯迁移"):
        database.initialize(require_result_source_origin=True)
    with pytest.raises(ValueError, match="必须停止应用"):
        migrate_result_source_origin(settings, app_stopped=False)
    with database.connect() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM app_migrations WHERE migration_id = ?",
                (RESULT_SOURCE_ORIGIN_MIGRATION,),
            ).fetchone()[0]
            == 0
        )

    backup_path = migrate_result_source_origin(settings, app_stopped=True)

    assert backup_path.is_file()
    database.initialize(require_result_source_origin=True)
    with database.connect() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM app_migrations WHERE migration_id = ?",
                (RESULT_SOURCE_ORIGIN_MIGRATION,),
            ).fetchone()[0]
            == 1
        )

    restore_backup(settings, backup_path)
    with database.connect() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM app_migrations WHERE migration_id = ?",
                (RESULT_SOURCE_ORIGIN_MIGRATION,),
            ).fetchone()[0]
            == 0
        )


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
