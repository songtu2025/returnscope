from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Sequence

from web_backend.backup import _validate_archive, create_backup
from web_backend.settings import Settings

RUNTIME_DIRECTORIES = ("uploads", "results", "cache")
PATH_COLUMNS = (
    ("dataset_versions", "file_path"),
    ("tasks", "result_file_path"),
    ("tasks", "results_json_path"),
    ("task_segments", "result_file_path"),
    ("task_segments", "result_json_path"),
)


class ProductionMigrationError(ValueError):
    pass


@dataclass(frozen=True)
class ProductionMigrationResult:
    copied_file_count: int
    rebased_path_count: int
    encrypted_config_count: int
    backup_path: Path


def _migration_settings(data_dir: Path, database_path: Path) -> Settings:
    return Settings(
        data_dir=data_dir,
        database_path=database_path,
        session_days=14,
        task_workers=15,
        bootstrap_email="migration@example.invalid",
        bootstrap_name="migration",
        bootstrap_password="migration-only",
        encryption_key="",
        secure_cookies=False,
    )


def _validate_source(source_root: Path) -> tuple[Path, int]:
    if not source_root.is_dir():
        raise ProductionMigrationError("源运行目录不存在或不是目录")
    database_path = source_root / "app.db"
    if (
        not database_path.is_file()
        or database_path.is_symlink()
        or not database_path.resolve().is_relative_to(source_root)
    ):
        raise ProductionMigrationError("源运行目录缺少 app.db")
    for directory_name in RUNTIME_DIRECTORIES:
        path = source_root / directory_name
        if not path.is_dir():
            raise ProductionMigrationError(f"源运行目录缺少 {directory_name}")
        if path.is_symlink() or not path.resolve().is_relative_to(source_root):
            raise ProductionMigrationError(f"源目录 {directory_name} 路径不安全")
        if any(
            item.is_symlink() or not item.resolve().is_relative_to(source_root)
            for item in path.rglob("*")
        ):
            raise ProductionMigrationError(f"源目录 {directory_name} 包含不安全路径")

    connection = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        tables = {
            str(row[0])
            for row in connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'table'
                  AND name IN ('users', 'tasks', 'api_config_versions')
                """
            ).fetchall()
        }
        encrypted_config_count = int(
            connection.execute(
                """
                SELECT COUNT(*) FROM api_config_versions
                WHERE api_key_ciphertext IS NOT NULL
                  AND TRIM(api_key_ciphertext) <> ''
                """
            ).fetchone()[0]
        )
    finally:
        connection.close()
    if integrity != ("ok",) or tables != {
        "users",
        "tasks",
        "api_config_versions",
    }:
        raise ProductionMigrationError("源数据库完整性或结构校验失败")
    return database_path, encrypted_config_count


def _validate_empty_target(target_root: Path) -> None:
    if target_root.exists() and not target_root.is_dir():
        raise ProductionMigrationError("生产目标不是目录")
    if target_root.exists() and any(target_root.iterdir()):
        raise ProductionMigrationError("生产目标非空，禁止覆盖")


def _paths_overlap(first: Path, second: Path) -> bool:
    return first.is_relative_to(second) or second.is_relative_to(first)


def _normalize_path(value: str) -> str:
    return value.strip().replace("\\", "/").rstrip("/")


def _detect_stored_source_root(connection: sqlite3.Connection) -> str | None:
    roots: set[str] = set()
    for table, column in PATH_COLUMNS:
        rows = connection.execute(
            f"SELECT {column} FROM {table} "
            f"WHERE {column} IS NOT NULL AND TRIM({column}) <> ''"
        ).fetchall()
        for row in rows:
            value = _normalize_path(str(row[0]))
            lowered = value.casefold()
            for directory_name in RUNTIME_DIRECTORIES:
                marker = f"/{directory_name}/"
                position = lowered.find(marker)
                if position >= 0:
                    roots.add(value[:position])
                    break
    if not roots:
        return None
    normalized_roots = {_normalize_path(root).casefold(): root for root in roots}
    if len(normalized_roots) != 1:
        raise ProductionMigrationError(
            "数据库包含多个旧运行根路径，请显式传入 --stored-source-root"
        )
    return next(iter(normalized_roots.values()))


def _runtime_relative_path(value: str, stored_source_root: str) -> Path:
    normalized_value = _normalize_path(value)
    normalized_root = _normalize_path(stored_source_root)
    prefix = f"{normalized_root}/"
    if not normalized_value.casefold().startswith(prefix.casefold()):
        raise ProductionMigrationError("数据库文件路径不属于旧运行目录")
    relative_text = normalized_value[len(prefix) :]
    relative = PurePosixPath(relative_text)
    if (
        not relative.parts
        or relative.parts[0] not in RUNTIME_DIRECTORIES
        or ".." in relative.parts
        or relative.is_absolute()
    ):
        raise ProductionMigrationError("数据库文件路径不安全")
    return Path(*relative.parts)


def _rebase_database_paths(
    database_path: Path,
    target_root: Path,
    stored_source_root: str | None,
) -> int:
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        effective_root = stored_source_root or _detect_stored_source_root(connection)
        if effective_root is None:
            effective_root = str(target_root)
        rebased_count = 0
        for table, column in PATH_COLUMNS:
            rows = connection.execute(
                f"SELECT rowid, {column} FROM {table} "
                f"WHERE {column} IS NOT NULL AND TRIM({column}) <> ''"
            ).fetchall()
            for rowid, raw_path in rows:
                relative = _runtime_relative_path(str(raw_path), effective_root)
                destination = target_root / relative
                if not (database_path.parent / relative).is_file():
                    raise ProductionMigrationError(
                        f"备份缺少数据库引用文件：{relative.as_posix()}"
                    )
                connection.execute(
                    f"UPDATE {table} SET {column} = ? WHERE rowid = ?",
                    (str(destination), rowid),
                )
                rebased_count += 1
        connection.execute("DELETE FROM sessions")
        connection.commit()
        return rebased_count
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _validate_staged_database(database_path: Path) -> None:
    connection = sqlite3.connect(database_path)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        connection.close()
    if integrity != ("ok",) or foreign_key_errors:
        raise ProductionMigrationError("迁移后的数据库校验失败")


def migrate_production_data(
    *,
    source_root: Path,
    target_root: Path,
    backup_dir: Path,
    app_stopped: bool,
    stored_source_root: str | None = None,
) -> ProductionMigrationResult:
    if not app_stopped:
        raise ProductionMigrationError("迁移前必须停止应用，并传入 --app-stopped")
    source_root = source_root.resolve()
    target_root = target_root.resolve()
    backup_dir = backup_dir.resolve()
    if _paths_overlap(source_root, target_root):
        raise ProductionMigrationError("源目录和生产目标不能相同或互相包含")
    if _paths_overlap(backup_dir, source_root) or _paths_overlap(
        backup_dir,
        target_root,
    ):
        raise ProductionMigrationError("备份目录必须独立于源目录和生产目标")
    database_path, encrypted_config_count = _validate_source(source_root)
    _validate_empty_target(target_root)

    source_settings = _migration_settings(source_root, database_path)
    backup_path = create_backup(source_settings, backup_dir=backup_dir)

    target_root.mkdir(parents=True, exist_ok=True)
    installed: list[Path] = []
    try:
        with tempfile.TemporaryDirectory(
            prefix=".production-migration-",
            dir=target_root,
        ) as temporary:
            staging = Path(temporary)
            with zipfile.ZipFile(backup_path) as archive:
                _validate_archive(archive)
                archive.extractall(staging)
            for directory_name in RUNTIME_DIRECTORIES:
                (staging / directory_name).mkdir(exist_ok=True)
            staged_database = staging / "app.db"
            rebased_path_count = _rebase_database_paths(
                staged_database,
                target_root,
                stored_source_root,
            )
            _validate_staged_database(staged_database)
            copied_file_count = sum(
                1 for path in staging.rglob("*") if path.is_file()
            )
            for name in ("app.db", *RUNTIME_DIRECTORIES):
                source = staging / name
                destination = target_root / name
                source.replace(destination)
                installed.append(destination)
    except Exception:
        for path in reversed(installed):
            if path.is_dir():
                shutil.rmtree(path)
            elif path.exists():
                path.unlink()
        raise

    return ProductionMigrationResult(
        copied_file_count=copied_file_count,
        rebased_path_count=rebased_path_count,
        encrypted_config_count=encrypted_config_count,
        backup_path=backup_path,
    )


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="离线迁移生产运行数据")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--backup-dir", required=True, type=Path)
    parser.add_argument("--stored-source-root")
    parser.add_argument("--app-stopped", action="store_true")
    args = parser.parse_args(argv)
    if not args.app_stopped:
        parser.error("迁移前必须停止应用，并传入 --app-stopped")
    try:
        result = migrate_production_data(
            source_root=args.source,
            target_root=args.target,
            backup_dir=args.backup_dir,
            app_stopped=True,
            stored_source_root=args.stored_source_root,
        )
    except ProductionMigrationError as exc:
        parser.error(str(exc))
    print(
        json.dumps(
            {
                "copied_file_count": result.copied_file_count,
                "rebased_path_count": result.rebased_path_count,
                "encrypted_config_count": result.encrypted_config_count,
                "backup_path": str(result.backup_path),
                "next_step": "rotate_target_key_before_start",
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
