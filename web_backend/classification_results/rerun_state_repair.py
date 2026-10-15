"""显式修复历史派生状态；预览不写入，不由应用启动自动调用。"""

from __future__ import annotations

import argparse
import hashlib
import sqlite3
from typing import Any

from return_semantics.semantic_review import (
    BUSINESS_REVIEW_REQUIRED,
    SYSTEM_RERUN_REQUIRED,
    review_route,
)
from web_backend.backup import create_backup, verify_backup
from web_backend.classification_result_payload import _version_quality
from web_backend.classification_results.effective_content import (
    business_hash,
    load_content,
)
from web_backend.common import json_value
from web_backend.dashboards.live_sources import refresh_related_dashboards
from web_backend.database import Database
from web_backend.result_hierarchy import result_taxonomy
from web_backend.security import utc_now
from web_backend.settings import Settings

MIGRATION_ID = "20261014_execution_failure_rerun_policy"
MIGRATION_CHECKSUM = hashlib.sha256(b"execution_failure_rerun_policy:v1").hexdigest()


def preview_changes(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    """复用实时判定，仅收集需要修正的派生字段，不修改原始语义。"""
    rows = connection.execute("SELECT * FROM classification_units").fetchall()
    taxonomies = {}
    changes = []
    for row in rows:
        version_id = str(row["result_version_id"])
        if version_id not in taxonomies:
            taxonomies[version_id] = result_taxonomy(connection, version_id)
        route = review_route(
            json_value(row["classification_json"], {}),
            str(row["comment"] or ""),
            taxonomies[version_id],
            processing_status=str(row["processing_status"] or ""),
        )
        quality = (
            "excluded"
            if row["quality_status"] == "excluded"
            else "unusable"
            if route == SYSTEM_RERUN_REQUIRED
            else "review_required"
            if route == BUSINESS_REVIEW_REQUIRED
            else "ready"
        )
        rerun = int(route == SYSTEM_RERUN_REQUIRED and quality != "excluded")
        if (rerun, quality) != (row["system_rerun_required"], row["quality_status"]):
            changes.append(
                {
                    "id": row["id"],
                    "version_id": version_id,
                    "classification_key": row["classification_key"],
                    "rerun": rerun,
                    "quality": quality,
                }
            )
    return changes


def repair_states(database: Database, *, apply: bool = False) -> dict[str, int]:
    with database.transaction(immediate=apply) as connection:
        migration = connection.execute(
            "SELECT checksum FROM app_migrations WHERE migration_id = ?",
            (MIGRATION_ID,),
        ).fetchone()
        # 预览始终反映当前差异，执行记录只约束修复写入。
        if apply and migration:
            if migration["checksum"] != MIGRATION_CHECKSUM:
                raise ValueError("重跑状态修复校验不一致")
            return {"units": 0, "versions": 0}
        changes = preview_changes(connection)
        versions = {item["version_id"] for item in changes}
        summary = {"units": len(changes), "versions": len(versions)}
        if not apply:
            return summary
        for item in changes:
            connection.execute(
                "UPDATE classification_units SET system_rerun_required = ?, quality_status = ? WHERE id = ?",
                (item["rerun"], item["quality"], item["id"]),
            )
            connection.execute(
                "UPDATE classification_result_records SET quality_status = ? "
                "WHERE result_version_id = ? AND classification_key = ? AND quality_status != 'excluded'",
                (item["quality"], item["version_id"], item["classification_key"]),
            )
        now = utc_now()
        result_ids = set()
        for version_id in versions:
            result_ids.add(_refresh_version(connection, version_id))
        for result_id in result_ids:
            refresh_related_dashboards(database, connection, result_id, now)
        connection.execute(
            "INSERT INTO app_migrations(migration_id, checksum, status, applied_at) VALUES (?, ?, 'applied', ?)",
            (MIGRATION_ID, MIGRATION_CHECKSUM, now),
        )
        return summary


def _refresh_version(connection: sqlite3.Connection, version_id: str) -> str:
    content = load_content(connection, version_id)
    quality = _version_quality(
        [
            item["quality_status"]
            for item in content["records"]
            if item["quality_status"] != "excluded"
        ]
    )
    connection.execute(
        "UPDATE classification_result_versions SET quality_status = ?, content_hash = ? WHERE id = ?",
        (quality, business_hash(content), version_id),
    )
    connection.execute(
        "UPDATE task_segments SET result_quality_status = ?, revision = revision + 1 WHERE result_version_id = ?",
        (quality, version_id),
    )
    row = connection.execute(
        "SELECT result_id FROM classification_result_versions WHERE id = ?",
        (version_id,),
    ).fetchone()
    return str(row["result_id"])


def main() -> None:
    parser = argparse.ArgumentParser(description="预览或修复历史重跑状态")
    parser.add_argument("--apply", action="store_true", help="备份校验通过后执行修复")
    parser.add_argument(
        "--app-stopped", action="store_true", help="确认应用和任务工作进程已停止"
    )
    arguments = parser.parse_args()
    if arguments.apply and not arguments.app_stopped:
        parser.error("执行修复前必须停止应用及任务工作进程，并传入 --app-stopped")
    settings = Settings.from_env()
    if not settings.database_path.is_file():
        parser.error("数据库不存在")
    if arguments.apply:
        backup = create_backup(settings)
        verify_backup(backup)
        print(f"修复前备份及校验通过：{backup}")
    result = repair_states(Database(settings.database_path), apply=arguments.apply)
    print(
        f"{'已修复' if arguments.apply else '预览'}：{result['units']} 个分类单元，{result['versions']} 个结果版本"
    )


if __name__ == "__main__":
    main()
