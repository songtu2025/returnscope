from __future__ import annotations

from typing import Any

from return_semantics.pipeline import PipelineRun
from web_backend.common import json_text
from web_backend.database import Database
from web_backend.security import utc_now


class ClassificationStandardValidationStoreMixin:
    database: Database

    def _save_validation_progress(
        self, run_id: str, stage: str, current: int, total: int
    ) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                            UPDATE classification_standard_validation_runs
                            SET processed_count = ?, stage = ?
                            WHERE id = ? AND status = 'running'
                            """,
                (current, stage, run_id),
            )

    def _store_validation_result(
        self,
        run_id: str,
        comparison: tuple[list[dict[str, Any]], dict[str, Any], list[str]],
        pipeline: PipelineRun,
        baseline_pipeline: PipelineRun | None,
    ) -> None:
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                    UPDATE classification_standard_validation_runs
                    SET status = 'completed', stage = 'completed',
                        processed_count = sample_size, changed_count = ?,
                        unknown_count = ?, review_count = ?, error_count = ?,
                        result_json = ?, summary_json = ?, usage_json = ?,
                        metrics_json = ?, model_names_json = ?,
                        error = NULL, completed_at = ?
                    WHERE id = ? AND status = 'running'
                    """,
                self._completion_values(
                    run_id,
                    comparison,
                    pipeline,
                    baseline_pipeline,
                ),
            )

    @staticmethod
    def _completion_values(
        run_id: str,
        comparison: tuple[list[dict[str, Any]], dict[str, Any], list[str]],
        pipeline: PipelineRun,
        baseline_pipeline: PipelineRun | None,
    ) -> tuple[Any, ...]:
        items, summary, model_names = comparison
        return (
            summary["changed_count"],
            summary["unknown_count"],
            summary["review_count"],
            summary["error_count"],
            json_text(items),
            json_text(summary),
            json_text(
                {
                    "baseline": baseline_pipeline.usage
                    if baseline_pipeline is not None
                    else {},
                    "draft": pipeline.usage,
                }
            ),
            json_text(
                {
                    "baseline": baseline_pipeline.request_metrics
                    if baseline_pipeline is not None
                    else {},
                    "draft": pipeline.request_metrics,
                }
            ),
            json_text(model_names),
            utc_now(),
            run_id,
        )

    def _fail_validation(self, run_id: str, exc: Exception) -> None:
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                    UPDATE classification_standard_validation_runs
                    SET status = 'failed', stage = 'failed', error = ?,
                        completed_at = ?
                    WHERE id = ? AND status = 'running'
                    """,
                (str(exc)[:2000], utc_now(), run_id),
            )
