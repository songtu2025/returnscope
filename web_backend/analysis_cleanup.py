"""供维护负责人使用的分析数据清理入口，默认只读预览。"""

from __future__ import annotations

import hashlib
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from web_backend.analysis_cleanup_files import remove_cleanup_files
from web_backend.analysis_cleanup_plan import CleanupPlan, build_cleanup_plan
from web_backend.backup import verify_backup
from web_backend.common import insert_audit, new_id


@dataclass(frozen=True)
class CleanupApproval:
    preview_hash: str
    backup_path: Path
    actor_id: str
    app_stopped: bool


def _connect(database_path: Path, *, apply: bool) -> sqlite3.Connection:
    mode = "rw" if apply else "ro"
    connection = sqlite3.connect(
        f"{database_path.resolve().as_uri()}?mode={mode}",
        uri=True,
        isolation_level=None,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    if not apply:
        connection.execute("PRAGMA query_only = ON")
    return connection


def preview_cleanup(
    database_path: Path,
    data_dir: Path,
) -> CleanupPlan:
    with closing(_connect(database_path, apply=False)) as connection:
        connection.execute("BEGIN")
        return build_cleanup_plan(connection, data_dir)


def apply_cleanup(
    database_path: Path,
    data_dir: Path,
    *,
    approval: CleanupApproval,
) -> dict[str, Any]:
    if not approval.app_stopped:
        raise ValueError("必须由维护负责人确认应用已停止")
    plan = preview_cleanup(database_path, data_dir)
    if not approval.preview_hash or plan.preview_hash != approval.preview_hash:
        raise ValueError("清理范围已变化，请重新预览并确认")
    _validate_backup(approval.backup_path, data_dir, plan)
    with closing(_connect(database_path, apply=True)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            actor = connection.execute(
                "SELECT 1 FROM users WHERE id = ? AND active = 1 AND is_admin = 1",
                (approval.actor_id,),
            ).fetchone()
            if actor is None:
                raise ValueError("清理操作必须指定启用的管理员")
            if list(connection.execute("PRAGMA foreign_key_check")):
                raise ValueError("数据库存在外键异常，拒绝清理")
            current = build_cleanup_plan(connection, data_dir)
            if current.preview_hash != approval.preview_hash:
                raise ValueError("清理范围已变化，请重新预览并确认")
            # 派生版本和重试记录有同批次内部引用，提交时统一验证外键。
            connection.execute("PRAGMA defer_foreign_keys = ON")
            _delete_records(connection, current)
            if list(connection.execute("PRAGMA foreign_key_check")):
                raise ValueError("清理将破坏保留数据的引用，操作已回滚")
            remaining = build_cleanup_plan(connection, data_dir)
            if remaining.protected_counts != current.protected_counts:
                raise ValueError("清理影响了保留数据，操作已回滚")
            insert_audit(
                connection,
                "analysis_cleanup",
                new_id("cleanup"),
                "purge",
                approval.actor_id,
                after=current.summary(),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    failed_files = remove_cleanup_files(data_dir, current.files)
    return {
        **current.summary(),
        "database_applied": True,
        "failed_files": failed_files,
        "complete": not failed_files,
    }


def _validate_backup(backup_path: Path, data_dir: Path, plan: CleanupPlan) -> None:
    verify_backup(backup_path)
    with zipfile.ZipFile(backup_path) as archive:
        # tmp 仅存放临时文件检查产物，不属于现有业务备份的恢复范围。
        required = {
            item["path"]
            for item in plan.files
            if item["size"] is not None and not item["path"].startswith("tmp/")
        }
        if not required.issubset(archive.namelist()):
            raise ValueError("备份未包含全部待清理文件")
        if any(
            archive.getinfo(item["path"]).file_size != item["size"]
            for item in plan.files
            if item["size"] is not None and not item["path"].startswith("tmp/")
        ):
            raise ValueError("备份产物与当前文件不一致")
        for item in plan.files:
            if item["size"] is not None and not item["path"].startswith("tmp/"):
                with archive.open(item["path"]) as source:
                    digest = hashlib.sha256()
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        digest.update(chunk)
                    if digest.hexdigest() != item["sha256"]:
                        raise ValueError("备份产物内容与当前文件不一致")
        with tempfile.TemporaryDirectory(
            prefix="analysis-cleanup-backup-"
        ) as temporary:
            database = Path(temporary) / "app.db"
            database.write_bytes(archive.read("app.db"))
            backed_up = preview_cleanup(database, data_dir)
            if backed_up.preview_hash != plan.preview_hash:
                raise ValueError("备份数据与当前清理范围不一致，请重新备份")


def _delete_records(connection: sqlite3.Connection, plan: CleanupPlan) -> None:
    for table in plan.rows:
        connection.executemany(
            f"DELETE FROM {table} WHERE rowid = ?",
            [(row_id,) for row_id in plan.rows[table]],
        )
