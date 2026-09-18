from __future__ import annotations

import shutil
import sqlite3
import zipfile
from pathlib import Path

import pytest

from web_backend.backup import create_backup, restore_backup
from web_backend.database import Database
from web_backend.settings import Settings


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "runtime",
        database_path=tmp_path / "runtime" / "app.db",
        session_days=14,
        task_workers=1,
        bootstrap_email="admin@example.com",
        bootstrap_name="管理员",
        bootstrap_password="test-password-123",
        encryption_key="",
        secure_cookies=False,
    )


def test_backup_contains_database_and_immutable_files(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings = _settings(tmp_path)
    settings.ensure_directories()
    database = Database(settings.database_path)
    database.initialize()
    with database.transaction(immediate=True) as connection:
        connection.execute(
            """
            INSERT INTO users(
                id, email, display_name, password_hash, created_at
            ) VALUES ('user-1', 'user@example.com', '原始用户', 'hash', '2026-01-01')
            """
        )
    upload = settings.data_dir / "uploads" / "dataset" / "v1.csv"
    upload.parent.mkdir(parents=True)
    upload.write_text("sku,comment\n1,test\n", encoding="utf-8")
    cache = settings.data_dir / "cache" / "config-1.jsonl"
    cache.write_text("cached\n", encoding="utf-8")
    raw_import = settings.data_dir / "imports" / "return-import.csv"
    raw_import.write_text("sku,comment\n1,raw\n", encoding="utf-8")
    backup_dir = tmp_path / "separate-backups"
    monkeypatch.setenv("WEBAPP_BACKUP_DIR", str(backup_dir))

    backup = create_backup(settings)

    assert backup.exists()
    assert backup.parent == backup_dir
    with zipfile.ZipFile(backup) as archive:
        assert "app.db" in archive.namelist()
        assert "uploads/dataset/v1.csv" in archive.namelist()
        assert "cache/config-1.jsonl" in archive.namelist()
        assert "imports/return-import.csv" in archive.namelist()
        database_copy = tmp_path / "restored.db"
        database_copy.write_bytes(archive.read("app.db"))
    with sqlite3.connect(database_copy) as connection:
        table = connection.execute(
            "SELECT name FROM sqlite_master WHERE name = 'tasks'"
        ).fetchone()
    assert table == ("tasks",)

    upload.write_text("sku,comment\n1,changed\n", encoding="utf-8")
    cache.write_text("changed\n", encoding="utf-8")
    raw_import.write_text("changed\n", encoding="utf-8")
    with database.transaction(immediate=True) as connection:
        connection.execute(
            "UPDATE users SET display_name = '已修改' WHERE id = 'user-1'"
        )
        connection.execute(
            """
            INSERT INTO sessions(
                id, user_id, token_hash, expires_at, created_at
            ) VALUES ('session-1', 'user-1', 'token', '2099-01-01', '2026-01-01')
            """
        )

    safety_backup = restore_backup(settings, backup)

    assert safety_backup.exists()
    assert safety_backup != backup
    assert upload.read_text(encoding="utf-8") == "sku,comment\n1,test\n"
    assert cache.read_text(encoding="utf-8") == "cached\n"
    assert raw_import.read_text(encoding="utf-8") == "sku,comment\n1,raw\n"
    with database.connect() as connection:
        restored_user = connection.execute(
            "SELECT display_name FROM users WHERE id = 'user-1'"
        ).fetchone()
        sessions = connection.execute(
            "SELECT COUNT(*) AS count FROM sessions"
        ).fetchone()
    assert restored_user["display_name"] == "原始用户"
    assert sessions["count"] == 0


def test_restore_accepts_legacy_backup_without_imports_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings = _settings(tmp_path)
    settings.ensure_directories()
    Database(settings.database_path).initialize()
    raw_import = settings.data_dir / "imports" / "current.csv"
    raw_import.write_text("current\n", encoding="utf-8")
    backup_dir = tmp_path / "backups"
    monkeypatch.setenv("WEBAPP_BACKUP_DIR", str(backup_dir))
    current_backup = create_backup(settings)
    legacy_backup = backup_dir / "legacy-backup.zip"
    with (
        zipfile.ZipFile(current_backup) as source,
        zipfile.ZipFile(legacy_backup, mode="w") as destination,
    ):
        for item in source.infolist():
            if not item.filename.startswith("imports/"):
                destination.writestr(item, source.read(item.filename))

    restore_backup(settings, legacy_backup)

    assert (settings.data_dir / "imports").is_dir()
    assert not list((settings.data_dir / "imports").iterdir())


def test_restore_validation_failure_keeps_runtime_and_creates_safety_backup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    settings.ensure_directories()
    Database(settings.database_path).initialize()
    current_upload = settings.data_dir / "uploads" / "current.csv"
    current_upload.write_text("current\n", encoding="utf-8")
    invalid_backup = tmp_path / "invalid.zip"
    with zipfile.ZipFile(invalid_backup, mode="w") as archive:
        archive.writestr("uploads/replacement.csv", "replacement\n")
    safety_backup_dir = tmp_path / "safety-backups"
    monkeypatch.setenv("WEBAPP_BACKUP_DIR", str(safety_backup_dir))

    with pytest.raises(ValueError, match="备份文件缺少 app.db"):
        restore_backup(settings, invalid_backup)

    assert current_upload.read_text(encoding="utf-8") == "current\n"
    assert len(list(safety_backup_dir.glob("seekway-backup-*.zip"))) == 1


def test_restore_install_failure_rolls_back_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    settings.ensure_directories()
    database = Database(settings.database_path)
    database.initialize()
    with database.transaction(immediate=True) as connection:
        connection.execute(
            """
            INSERT INTO users(
                id, email, display_name, password_hash, created_at
            ) VALUES ('user-1', 'user@example.com', '备份状态', 'hash', '2026-01-01')
            """
        )
    current_upload = settings.data_dir / "uploads" / "current.csv"
    current_upload.write_text("before-backup\n", encoding="utf-8")
    source_backup = create_backup(settings, tmp_path / "source-backups")
    current_upload.write_text("current\n", encoding="utf-8")
    with database.transaction(immediate=True) as connection:
        connection.execute(
            "UPDATE users SET display_name = '当前状态' WHERE id = 'user-1'"
        )
    original_copytree = shutil.copytree

    def fail_staged_imports(source: Path, target: Path, *args, **kwargs):
        if source.name == "imports" and source.parent.name.startswith("restore-"):
            raise OSError("模拟恢复安装失败")
        return original_copytree(source, target, *args, **kwargs)

    monkeypatch.setattr(shutil, "copytree", fail_staged_imports)
    monkeypatch.setenv("WEBAPP_BACKUP_DIR", str(tmp_path / "safety-backups"))

    with pytest.raises(OSError, match="模拟恢复安装失败"):
        restore_backup(settings, source_backup)

    assert current_upload.read_text(encoding="utf-8") == "current\n"
    assert not list(settings.data_dir.glob(".restore-old-*"))
    with database.connect() as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert (
            connection.execute(
                "SELECT display_name FROM users WHERE id = 'user-1'"
            ).fetchone()[0]
            == "当前状态"
        )
