from __future__ import annotations

import secrets
import sqlite3
from pathlib import Path


def migrate_ai_insight_reports(connection: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in connection.execute(
            "PRAGMA table_info(ai_insight_reports)"
        ).fetchall()
    }
    definitions = {
        "stage": "TEXT NOT NULL DEFAULT 'queued'",
        "technical_error": "TEXT",
        "parent_job_id": "TEXT REFERENCES ai_insight_reports(id)",
    }
    for column_name, definition in definitions.items():
        if column_name not in columns:
            connection.execute(
                f"ALTER TABLE ai_insight_reports ADD COLUMN {column_name} {definition}"
            )
    connection.execute(
        """
            UPDATE ai_insight_reports
            SET stage = CASE status
                WHEN 'queued' THEN 'queued'
                WHEN 'running' THEN 'preparing_evidence'
                WHEN 'completed' THEN 'completed'
                WHEN 'failed' THEN 'failed'
                ELSE stage
            END
            WHERE stage IS NULL OR stage = ''
               OR (stage = 'queued' AND status != 'queued')
            """
    )
    connection.execute(
        """
            UPDATE ai_insight_reports
            SET technical_error = COALESCE(technical_error, error),
                error = '报告生成未完成，请稍后重试。失败尝试已保留，且不会占用报告版本号。'
            WHERE status = 'failed'
              AND error IS NOT NULL
              AND error != '报告生成未完成，请稍后重试。失败尝试已保留，且不会占用报告版本号。'
            """
    )
    completed_rows = connection.execute(
        """
            SELECT report.id, report.dashboard_id,
                   report.dashboard_version_id, report.completed_at,
                   report.created_at
            FROM ai_insight_reports report
            LEFT JOIN ai_insight_report_versions version
              ON version.job_id = report.id
            WHERE report.status = 'completed' AND version.id IS NULL
            ORDER BY report.dashboard_id,
                     COALESCE(report.completed_at, report.created_at),
                     report.id
            """
    ).fetchall()
    next_versions: dict[str, int] = {}
    for row in completed_rows:
        dashboard_id = str(row["dashboard_id"])
        if dashboard_id not in next_versions:
            next_versions[dashboard_id] = int(
                connection.execute(
                    """
                        SELECT COALESCE(MAX(version_no), 0) + 1
                        FROM ai_insight_report_versions
                        WHERE dashboard_id = ?
                        """,
                    (dashboard_id,),
                ).fetchone()[0]
            )
        version_no = next_versions[dashboard_id]
        next_versions[dashboard_id] += 1
        connection.execute(
            """
                INSERT INTO ai_insight_report_versions(
                    id, job_id, dashboard_id, dashboard_version_id,
                    version_no, published_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
            (
                f"insight_report_version_{secrets.token_hex(8)}",
                row["id"],
                dashboard_id,
                row["dashboard_version_id"],
                version_no,
                row["completed_at"] or row["created_at"],
            ),
        )


def repair_draft_review_batches(connection: sqlite3.Connection) -> None:
    missing_records = connection.execute(
        """
            SELECT b.id AS batch_id, b.base_result_version_id,
                   b.updated_at, result.source_task_id,
                   unit.classification_key, unit.comment,
                   unit.classification_json
            FROM review_batches b
            JOIN classification_results result ON result.id = b.result_id
            JOIN classification_units unit
              ON unit.result_version_id = b.base_result_version_id
            LEFT JOIN review_records review
              ON review.batch_id = b.id
             AND review.classification_key = unit.classification_key
            WHERE b.status = 'draft'
              AND unit.quality_status != 'ready'
              AND review.id IS NULL
            ORDER BY b.id, unit.classification_key
            """
    ).fetchall()
    if not missing_records:
        return
    connection.executemany(
        """
            INSERT INTO review_records(
                id, task_id, batch_id, base_result_version_id,
                classification_key, comment, workflow_status,
                classification_json, revision, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, 1, ?)
            """,
        [
            (
                f"review_{secrets.token_hex(8)}",
                row["source_task_id"],
                row["batch_id"],
                row["base_result_version_id"],
                row["classification_key"],
                str(row["comment"] or ""),
                row["classification_json"],
                row["updated_at"],
            )
            for row in missing_records
        ],
    )


def repair_missing_empty_checkpoint_references(
    connection: sqlite3.Connection,
) -> int:
    """清理从未产生结果且检查点文件不存在的历史路径。"""
    rows = connection.execute(
        """
        SELECT id, result_json_path
        FROM task_segments
        WHERE result_json_path IS NOT NULL
          AND TRIM(result_json_path) <> ''
          AND result_version = 0
          AND progress_current = 0
          AND model_calls = 0
          AND cache_hits = 0
          AND model_failures = 0
          AND result_publish_status IS NULL
          AND status IN ('cancelled', 'paused', 'failed', 'retry_pending')
        """
    ).fetchall()
    stale_ids = [
        str(row["id"])
        for row in rows
        if not Path(str(row["result_json_path"])).is_file()
    ]
    if stale_ids:
        connection.executemany(
            "UPDATE task_segments SET result_json_path = NULL WHERE id = ?",
            ((segment_id,) for segment_id in stale_ids),
        )
    return len(stale_ids)
