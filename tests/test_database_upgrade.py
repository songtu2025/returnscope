from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from database_migration_helpers import build_migration_settings as _settings

from web_backend.backup import restore_backup
from web_backend.database import Database
from web_backend.database_migrations import (
    RESULT_SOURCE_ORIGIN_MIGRATION,
)
from web_backend.migrate_result_source_origin import migrate_result_source_origin
from web_backend.upgrade_database import (
    initialize_empty_database,
    upgrade_database,
)


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


def test_product_alias_upgrade_requires_stop_and_supports_backup_restore(tmp_path):
    settings = _settings(tmp_path)
    database = Database(settings.database_path)
    database.initialize()
    with database.transaction() as connection:
        connection.execute("DROP TABLE product_identity_aliases")
        connection.execute(
            "DELETE FROM app_migrations WHERE migration_id = '20261011_product_identity_aliases'"
        )
    with pytest.raises(RuntimeError, match="缺少表"):
        database.initialize(production=True)
    with pytest.raises(ValueError, match="必须停止应用"):
        upgrade_database(settings, app_stopped=False)
    backup = upgrade_database(settings, app_stopped=True)
    database.initialize(production=True)
    restore_backup(settings, backup)
    with pytest.raises(RuntimeError, match="缺少表"):
        database.initialize(production=True)


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
    database.initialize(production=True)

    restore_backup(settings, backup_path)
    with pytest.raises(RuntimeError, match="缺少索引"):
        database.initialize(production=True)


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


def test_offline_upgrade_rolls_back_migration_changes_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    database = Database(settings.database_path)
    database.initialize()
    with database.connect() as connection:
        connection.execute("CREATE TABLE migration_test_state (value TEXT NOT NULL)")
        connection.execute("INSERT INTO migration_test_state VALUES ('before')")
        connection.execute("DROP INDEX idx_task_segments_status_order")

    def snapshot() -> tuple[list[tuple[object, ...]], list[tuple[object, ...]], str]:
        with database.connect() as connection:
            schema = [
                tuple(row)
                for row in connection.execute(
                    "SELECT type, name, sql FROM sqlite_master ORDER BY type, name"
                )
            ]
            migrations = [
                tuple(row)
                for row in connection.execute(
                    "SELECT migration_id, checksum, status FROM app_migrations "
                    "ORDER BY migration_id"
                )
            ]
            value = connection.execute(
                "SELECT value FROM migration_test_state"
            ).fetchone()[0]
            return schema, migrations, value

    before = snapshot()

    def fail_after_changes(connection: sqlite3.Connection) -> None:
        connection.execute("CREATE TABLE partial_upgrade_marker (id TEXT)")
        connection.execute("UPDATE migration_test_state SET value = 'changed'")
        connection.execute(
            "INSERT INTO app_migrations(migration_id, checksum, status, applied_at) "
            "VALUES ('test_partial_upgrade', 'test', 'applied', '2026-01-01')"
        )
        raise RuntimeError("模拟迁移中途失败")

    with monkeypatch.context() as failure:
        failure.setattr(
            Database, "_migrate_dataset_columns", staticmethod(fail_after_changes)
        )
        with pytest.raises(RuntimeError, match="保持停服，使用备份恢复"):
            upgrade_database(settings, app_stopped=True)

    assert next((tmp_path / "backups").glob("seekway-backup-*.zip")).is_file()
    assert snapshot() == before

    upgrade_database(settings, app_stopped=True)
    database.validate_production_schema()
    upgraded = snapshot()
    upgrade_database(settings, app_stopped=True)
    assert snapshot() == upgraded


def test_upgrade_rejects_foreign_key_violation_without_partial_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = Database(tmp_path / "app.db")
    database.initialize()
    with database.connect() as connection:
        connection.execute("DROP INDEX idx_task_segments_status_order")

    def insert_invalid_session(connection: sqlite3.Connection) -> None:
        connection.execute(
            "INSERT INTO sessions(id, user_id, token_hash, expires_at, created_at) "
            "VALUES ('session-1', 'missing-user', 'token-1', '2026-01-01', '2026-01-01')"
        )

    with monkeypatch.context() as failure:
        failure.setattr(
            Database, "_migrate_dataset_columns", staticmethod(insert_invalid_session)
        )
        with pytest.raises(RuntimeError, match="外键完整性检查失败"):
            database.upgrade_schema()

    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE name = 'idx_task_segments_status_order'"
            ).fetchone()
            is None
        )
