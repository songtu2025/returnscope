from __future__ import annotations

import sqlite3
import zipfile
from pathlib import Path

from web_backend.backup import create_backup, restore_backup
from web_backend.database import Database
from web_backend.settings import Settings


def test_backup_contains_database_and_immutable_files(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings = Settings(
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
    backup_dir = tmp_path / "separate-backups"
    monkeypatch.setenv("WEBAPP_BACKUP_DIR", str(backup_dir))

    backup = create_backup(settings)

    assert backup.exists()
    assert backup.parent == backup_dir
    with zipfile.ZipFile(backup) as archive:
        assert "app.db" in archive.namelist()
        assert "uploads/dataset/v1.csv" in archive.namelist()
        assert "cache/config-1.jsonl" in archive.namelist()
        database_copy = tmp_path / "restored.db"
        database_copy.write_bytes(archive.read("app.db"))
    with sqlite3.connect(database_copy) as connection:
        table = connection.execute(
            "SELECT name FROM sqlite_master WHERE name = 'tasks'"
        ).fetchone()
    assert table == ("tasks",)

    upload.write_text("sku,comment\n1,changed\n", encoding="utf-8")
    cache.write_text("changed\n", encoding="utf-8")
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
    with database.connect() as connection:
        restored_user = connection.execute(
            "SELECT display_name FROM users WHERE id = 'user-1'"
        ).fetchone()
        sessions = connection.execute(
            "SELECT COUNT(*) AS count FROM sessions"
        ).fetchone()
    assert restored_user["display_name"] == "原始用户"
    assert sessions["count"] == 0
