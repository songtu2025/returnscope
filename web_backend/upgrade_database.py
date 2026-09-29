from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from web_backend.backup import create_backup, verify_backup
from web_backend.database import Database
from web_backend.settings import Settings


def upgrade_database(settings: Settings, *, app_stopped: bool) -> Path:
    """停服后备份并升级现有数据库，返回迁移前备份路径。"""
    if not app_stopped:
        raise ValueError("升级前必须停止应用和定时备份服务")
    if not settings.database_path.is_file():
        raise FileNotFoundError("运行数据库不存在，已取消升级")

    database = Database(settings.database_path)
    with database.connect() as connection:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("运行数据库完整性检查失败，已取消升级")
    backup_path = create_backup(settings)
    verify_backup(backup_path)

    try:
        database.upgrade_schema()
        database.validate_production_schema()
        with database.connect() as connection:
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("升级后数据库完整性检查失败")
    except (RuntimeError, ValueError, sqlite3.Error) as exc:
        raise RuntimeError(
            f"数据库升级失败；保持停服，使用备份恢复：{backup_path}"
        ) from exc
    return backup_path


def initialize_empty_database(settings: Settings, *, app_stopped: bool) -> None:
    """仅在全新部署且没有运行数据库时显式创建结构。"""
    if not app_stopped:
        raise ValueError("初始化前必须停止应用和定时备份服务")
    if settings.database_path.exists():
        raise FileExistsError("运行数据库已存在，已取消空库初始化")
    settings.ensure_directories()
    database = Database(settings.database_path)
    database.upgrade_schema()
    database.validate_production_schema()


def main() -> None:
    parser = argparse.ArgumentParser(description="停服后备份并升级 Web 数据库")
    parser.add_argument(
        "--app-stopped", action="store_true", help="确认应用和定时备份服务已停止"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check-only",
        action="store_true",
        help="只读检查运行数据库是否可供当前版本启动",
    )
    mode.add_argument(
        "--initialize-empty", action="store_true", help="仅供全新部署初始化空数据库"
    )
    args = parser.parse_args()
    if args.check_only:
        Database(Settings.from_env().database_path).validate_production_schema()
        print("数据库结构检查通过")
        return
    if not args.app_stopped:
        parser.error("升级前必须停止应用和定时备份服务，并传入 --app-stopped")
    settings = Settings.from_env()
    if args.initialize_empty:
        initialize_empty_database(settings, app_stopped=True)
        print("空数据库初始化完成")
        return
    backup_path = upgrade_database(settings, app_stopped=True)
    print(f"数据库升级完成；迁移前备份：{backup_path}")


if __name__ == "__main__":
    main()
