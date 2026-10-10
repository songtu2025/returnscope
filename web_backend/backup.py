from __future__ import annotations

import argparse
import os
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from secrets import token_hex

from web_backend.backup_runtime import (
    _cleanup_restored_state as _cleanup_restored_state,
)
from web_backend.backup_runtime import (
    _install_staged_state as _install_staged_state,
)
from web_backend.backup_runtime import (
    _move_current_state as _move_current_state,
)
from web_backend.backup_runtime import (
    _prepare_staging as _prepare_staging,
)
from web_backend.backup_runtime import (
    _remove_path as _remove_path,
)
from web_backend.backup_runtime import (
    _replace_runtime_state as _replace_runtime_state,
)
from web_backend.backup_runtime import (
    _resolve_restore_paths as _resolve_restore_paths,
)
from web_backend.backup_runtime import (
    _RestoreContext as _RestoreContext,
)
from web_backend.backup_runtime import (
    _rollback_restore as _rollback_restore,
)
from web_backend.backup_runtime import (
    _validate_archive as _validate_archive,
)
from web_backend.backup_runtime import (
    _validate_staged_database as _validate_staged_database,
)
from web_backend.settings import RUNTIME_DIRECTORIES, Settings

BACKUP_KEEP_COUNT = 3
BACKUP_INTERVAL_SECONDS = 24 * 60 * 60


def _backup_dir(settings: Settings) -> Path:
    return Path(os.getenv("WEBAPP_BACKUP_DIR", settings.data_dir / "backups")).resolve()


def create_backup(settings: Settings, backup_dir: Path | None = None) -> Path:
    settings.ensure_directories()
    backup_dir = (backup_dir or _backup_dir(settings)).resolve()
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    database_snapshot = backup_dir / f"database-{timestamp}.db"
    archive_path = backup_dir / f"seekway-backup-{timestamp}.zip"

    source = sqlite3.connect(settings.database_path)
    destination = sqlite3.connect(database_snapshot)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()

    try:
        with zipfile.ZipFile(
            archive_path,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
        ) as archive:
            archive.write(database_snapshot, "app.db")
            for directory_name in RUNTIME_DIRECTORIES:
                directory = settings.data_dir / directory_name
                if not directory.exists():
                    continue
                for path in directory.rglob("*"):
                    if path.is_file():
                        archive.write(
                            path,
                            path.relative_to(settings.data_dir).as_posix(),
                        )
        with zipfile.ZipFile(archive_path) as archive:
            _validate_archive(archive)
            if archive.testzip() is not None:
                raise ValueError("备份文件校验失败")
    except Exception:
        archive_path.unlink(missing_ok=True)
        raise
    finally:
        database_snapshot.unlink(missing_ok=True)
    return archive_path


def verify_backup(archive_path: Path) -> None:
    source_archive = archive_path.resolve()
    if not source_archive.is_file():
        raise ValueError("备份文件不存在")
    with tempfile.TemporaryDirectory(
        prefix=".backup-verify-",
        dir=source_archive.parent,
    ) as temporary:
        _prepare_staging(source_archive, Path(temporary))


def restore_backup(
    settings: Settings,
    archive_path: Path,
    safety_backup_dir: Path | None = None,
) -> Path:
    data_root, database_path, source_archive = _resolve_restore_paths(
        settings,
        archive_path,
    )

    safety_backup = create_backup(settings, safety_backup_dir)
    restore_token = token_hex(6)
    with tempfile.TemporaryDirectory(
        prefix="restore-",
        dir=data_root,
    ) as temporary:
        staging = Path(temporary)
        _prepare_staging(source_archive, staging)
        context = _RestoreContext(
            data_root=data_root,
            database_path=database_path,
            staging=staging,
            restore_token=restore_token,
            directory_targets={name: data_root / name for name in RUNTIME_DIRECTORIES},
        )
        _replace_runtime_state(context)
    return safety_backup


def drill_restore(
    settings: Settings,
    archive_path: Path,
    *,
    check_app: bool = False,
) -> None:
    source_archive = archive_path.resolve()
    if not source_archive.is_file():
        raise ValueError("备份文件不存在")
    with tempfile.TemporaryDirectory(
        prefix=".restore-drill-",
        dir=source_archive.parent,
    ) as temporary:
        drill_root = Path(temporary)
        drill_runtime = drill_root / "runtime"
        drill_settings = replace(
            settings,
            data_dir=drill_runtime,
            database_path=drill_runtime / "app.db",
        )
        drill_settings.ensure_directories()
        sqlite3.connect(drill_settings.database_path).close()
        restore_backup(drill_settings, source_archive, drill_root / "safety-backups")
        _validate_staged_database(drill_settings.database_path)
        connection = sqlite3.connect(drill_settings.database_path)
        try:
            sessions = connection.execute("SELECT COUNT(*) FROM sessions").fetchone()
        finally:
            connection.close()
        if sessions != (0,):
            raise ValueError("恢复演练后会话未清除")
        with zipfile.ZipFile(source_archive) as archive:
            for member in archive.infolist():
                if member.is_dir() or member.filename == "app.db":
                    continue
                restored_file = drill_runtime.joinpath(
                    *PurePosixPath(member.filename).parts
                )
                if (
                    not restored_file.is_file()
                    or restored_file.stat().st_size != member.file_size
                ):
                    raise ValueError("恢复演练后运行文件不完整")
        if check_app:
            environment = os.environ.copy()
            environment.update(
                {
                    "WEBAPP_DATA_DIR": str(drill_runtime),
                    "WEBAPP_DATABASE_PATH": str(drill_settings.database_path),
                    "WEBAPP_PRODUCTION": "false",
                    "WEBAPP_SECURE_COOKIES": "false",
                    "WEBAPP_MAIL_PROVIDER": "console",
                    "WEBAPP_SMTP_USE_TLS": "false",
                    "WEBAPP_SMTP_USE_SSL": "false",
                    "WEBAPP_ENCRYPTION_KEY": "",
                }
            )
            completed = subprocess.run(
                [sys.executable, "-m", "web_backend.restore_app_smoke"],
                env=environment,
                capture_output=True,
                text=True,
                check=False,
                timeout=180,
            )
            if completed.returncode != 0:
                raise RuntimeError("恢复后的应用检查失败")


def prune_backups(settings: Settings) -> None:
    backup_dir = _backup_dir(settings)
    if not backup_dir.exists():
        return
    backups = sorted(
        backup_dir.glob("seekway-backup-*.zip"),
        key=lambda path: path.name,
        reverse=True,
    )
    for path in backups[BACKUP_KEEP_COUNT:]:
        path.unlink()


def _backup_due(settings: Settings) -> bool:
    backup_dir = _backup_dir(settings)
    latest_modified = max(
        (path.stat().st_mtime for path in backup_dir.glob("seekway-backup-*.zip")),
        default=None,
    )
    return (
        latest_modified is None
        or datetime.now(UTC).timestamp() - latest_modified >= BACKUP_INTERVAL_SECONDS
    )


def main() -> None:
    settings = Settings.from_env()
    parser = argparse.ArgumentParser(description="备份或恢复 Web 运行数据")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("scheduled")
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("archive", type=Path)
    drill_parser = subparsers.add_parser("drill")
    drill_parser.add_argument("archive", type=Path)
    drill_parser.add_argument("--check-app", action="store_true")
    restore_parser = subparsers.add_parser("restore")
    restore_parser.add_argument("archive", type=Path)
    restore_parser.add_argument(
        "--app-stopped",
        action="store_true",
        help="确认 Web 应用和备份容器已停止",
    )
    args = parser.parse_args()
    if args.command == "verify":
        verify_backup(args.archive)
        print(f"备份验证通过：{args.archive}")
        return
    if args.command == "drill":
        drill_restore(settings, args.archive, check_app=args.check_app)
        label = "恢复与应用演练" if args.check_app else "恢复演练"
        print(f"{label}通过：{args.archive}")
        return
    if args.command == "restore":
        if not args.app_stopped:
            parser.error("恢复前必须停止应用，并传入 --app-stopped")
        safety_backup = restore_backup(settings, args.archive)
        print(f"恢复完成；恢复前安全备份：{safety_backup}")
        return
    if args.command == "scheduled" and not _backup_due(settings):
        return
    path = create_backup(settings)
    prune_backups(settings)
    print(path)


# 保留原辅助入口的模块归属和可调用签名。
for _entry in (
    _validate_archive,
    _remove_path,
    _RestoreContext,
    _resolve_restore_paths,
    _validate_staged_database,
    _prepare_staging,
    _move_current_state,
    _install_staged_state,
    _rollback_restore,
    _cleanup_restored_state,
    _replace_runtime_state,
):
    _entry.__module__ = __name__
del _entry


if __name__ == "__main__":
    main()
