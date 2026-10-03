from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from return_semantics.data import ReturnDataset
from return_semantics.pipeline import PipelineRun
from return_semantics.schemas import TaxonomyConfig, ValidatedClassification
from web_backend.classification_result_publication import SegmentPublicationState
from web_backend.classification_result_service import ClassificationResultService
from web_backend.common import json_text
from web_backend.database import Database
from web_backend.security import utc_now
from web_backend.task_execution.failure_outcomes import SegmentFailureOutcomesMixin

if TYPE_CHECKING:
    from web_backend.agent_runner_segment_execution import _SegmentRunContext


class SegmentOutcomesMixin(SegmentFailureOutcomesMixin):
    _refresh_parent: Callable[..., None]
    _results_have_quality_errors: Callable[..., bool]
    _write_checkpoint: Callable[..., None]
    database: Database
    result_service: ClassificationResultService

    def _complete_segment(
        self,
        context: _SegmentRunContext,
        dataset: ReturnDataset,
        results: dict[str, ValidatedClassification],
        taxonomy: TaxonomyConfig,
        result_version: int,
    ) -> None:
        model_calls, cache_hits, model_failures = context.runtime_totals()
        self.result_service.publish_v1(
            dataset=dataset,
            results=results,
            taxonomy=taxonomy,
            segment_state=SegmentPublicationState(
                task_id=context.task_id,
                segment_id=context.segment_id,
                segment_status="completed_with_errors"
                if self._results_have_quality_errors(results)
                else "completed",
                progress_total=len(results),
                model_calls=model_calls,
                cache_hits=cache_hits,
                model_failures=model_failures,
                checkpoint_path=str(context.checkpoint_path),
                legacy_result_version=result_version,
            ),
        )

    def _save_partial_checkpoint(
        self,
        checkpoint_path: Path,
        existing_results: dict[str, ValidatedClassification],
        latest_run: PipelineRun | None,
    ) -> tuple[dict[str, ValidatedClassification], str | None]:
        partial_results = {
            **existing_results,
            **(latest_run.classifications if latest_run else {}),
        }
        if partial_results:
            self._write_checkpoint(checkpoint_path, partial_results)
            return partial_results, str(checkpoint_path)
        return partial_results, None

    def _finish_interrupted_segment(
        self,
        context: _SegmentRunContext,
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
                    checkpoint_reference,
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

    def _finish_result_publish_failed_segment(
        self,
        context: _SegmentRunContext,
        error: str,
    ) -> None:
        task_id = context.task_id
        segment_id = context.segment_id
        model_calls, cache_hits, model_failures = context.runtime_totals()
        results, checkpoint_reference = self._save_partial_checkpoint(
            context.checkpoint_path,
            context.existing_results,
            context.latest_run,
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
                    checkpoint_reference,
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
