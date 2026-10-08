"""盘点分析产物文件，并校验已确认的恢复备份。"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from web_backend.dataset_files import _sha256_file


def inventory_files(
    connection: sqlite3.Connection, data_dir: Path
) -> list[dict[str, Any]]:
    root = data_dir.resolve()
    files: set[Path] = set()
    for folder in (root / "results", root / "tmp"):
        if folder.exists():
            files.update(path for path in folder.rglob("*") if not path.is_dir())
    files.update((root / "cache").glob("*.jsonl"))
    retained: set[Path] = set()
    for table, column in (
        ("dataset_versions", "file_path"),
        ("dataset_imports", "raw_file_path"),
    ):
        for row in connection.execute(
            f"SELECT v.{column}, d.kind FROM {table} v JOIN datasets d ON d.id = v.dataset_id"
        ):
            if row[0]:
                path = Path(row[0])
                if row[1] == "returns":
                    files.add(path)
                else:
                    retained.add(path.resolve())
    for table, columns in (
        ("tasks", "result_file_path, results_json_path"),
        ("task_segments", "result_file_path, result_json_path"),
        ("dataset_import_staging", "temp_path"),
    ):
        for row in connection.execute(f"SELECT {columns} FROM {table}"):
            files.update(Path(value) for value in row if value)
    return [_file_entry(path, root, retained) for path in sorted(files)]


def _file_entry(
    path: Path,
    root: Path,
    retained: set[Path],
) -> dict[str, Any]:
    resolved = path.resolve()
    allowed = any(
        resolved.is_relative_to(root / directory)
        for directory in ("results", "uploads", "imports", "tmp")
    ) or (resolved.parent == root / "cache" and resolved.suffix == ".jsonl")
    if not allowed or resolved in retained:
        raise ValueError("产物文件越界或仍被保留的数据引用，拒绝清理")
    if any(parent.is_symlink() for parent in (path, *path.parents) if parent != root):
        raise ValueError("产物路径包含符号链接，拒绝清理")
    stat = path.stat() if path.exists() else None
    return {
        "path": resolved.relative_to(root).as_posix(),
        "size": stat.st_size if stat else None,
        "mtime_ns": stat.st_mtime_ns if stat else None,
        "sha256": _sha256_file(path) if stat else None,
    }


def remove_cleanup_files(data_dir: Path, files: list[dict[str, Any]]) -> list[str]:
    """数据库提交后逐文件清理；失败路径单独返回，避免掩盖部分完成。"""
    failed = []
    for item in files:
        try:
            root = data_dir.resolve()
            path = root / item["path"]
            _file_entry(path, root, set())
            path.unlink(missing_ok=True)
        except (OSError, ValueError):
            failed.append(item["path"])
    return failed
