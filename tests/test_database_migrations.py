from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from web_backend.backup import restore_backup
from web_backend.classification_result_queries import system_rerun_counts
from web_backend.database import Database
from web_backend.database_migrations import (
    CLASSIFICATION_UNIT_RERUN_MIGRATION,
    CLASSIFICATION_UNIT_RERUN_MIGRATION_CHECKSUM,
    RESULT_SOURCE_ORIGIN_MIGRATION,
    RESULT_SOURCE_ORIGIN_MIGRATION_CHECKSUM,
)
from web_backend.migrate_result_source_origin import migrate_result_source_origin
from web_backend.settings import Settings
from web_backend.upgrade_database import initialize_empty_database, upgrade_database


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path,
        database_path=tmp_path / "app.db",
        session_days=14,
        task_workers=1,
        bootstrap_email="test@example.com",
        bootstrap_name="测试用户",
        bootstrap_password="test-password-only",
        encryption_key="test-key-only",
        secure_cookies=False,
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


def test_production_requires_explicit_result_origin_migration(tmp_path: Path) -> None:
    database_path = tmp_path / "app.db"
    database = Database(database_path)
    database.initialize()
    with database.transaction() as connection:
        connection.execute(
            "DELETE FROM app_migrations WHERE migration_id = ?",
            (RESULT_SOURCE_ORIGIN_MIGRATION,),
        )
    settings = _settings(tmp_path)

    with pytest.raises(RuntimeError, match="迁移记录 .* 缺失或校验失败"):
        database.initialize(production=True)
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
    database.initialize(production=True)
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


def test_production_startup_validates_schema_without_modifying_it(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "app.db")
    database.initialize()
    with database.connect() as connection:
        before = [
            tuple(row)
            for row in connection.execute(
                "SELECT type, name, sql FROM sqlite_master ORDER BY type, name"
            )
        ]
    database.initialize(production=True)
    database.initialize(production=True)
    with database.connect() as connection:
        after = [
            tuple(row)
            for row in connection.execute(
                "SELECT type, name, sql FROM sqlite_master ORDER BY type, name"
            )
        ]
    assert after == before


def test_production_startup_rejects_missing_database_and_index(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "app.db")
    with pytest.raises(RuntimeError, match="生产数据库不存在"):
        database.initialize(production=True)
    assert not database.path.exists()

    database.initialize()
    with database.connect() as connection:
        connection.execute("DROP INDEX idx_task_segments_status_order")
    before = database.path.read_bytes()
    with pytest.raises(RuntimeError, match="缺少索引"):
        database.initialize(production=True)
    assert database.path.read_bytes() == before


def test_empty_production_database_requires_explicit_initialization(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    database = Database(settings.database_path)
    with pytest.raises(RuntimeError, match="生产数据库不存在"):
        database.initialize(production=True)
    with pytest.raises(ValueError, match="必须停止应用"):
        initialize_empty_database(settings, app_stopped=False)

    initialize_empty_database(settings, app_stopped=True)
    database.initialize(production=True)
    with pytest.raises(FileExistsError, match="已存在"):
        initialize_empty_database(settings, app_stopped=True)


def test_offline_upgrade_restores_missing_schema_and_can_rollback(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "app.db"
    database = Database(database_path)
    database.initialize()
    with database.connect() as connection:
        connection.execute("DROP INDEX idx_task_segments_status_order")
    settings = _settings(tmp_path)
    with pytest.raises(ValueError, match="必须停止应用"):
        upgrade_database(settings, app_stopped=False)
    with pytest.raises(RuntimeError, match="缺少索引"):
        database.validate_production_schema()

    backup_path = upgrade_database(settings, app_stopped=True)
    assert backup_path.is_file()
    database.validate_production_schema()

    restore_backup(settings, backup_path)
    with pytest.raises(RuntimeError, match="缺少索引"):
        database.validate_production_schema()


def test_offline_upgrade_failure_keeps_verified_backup_for_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "app.db"
    database = Database(database_path)
    database.initialize()
    settings = _settings(tmp_path)

    def fail_after_partial_change(self: Database) -> None:
        with self.connect() as connection:
            connection.execute("CREATE TABLE partial_upgrade_marker (id TEXT)")
        raise RuntimeError("模拟中途失败")

    monkeypatch.setattr(Database, "upgrade_schema", fail_after_partial_change)
    with pytest.raises(RuntimeError, match="保持停服，使用备份恢复"):
        upgrade_database(settings, app_stopped=True)
    backup_path = next((tmp_path / "backups").glob("seekway-backup-*.zip"))
    assert backup_path.is_file()
    with database.connect() as connection:
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE name = 'partial_upgrade_marker'"
        ).fetchone()

    restore_backup(settings, backup_path)
    with database.connect() as connection:
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE name = 'partial_upgrade_marker'"
            ).fetchone()
            is None
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
