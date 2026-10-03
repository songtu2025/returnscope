from __future__ import annotations

from typing import Any

from web_backend.common import json_text
from web_backend.database import Database
from web_backend.security import utc_now


class SegmentStateMixin:
    database: Database

    def _load_segment(self, segment_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM task_segments WHERE id = ?",
                (segment_id,),
            ).fetchone()
        return dict(row) if row else None

    def _load_segments(self, task_id: str) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM task_segments
                WHERE task_id = ? ORDER BY execution_order, segment_key
                """,
                (task_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _segment_should_stop(self, task_id: str, segment_id: str) -> bool:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT s.requested_action, t.cancel_requested, t.pause_requested
                FROM task_segments s
                JOIN tasks t ON t.id = s.task_id
                WHERE s.id = ? AND s.task_id = ?
                """,
                (segment_id, task_id),
            ).fetchone()
        return bool(
            row
            and (
                row["requested_action"]
                or row["cancel_requested"]
                or row["pause_requested"]
            )
        )

    def _update_segment_progress(
        self,
        task_id: str,
        segment_id: str,
        current: int,
        total: int,
    ) -> None:
        now = utc_now()
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE task_segments
                SET progress_current = ?, progress_total = ?, heartbeat_at = ?
                WHERE id = ? AND status = 'running'
                """,
                (current, total, now, segment_id),
            )
            totals = connection.execute(
                """
                SELECT COALESCE(SUM(progress_current), 0) AS current,
                       COALESCE(SUM(progress_total), 0) AS total
                FROM task_segments
                WHERE task_id = ? AND agent_key != 'unknown'
                """,
                (task_id,),
            ).fetchone()
            task_current = int(totals["current"])
            task_total = int(totals["total"])
            percent = round(task_current / task_total * 100, 2) if task_total else 0
            connection.execute(
                """
                UPDATE tasks
                SET progress_current = ?, progress_total = ?,
                    progress_percent = ?, heartbeat_at = ?
                WHERE id = ?
                """,
                (task_current, task_total, percent, now, task_id),
            )
            connection.execute(
                """
                INSERT INTO task_events(
                    task_id, event_type, stage, message,
                    progress_current, progress_total, data_json, created_at
                ) VALUES (?, 'segment_progress', '语义分析', ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    f"Listing 已完成 {current}/{total} 组评论",
                    task_current,
                    task_total,
                    json_text({"segment_id": segment_id}),
                    now,
                ),
            )

    def _update_segment_runtime_metrics(
        self,
        segment_id: str,
        model_calls: int,
        cache_hits: int,
        model_failures: int,
    ) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE task_segments
                SET model_calls = MAX(model_calls, ?),
                    cache_hits = MAX(cache_hits, ?),
                    model_failures = MAX(model_failures, ?)
                WHERE id = ? AND status = 'running'
                """,
                (model_calls, cache_hits, model_failures, segment_id),
            )

    def _record_model_degraded(
        self,
        task_id: str,
        segment_id: str,
        error: str,
        consecutive_failures: int,
    ) -> None:
        now = utc_now()
        message = (
            f"模型服务已连续失败 {consecutive_failures} 次，正在重试；"
            "达到 5 次将自动暂停"
        )
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                UPDATE task_segments
                SET error = ?, heartbeat_at = ?, revision = revision + 1
                WHERE id = ? AND task_id = ? AND status = 'running'
                """,
                (message, now, segment_id, task_id),
            )
            connection.execute(
                """
                UPDATE tasks
                SET stage = '模型服务异常', message = ?, heartbeat_at = ?,
                    revision = revision + 1
                WHERE id = ?
                """,
                (message, now, task_id),
            )
            connection.execute(
                """
                INSERT INTO task_events(
                    task_id, event_type, stage, message, data_json, created_at
                ) VALUES (?, 'model_service_degraded', '模型服务异常', ?, ?, ?)
                """,
                (
                    task_id,
                    message,
                    json_text(
                        {
                            "segment_id": segment_id,
                            "consecutive_failures": consecutive_failures,
                            "error": error[:500],
                        }
                    ),
                    now,
                ),
            )
