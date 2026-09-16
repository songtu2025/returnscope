from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from secrets import token_hex

from web_backend.settings import RUNTIME_DIRECTORIES, Settings


def create_backup(settings: Settings, backup_dir: Path | None = None) -> Path:
    settings.ensure_directories()
    backup_dir = (
        backup_dir
        or Path(os.getenv("WEBAPP_BACKUP_DIR", settings.data_dir / "backups"))
    ).resolve()
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
    database_snapshot.unlink(missing_ok=True)
    return archive_path


def _validate_archive(archive: zipfile.ZipFile) -> None:
    names = set(archive.namelist())
    if "app.db" not in names:
        raise ValueError("备份文件缺少 app.db")
    for name in names:
        path = PurePosixPath(name)
        allowed = name == "app.db" or (
            bool(path.parts) and path.parts[0] in RUNTIME_DIRECTORIES
        )
        if not allowed or path.is_absolute() or ".." in path.parts:
            raise ValueError(f"备份文件包含非法路径：{name}")


def _remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


@dataclass
class _RestoreContext:
    data_root: Path
    database_path: Path
    staging: Path
    restore_token: str
    directory_targets: dict[str, Path]
    old_paths: dict[str, Path] = field(default_factory=dict)
    installed: list[Path] = field(default_factory=list)
    old_database: Path | None = None
    old_sidecars: dict[Path, Path] = field(default_factory=dict)


def _resolve_restore_paths(
    settings: Settings,
    archive_path: Path,
) -> tuple[Path, Path, Path]:
    settings.ensure_directories()
    data_root = settings.data_dir.resolve()
    database_path = settings.database_path.resolve()
    if not database_path.is_relative_to(data_root):
        raise ValueError("恢复时数据库必须位于 WEBAPP_DATA_DIR 内")
    source_archive = archive_path.resolve()
    if not source_archive.is_file():
        raise ValueError("备份文件不存在")
    return data_root, database_path, source_archive


def _validate_staged_database(database_path: Path) -> None:
    connection = sqlite3.connect(database_path)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        required = {
            row[0]
            for row in connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'table' AND name IN ('users', 'tasks')
                """
            ).fetchall()
        }
    finally:
        connection.close()
    if integrity != ("ok",) or required != {"users", "tasks"}:
        raise ValueError("备份数据库校验失败")


def _prepare_staging(source_archive: Path, staging: Path) -> None:
    with zipfile.ZipFile(source_archive) as archive:
        _validate_archive(archive)
        archive.extractall(staging)
    for directory_name in RUNTIME_DIRECTORIES:
        (staging / directory_name).mkdir(exist_ok=True)
    _validate_staged_database(staging / "app.db")


def _move_current_state(context: _RestoreContext) -> None:
    if context.database_path.exists():
        context.old_database = (
            context.data_root / f".restore-old-{context.restore_token}-app.db"
        )
        shutil.copy2(context.database_path, context.old_database)
    for suffix in ("-wal", "-shm"):
        sidecar = Path(f"{context.database_path}{suffix}")
        if sidecar.exists():
            old_sidecar = context.data_root / (
                f".restore-old-{context.restore_token}-app.db{suffix}"
            )
            sidecar.replace(old_sidecar)
            context.old_sidecars[sidecar] = old_sidecar
    for name, target in context.directory_targets.items():
        if target.exists():
            old_path = context.data_root / (
                f".restore-old-{context.restore_token}-{name}"
            )
            target.replace(old_path)
            context.old_paths[name] = old_path


def _install_staged_state(context: _RestoreContext) -> None:
    shutil.copy2(context.staging / "app.db", context.database_path)
    for name, target in context.directory_targets.items():
        (context.staging / name).replace(target)
        context.installed.append(target)
    connection = sqlite3.connect(context.database_path)
    try:
        connection.execute("DELETE FROM sessions")
        connection.commit()
    finally:
        connection.close()


def _rollback_restore(context: _RestoreContext) -> None:
    for path in reversed(context.installed):
        _remove_path(path)
    for name, old_path in context.old_paths.items():
        old_path.replace(context.directory_targets[name])
    if context.old_database is not None:
        shutil.copy2(context.old_database, context.database_path)
    else:
        context.database_path.unlink(missing_ok=True)
    for suffix in ("-wal", "-shm"):
        Path(f"{context.database_path}{suffix}").unlink(missing_ok=True)
    for sidecar, old_sidecar in context.old_sidecars.items():
        old_sidecar.replace(sidecar)


def _cleanup_restored_state(context: _RestoreContext) -> None:
    for old_path in context.old_paths.values():
        _remove_path(old_path)
    if context.old_database is not None:
        context.old_database.unlink(missing_ok=True)
    for old_sidecar in context.old_sidecars.values():
        old_sidecar.unlink(missing_ok=True)


def _replace_runtime_state(context: _RestoreContext) -> None:
    try:
        _move_current_state(context)
        _install_staged_state(context)
    except Exception:
        _rollback_restore(context)
        raise
    else:
        _cleanup_restored_state(context)


def restore_backup(settings: Settings, archive_path: Path) -> Path:
    data_root, database_path, source_archive = _resolve_restore_paths(
        settings,
        archive_path,
    )

    safety_backup = create_backup(settings)
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


def remove_expired_backups(settings: Settings, retention_days: int) -> None:
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    backup_dir = Path(
        os.getenv("WEBAPP_BACKUP_DIR", settings.data_dir / "backups")
    ).resolve()
    if not backup_dir.exists():
        return
    for path in backup_dir.glob("seekway-backup-*.zip"):
        modified = datetime.fromtimestamp(path.stat().st_mtime, UTC)
        if modified < cutoff:
            path.unlink()


def main() -> None:
    settings = Settings.from_env()
    parser = argparse.ArgumentParser(description="备份或恢复 Web 运行数据")
    subparsers = parser.add_subparsers(dest="command")
    restore_parser = subparsers.add_parser("restore")
    restore_parser.add_argument("archive", type=Path)
    restore_parser.add_argument(
        "--app-stopped",
        action="store_true",
        help="确认 Web 应用和备份容器已停止",
    )
    args = parser.parse_args()
    if args.command == "restore":
        if not args.app_stopped:
            parser.error("恢复前必须停止应用，并传入 --app-stopped")
        safety_backup = restore_backup(settings, args.archive)
        print(f"恢复完成；恢复前安全备份：{safety_backup}")
        return
    retention_days = int(os.getenv("WEBAPP_BACKUP_RETENTION_DAYS", "14"))
    path = create_backup(settings)
    remove_expired_backups(settings, retention_days)
    print(path)


if __name__ == "__main__":
    main()
