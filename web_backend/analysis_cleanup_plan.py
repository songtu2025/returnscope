"""盘点全部历史分析业务数据；商品、标准规则与账号配置不参与清理。"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from web_backend.analysis_cleanup_files import inventory_files
from web_backend.common import json_text
from web_backend.task_contracts import FINAL_STATUSES

# 按子表到父表排列，显式列出范围，禁止按名称猜测要清理的表。
ANALYSIS_TABLES = (
    "ai_insight_issue_decisions",
    "ai_insight_report_versions",
    "ai_insight_reports",
    "dashboard_dataset_sources",
    "dashboard_versions",
    "dashboard_dataset_versions",
    "analysis_dashboards",
    "review_revisions",
    "review_records",
    "review_batches",
    "classification_unit_labels",
    "classification_unit_semantics",
    "classification_result_records",
    "classification_units",
    "classification_result_versions",
    "classification_results",
    "task_events",
    "task_segments",
    "tasks",
    "classification_standard_validation_runs",
    "dataset_import_staging",
)
ANALYSIS_AUDIT_TYPES = (
    "task",
    "task_segment",
    "classification_result",
    "classification_result_version",
    "review",
    "review_batch",
    "analysis_dashboard",
    "ai_insight_report",
    "ai_insight_issue_decision",
    "classification_standard_validation",
)
PROTECTED_TABLES = (
    "users",
    "sessions",
    "api_connections",
    "api_config_versions",
    "api_models",
    "api_validation_runs",
    "api_validation_events",
    "user_model_preferences",
    "classification_standards",
    "classification_standard_versions",
    "classification_standard_drafts",
    "app_migrations",
)


@dataclass(frozen=True)
class CleanupPlan:
    task_ids: tuple[str, ...]
    rows: dict[str, list[int]]
    files: list[dict[str, Any]]
    protected_counts: dict[str, int]
    preview_hash: str

    def summary(self) -> dict[str, Any]:
        return {
            "scope": "all-analysis",
            "task_ids": self.task_ids,
            "counts": {table: len(rows) for table, rows in self.rows.items()},
            "protected_counts": self.protected_counts,
            "file_count": len(self.files),
            "file_bytes": sum(item["size"] or 0 for item in self.files),
            "temporary_file_count": sum(
                item["path"].startswith("tmp/") for item in self.files
            ),
            "preview_hash": self.preview_hash,
        }


def _check_idle(connection: sqlite3.Connection) -> None:
    if any(
        row[0] not in FINAL_STATUSES
        for row in connection.execute("SELECT status FROM tasks")
    ):
        raise ValueError("任务尚未结束，请先通过正常流程结束执行")
    allowed = {"completed", "completed_with_errors", "cancelled", "failed"}
    if any(
        row[0] not in allowed
        for row in connection.execute("SELECT status FROM task_segments")
    ):
        raise ValueError("任务片段尚未结束")
    for table, label in (
        ("ai_insight_reports", "AI 洞察"),
        ("classification_standard_validation_runs", "分类标准验证"),
    ):
        if connection.execute(
            f"SELECT 1 FROM {table} WHERE status IN ('queued', 'running') LIMIT 1"
        ).fetchone():
            raise ValueError(f"{label}尚未结束")
    if list(connection.execute("PRAGMA foreign_key_check")):
        raise ValueError("数据库存在外键异常，拒绝清理")


def build_cleanup_plan(connection: sqlite3.Connection, data_dir: Path) -> CleanupPlan:
    _check_idle(connection)
    rows = {
        table: [
            row[0]
            for row in connection.execute(f"SELECT rowid FROM {table} ORDER BY rowid")
        ]
        for table in ANALYSIS_TABLES
    }
    conditions = {
        "dataset_imports": "dataset_id IN (SELECT id FROM datasets WHERE kind = 'returns')",
        "dataset_versions": "dataset_id IN (SELECT id FROM datasets WHERE kind = 'returns')",
        "datasets": "kind = 'returns'",
    }
    for table, condition in conditions.items():
        rows[table] = [
            row[0]
            for row in connection.execute(
                f"SELECT rowid FROM {table} WHERE {condition} ORDER BY rowid"
            )
        ]
    placeholders = ",".join("?" for _ in ANALYSIS_AUDIT_TYPES)
    rows["audit_logs"] = [
        row[0]
        for row in connection.execute(
            f"SELECT rowid FROM audit_logs WHERE entity_type IN ({placeholders}) OR (entity_type = 'dataset' AND entity_id IN (SELECT id FROM datasets WHERE kind = 'returns')) ORDER BY rowid",
            ANALYSIS_AUDIT_TYPES,
        )
    ]
    protected = {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in PROTECTED_TABLES
    }
    for table, condition in conditions.items():
        protected[table] = connection.execute(
            f"SELECT COUNT(*) FROM {table} WHERE NOT ({condition})"
        ).fetchone()[0]
    files = inventory_files(connection, data_dir)
    # 仅读取版本、状态与时间等维护元数据，预览不读取业务正文或认证凭据。
    metadata = {}
    for table in (*ANALYSIS_TABLES, *conditions):
        columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        fields = [
            name
            for name in (
                "id",
                "revision",
                "status",
                "content_hash",
                "updated_at",
                "created_at",
                "current_version",
            )
            if name in columns
        ]
        condition = f" WHERE {conditions[table]}" if table in conditions else ""
        metadata[table] = (
            [
                tuple(row)
                for row in connection.execute(
                    f"SELECT {','.join(fields)} FROM {table}{condition} ORDER BY rowid"
                )
            ]
            if fields
            else []
        )
    task_ids = tuple(
        row[0] for row in connection.execute("SELECT id FROM tasks ORDER BY id")
    )
    payload = {
        "scope": "all-analysis",
        "rows": rows,
        "metadata": metadata,
        "files": files,
        "protected": protected,
    }
    digest = hashlib.sha256(json_text(payload).encode("utf-8")).hexdigest()
    return CleanupPlan(task_ids, rows, files, protected, digest)
