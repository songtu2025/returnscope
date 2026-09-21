from __future__ import annotations

import argparse
import tempfile
import zipfile
from pathlib import Path

from web_backend.backup import (
    _validate_archive,
    _validate_staged_database,
    create_backup,
)
from web_backend.database import Database
from web_backend.settings import Settings


def migrate_result_source_origin(settings: Settings, *, app_stopped: bool) -> Path:
    if not app_stopped:
        raise ValueError("迁移前必须停止应用和定时备份服务")
    if not settings.database_path.is_file():
        raise FileNotFoundError("运行数据库不存在，已取消迁移")

    backup_path = create_backup(settings)
    with zipfile.ZipFile(backup_path) as archive:
        _validate_archive(archive)
        if archive.testzip() is not None:
            raise ValueError("迁移前备份文件校验失败")
        with tempfile.TemporaryDirectory(
            prefix="migration-check-", dir=settings.data_dir
        ) as temporary:
            archive.extract("app.db", temporary)
            _validate_staged_database(Path(temporary) / "app.db")

    database = Database(settings.database_path)
    with database.connect() as connection:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("运行数据库完整性检查失败，已取消迁移")
        database._migrate_result_source_origin(connection)
        database._require_result_source_origin(connection)
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("迁移后数据库完整性检查失败")
    return backup_path


def main() -> None:
    parser = argparse.ArgumentParser(description="显式迁移分类结果源明细追溯字段")
    parser.add_argument(
        "--app-stopped", action="store_true", help="确认应用和定时备份服务已停止"
    )
    args = parser.parse_args()
    if not args.app_stopped:
        parser.error("迁移前必须停止应用和定时备份服务，并传入 --app-stopped")
    backup_path = migrate_result_source_origin(
        Settings.from_env(), app_stopped=args.app_stopped
    )
    print(f"迁移完成；迁移前备份：{backup_path}")


if __name__ == "__main__":
    main()
