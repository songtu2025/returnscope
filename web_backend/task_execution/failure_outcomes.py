from __future__ import annotations

from collections.abc import Callable

from return_semantics.schemas import ValidatedClassification
from web_backend.common import json_text
from web_backend.database import Database
from web_backend.security import utc_now
from web_backend.task_execution.contracts import (
    TASK_ERROR_TEXT_LIMIT,
    TASK_EVENT_ERROR_TEXT_LIMIT,
    _SegmentRunContext,
)


class SegmentFailureOutcomesMixin:
    _refresh_parent: Callable[..., None]
    _save_partial_checkpoint: Callable[
        ..., tuple[dict[str, ValidatedClassification], str | None]
    ]
    database: Database

    def _finish_model_service_paused(
        self,
        context: _SegmentRunContext,
        error: str,
    ) -> None:
        task_id = context.task_id
        segment_id = context.segment_id
        model_calls, cache_hits, model_failures = context.runtime_totals()
        partial_results, checkpoint_reference = self._save_partial_checkpoint(
            context.checkpoint_path,
            context.existing_results,
            context.latest_run,
        )
        now = utc_now()
        message = "模型服务连续失败，任务已自动暂停；请检查连接后继续执行"
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                UPDATE task_segments
                SET status = 'paused', progress_current = ?,
                    model_calls = ?, cache_hits = ?, model_failures = ?,
                    error = ?, requested_action = NULL, result_json_path = ?,
                    heartbeat_at = ?, revision = revision + 1
                WHERE id = ? AND task_id = ?
                """,
                (
                    len(partial_results),
                    model_calls,
                    cache_hits,
                    model_failures,
                    message,
                    checkpoint_reference,
                    now,
                    segment_id,
                    task_id,
                ),
            )
            connection.execute(
                """
                UPDATE task_segments
                SET status = 'paused', requested_action = NULL,
                    revision = revision + 1
                WHERE task_id = ? AND id != ?
                  AND status IN ('queued', 'retry_pending')
                """,
                (task_id, segment_id),
            )
            connection.execute(
                """
                UPDATE task_segments
                SET requested_action = 'pause', revision = revision + 1
                WHERE task_id = ? AND id != ? AND status = 'running'
                """,
                (task_id, segment_id),
            )
            connection.execute(
                """
                UPDATE tasks
                SET pause_requested = 1, stage = '模型服务异常',
                    message = ?, error = ?, heartbeat_at = ?,
                    revision = revision + 1
                WHERE id = ?
                """,
                (message, error[:TASK_ERROR_TEXT_LIMIT], now, task_id),
            )
            connection.execute(
                """
                INSERT INTO task_events(
                    task_id, event_type, stage, message, data_json, created_at
                ) VALUES (?, 'model_service_paused', '模型服务异常', ?, ?, ?)
                """,
                (
                    task_id,
                    message,
                    json_text(
                        {
                            "segment_id": segment_id,
                            "model_failures": model_failures,
                            "error": error[:TASK_EVENT_ERROR_TEXT_LIMIT],
                        }
                    ),
                    now,
                ),
            )
        self._refresh_parent(task_id)

    def _finish_failed_segment(
        self,
        context: _SegmentRunContext,
        error: str,
    ) -> None:
        task_id = context.task_id
        segment_id = context.segment_id
        model_calls, cache_hits, model_failures = context.runtime_totals()
        partial_results, checkpoint_reference = self._save_partial_checkpoint(
            context.checkpoint_path,
            context.existing_results,
            context.latest_run,
        )
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                UPDATE task_segments
                SET status = 'failed', progress_current = ?,
                    model_calls = ?, cache_hits = ?, model_failures = ?,
                    error = ?, requested_action = NULL, result_json_path = ?,
                    completed_at = ?, heartbeat_at = ?, revision = revision + 1
                WHERE id = ? AND task_id = ?
                """,
                (
                    len(partial_results),
                    model_calls,
                    cache_hits,
                    model_failures,
                    error[:TASK_ERROR_TEXT_LIMIT],
                    checkpoint_reference,
                    now,
                    now,
                    segment_id,
                    task_id,
                ),
            )
            connection.execute(
                """
                INSERT INTO task_events(
                    task_id, event_type, stage, message, data_json, created_at
                ) VALUES (?, 'segment_failed', '运行失败', ?, ?, ?)
                """,
                (
                    task_id,
                    error[:TASK_EVENT_ERROR_TEXT_LIMIT],
                    json_text({"segment_id": segment_id}),
                    now,
                ),
            )
        self._refresh_parent(task_id)
