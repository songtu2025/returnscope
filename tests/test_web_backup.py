from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import time
import zipfile
from pathlib import Path

import pytest

import web_backend.backup as backup_module
from web_backend.backup import (
    BACKUP_INTERVAL_SECONDS,
    create_backup,
    prune_backups,
    restore_backup,
    verify_backup,
)
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


def _prepare_scheduled_backup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, list[str]]:
    settings = _settings(tmp_path)
    settings.ensure_directories()
    Database(settings.database_path).initialize()
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    monkeypatch.setenv("WEBAPP_BACKUP_DIR", str(backup_dir))
    old_names = [
        f"seekway-backup-202609{day:02d}T000000000000Z.zip" for day in range(1, 5)
    ]
    old_time = time.time() - BACKUP_INTERVAL_SECONDS - 60
    for name in old_names:
        path = backup_dir / name
        path.write_bytes(b"archive")
        os.utime(path, (old_time, old_time))
    monkeypatch.setattr(
        backup_module.Settings, "from_env", classmethod(lambda cls: settings)
    )
    monkeypatch.setattr(sys, "argv", ["backup", "scheduled"])
    return backup_dir, old_names


def _prepare_real_backup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path]:
    settings = _settings(tmp_path)
    settings.ensure_directories()
    Database(settings.database_path).initialize()
    backup_dir = tmp_path / "backups"
    existing = create_backup(settings, backup_dir)
    monkeypatch.setenv("WEBAPP_BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(
        backup_module.Settings, "from_env", classmethod(lambda cls: settings)
    )
    return backup_dir, existing


@pytest.mark.parametrize("archive_count", [1, 3, 5])
def test_prune_backups_keeps_latest_three(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    archive_count: int,
) -> None:
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    monkeypatch.setenv("WEBAPP_BACKUP_DIR", str(backup_dir))
    names = [
        f"seekway-backup-202609{day:02d}T000000000000Z.zip"
        for day in range(1, archive_count + 1)
    ]
    for name in names:
        (backup_dir / name).write_bytes(b"archive")
    (backup_dir / "manual-backup.zip").write_bytes(b"manual")

    prune_backups(_settings(tmp_path))

    assert (
        sorted(path.name for path in backup_dir.glob("seekway-backup-*.zip"))
        == names[-3:]
    )
    assert (backup_dir / "manual-backup.zip").exists()


def test_scheduled_backup_prunes_after_valid_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backup_dir, old_names = _prepare_scheduled_backup(tmp_path, monkeypatch)

    backup_module.main()

    remaining = sorted(path.name for path in backup_dir.glob("seekway-backup-*.zip"))
    assert len(remaining) == 3
    assert remaining[:2] == old_names[-2:]
    with zipfile.ZipFile(backup_dir / remaining[-1]) as archive:
        assert archive.testzip() is None


def test_scheduled_backup_skips_recent_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backup_dir, existing = _prepare_real_backup(tmp_path, monkeypatch)
    recent_time = time.time() - BACKUP_INTERVAL_SECONDS + 60
    os.utime(existing, (recent_time, recent_time))
    monkeypatch.setattr(sys, "argv", ["backup", "scheduled"])

    backup_module.main()
    backup_module.main()

    assert list(backup_dir.glob("seekway-backup-*.zip")) == [existing]
    assert not list(backup_dir.glob("database-*.db"))


def test_scheduled_backup_runs_after_interval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backup_dir, existing = _prepare_real_backup(tmp_path, monkeypatch)
    old_time = time.time() - BACKUP_INTERVAL_SECONDS - 60
    os.utime(existing, (old_time, old_time))
    monkeypatch.setattr(sys, "argv", ["backup", "scheduled"])

    backup_module.main()

    assert len(list(backup_dir.glob("seekway-backup-*.zip"))) == 2
    assert existing.exists()


def test_manual_backup_runs_with_recent_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backup_dir, existing = _prepare_real_backup(tmp_path, monkeypatch)
    monkeypatch.setattr(sys, "argv", ["backup"])

    backup_module.main()

    assert len(list(backup_dir.glob("seekway-backup-*.zip"))) == 2
    assert existing.exists()


def test_failed_backup_does_not_prune_existing_archives(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backup_dir, old_names = _prepare_scheduled_backup(tmp_path, monkeypatch)
    with monkeypatch.context() as failure_patch:
        failure_patch.setattr(
            backup_module.zipfile.ZipFile, "testzip", lambda self: "app.db"
        )
        with pytest.raises(ValueError, match="备份文件校验失败"):
            backup_module.main()

    assert (
        sorted(path.name for path in backup_dir.glob("seekway-backup-*.zip"))
        == old_names
    )
    assert not list(backup_dir.glob("database-*.db"))

    backup_module.main()

    assert len(list(backup_dir.glob("seekway-backup-*.zip"))) == 3


def test_verify_command_keeps_runtime_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = _settings(tmp_path)
    settings.ensure_directories()
    database = Database(settings.database_path)
    database.initialize()
    upload = settings.data_dir / "uploads" / "sample.csv"
    upload.write_text("sku,comment\n1,test\n", encoding="utf-8")
    backup_dir = tmp_path / "backups"
    backup = create_backup(settings, backup_dir)
    database_before = settings.database_path.read_bytes()
    monkeypatch.setattr(
        backup_module.Settings, "from_env", classmethod(lambda cls: settings)
    )
    monkeypatch.setattr(sys, "argv", ["backup", "verify", str(backup)])

    backup_module.main()

    assert "备份验证通过" in capsys.readouterr().out
    assert upload.read_text(encoding="utf-8") == "sku,comment\n1,test\n"
    assert settings.database_path.read_bytes() == database_before
    with database.connect() as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert not list(backup_dir.glob(".backup-verify-*"))
    assert list(backup_dir.glob("seekway-backup-*.zip")) == [backup]


def test_verify_backup_rejects_corrupt_database_and_cleans_staging(
    tmp_path: Path,
) -> None:
    backup = tmp_path / "invalid.zip"
    with zipfile.ZipFile(backup, mode="w") as archive:
        archive.writestr("app.db", b"not a sqlite database")

    with pytest.raises(sqlite3.DatabaseError):
        verify_backup(backup)

    assert not list(tmp_path.glob(".backup-verify-*"))


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
