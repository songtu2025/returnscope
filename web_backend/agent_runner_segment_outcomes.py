from __future__ import annotations

from pathlib import Path
from typing import Callable

from return_semantics.data import ReturnDataset
from return_semantics.pipeline import PipelineRun
from return_semantics.schemas import TaxonomyConfig, ValidatedClassification
from web_backend.classification_result_service import ClassificationResultService
from web_backend.common import json_text
from web_backend.database import Database
from web_backend.security import utc_now


class SegmentOutcomesMixin:
    database: Database
    result_service: ClassificationResultService
    _refresh_parent: Callable[..., None]
    _results_have_quality_errors: Callable[..., bool]
    _write_checkpoint: Callable[..., None]

    def _complete_segment(
        self,
        task_id: str,
        segment_id: str,
        status: str,
        progress_total: int,
        model_calls: int,
        cache_hits: int,
        checkpoint_path: Path,
        result_version: int,
        dataset: ReturnDataset,
        results: dict[str, ValidatedClassification],
        taxonomy: TaxonomyConfig,
        model_failures: int = 0,
    ) -> None:
        self.result_service.publish_v1(
            task_id=task_id,
            segment_id=segment_id,
            dataset=dataset,
            results=results,
            taxonomy=taxonomy,
            segment_status=status,
            progress_total=progress_total,
            model_calls=model_calls,
            cache_hits=cache_hits,
            model_failures=model_failures,
            checkpoint_path=str(checkpoint_path),
            legacy_result_version=result_version,
        )

    def _save_partial_checkpoint(
        self,
        checkpoint_path: Path,
        existing_results: dict[str, ValidatedClassification],
        latest_run: PipelineRun | None,
    ) -> dict[str, ValidatedClassification]:
        partial_results = {
            **existing_results,
            **(latest_run.classifications if latest_run else {}),
        }
        if partial_results:
            self._write_checkpoint(checkpoint_path, partial_results)
        return partial_results

    def _finish_interrupted_segment(
        self,
        task_id: str,
        segment_id: str,
        existing_results: dict[str, ValidatedClassification],
        latest_run: PipelineRun | None,
        checkpoint_path: Path,
        model_calls: int,
        cache_hits: int,
        model_failures: int,
    ) -> None:
        partial_results = self._save_partial_checkpoint(
            checkpoint_path,
            existing_results,
            latest_run,
        )
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute(
                """
                SELECT s.requested_action, t.cancel_requested, t.pause_requested
                FROM task_segments s
                JOIN tasks t ON t.id = s.task_id
                WHERE s.id = ? AND s.task_id = ?
                """,
                (segment_id, task_id),
            ).fetchone()
            requested = str(row["requested_action"] or "") if row else ""
            if requested == "cancel" or (row and row["cancel_requested"]):
                status = "cancelled"
                message = "Listing 已取消，完成片段不受影响"
            elif requested == "pause" or (row and row["pause_requested"]):
                status = "paused"
                message = "Listing 已保存检查点并暂停"
            else:
                status = "retry_pending"
                message = "Listing 已中断，等待从检查点恢复"
            connection.execute(
                """
                UPDATE task_segments
                SET status = ?, progress_current = ?,
                    model_calls = ?, cache_hits = ?, model_failures = ?,
                    requested_action = NULL, result_json_path = ?,
                    started_at = CASE WHEN ? = 'retry_pending' THEN NULL
                                      ELSE started_at END,
                    completed_at = CASE WHEN ? = 'cancelled' THEN ? ELSE NULL END,
                    heartbeat_at = ?, revision = revision + 1
                WHERE id = ? AND task_id = ?
                """,
                (
                    status,
                    len(partial_results),
                    model_calls,
                    cache_hits,
                    model_failures,
                    str(checkpoint_path),
                    status,
                    status,
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
                ) VALUES (?, ?, '语义分析', ?, ?, ?)
                """,
                (
                    task_id,
                    f"segment_{status}",
                    message,
                    json_text({"segment_id": segment_id}),
                    now,
                ),
            )
        self._refresh_parent(task_id)

    def _finish_model_service_paused(
        self,
        task_id: str,
        segment_id: str,
        error: str,
        existing_results: dict[str, ValidatedClassification],
        latest_run: PipelineRun | None,
        checkpoint_path: Path,
        model_calls: int,
        cache_hits: int,
        model_failures: int,
    ) -> None:
        partial_results = self._save_partial_checkpoint(
            checkpoint_path,
            existing_results,
            latest_run,
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
                    str(checkpoint_path),
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
                (message, error[:2000], now, task_id),
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
                            "error": error[:500],
                        }
                    ),
                    now,
                ),
            )
        self._refresh_parent(task_id)

    def _finish_failed_segment(
        self,
        task_id: str,
        segment_id: str,
        error: str,
        latest_run: PipelineRun | None,
        checkpoint_path: Path,
        existing_results: dict[str, ValidatedClassification],
        model_calls: int,
        cache_hits: int,
        model_failures: int,
    ) -> None:
        partial_results = self._save_partial_checkpoint(
            checkpoint_path,
            existing_results,
            latest_run,
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
                    error[:2000],
                    str(checkpoint_path),
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
                    error[:500],
                    json_text({"segment_id": segment_id}),
                    now,
                ),
            )
        self._refresh_parent(task_id)

    def _finish_result_publish_failed_segment(
        self,
        task_id: str,
        segment_id: str,
        error: str,
        latest_run: PipelineRun | None,
        checkpoint_path: Path,
        existing_results: dict[str, ValidatedClassification],
        model_calls: int,
        cache_hits: int,
        model_failures: int,
    ) -> None:
        results = self._save_partial_checkpoint(
            checkpoint_path,
            existing_results,
            latest_run,
        )
        status = (
            "completed_with_errors"
            if self._results_have_quality_errors(results)
            else "completed"
        )
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                UPDATE task_segments
                SET status = ?, progress_current = progress_total,
                    model_calls = ?, cache_hits = ?, model_failures = ?,
                    error = NULL, requested_action = NULL,
                    result_json_path = ?, result_publish_status = 'failed',
                    result_publish_error = COALESCE(result_publish_error, ?),
                    completed_at = ?, heartbeat_at = ?, revision = revision + 1
                WHERE id = ? AND task_id = ?
                """,
                (
                    status,
                    model_calls,
                    cache_hits,
                    model_failures,
                    str(checkpoint_path),
                    error[:500],
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
                ) VALUES (?, 'segment_classified_publish_failed', '生成结果',
                          'Listing 语义分类已完成，但结果发布失败', ?, ?)
                """,
                (
                    task_id,
                    json_text({"segment_id": segment_id, "error": error[:500]}),
                    now,
                ),
            )
        self._refresh_parent(task_id)
