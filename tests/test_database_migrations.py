from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from web_backend.classification_result_queries import system_rerun_counts
from web_backend.database import (
    CLASSIFICATION_UNIT_RERUN_MIGRATION,
    CLASSIFICATION_UNIT_RERUN_MIGRATION_CHECKSUM,
    Database,
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
