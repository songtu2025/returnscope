from __future__ import annotations

from pathlib import Path

from web_backend.settings import Settings


def build_migration_settings(tmp_path: Path) -> Settings:
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
