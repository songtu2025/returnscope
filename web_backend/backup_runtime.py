from __future__ import annotations

import shutil
import sqlite3
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from web_backend.settings import RUNTIME_DIRECTORIES, Settings


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
        shutil.copytree(context.staging / name, target)
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
        _cleanup_restored_state(context)
        raise
    else:
        _cleanup_restored_state(context)
