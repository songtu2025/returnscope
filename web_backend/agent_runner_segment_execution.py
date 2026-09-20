from __future__ import annotations

import logging
import time
from dataclasses import dataclass, is_dataclass, replace
from pathlib import Path
from typing import Any, Callable

from return_semantics.analysis_context import analysis_context_from_snapshot
from return_semantics.capabilities import CategoryCapability
from return_semantics.category_pipeline import CategorySegmentRuntime
from return_semantics.data import ReturnDataset
from return_semantics.pipeline import PipelineRun
from return_semantics.schemas import TaxonomyConfig, ValidatedClassification
from return_semantics.semantic_review import requires_system_rerun
from web_backend.classification_standard_service import ClassificationStandardService
from web_backend.common import json_text, json_value
from web_backend.config_service import ConfigService
from web_backend.database import Database
from web_backend.dataset_cache import load_cached_dataset
from web_backend.security import utc_now
from web_backend.settings import Settings

performance_logger = logging.getLogger("uvicorn.error.performance")


@dataclass
class _SegmentRunContext:
    task_id: str
    segment_id: str
    task: dict[str, Any]
    segment: dict[str, Any]
    checkpoint_path: Path
    existing_results: dict[str, ValidatedClassification]
    base_model_calls: int
    base_cache_hits: int
    base_model_failures: int
    latest_run: PipelineRun | None = None

    def runtime_totals(self) -> tuple[int, int, int]:
        run = self.latest_run
        return (
            self.base_model_calls + (run.model_calls if run else 0),
            self.base_cache_hits + (run.cache_hits if run else 0),
            self.base_model_failures + (run.model_failures if run else 0),
        )


class SegmentExecutionMixin:
    database: Database
    settings: Settings
    config_service: ConfigService
    standard_service: ClassificationStandardService
    capability_registry: Any
    _build_segment_runtime: Callable[..., CategorySegmentRuntime]
    _classify_segment: Callable[..., PipelineRun]
    _complete_segment: Callable[..., None]
    _export_legacy_segment_result: Callable[..., None]
    _load_checkpoint: Callable[..., dict[str, ValidatedClassification]]
    _refresh_parent: Callable[..., None]
    _results_have_quality_errors: Callable[..., bool]
    _subset_dataset: Callable[..., ReturnDataset]
    _write_checkpoint: Callable[..., None]

    def _segment_run_context(
        self,
        task_id: str,
        segment_id: str,
        task: dict[str, Any],
        segment: dict[str, Any],
    ) -> _SegmentRunContext:
        segment_dir = self.settings.data_dir / "results" / task_id / "segments"
        segment_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_path = Path(
            segment["result_json_path"]
            or segment_dir / f"{segment_id}-classifications.json"
        )
        existing_results = {
            key: value
            for key, value in self._load_checkpoint(checkpoint_path).items()
            if not requires_system_rerun(value, "")
        }
        return _SegmentRunContext(
            task_id=task_id,
            segment_id=segment_id,
            task=task,
            segment=segment,
            checkpoint_path=checkpoint_path,
            existing_results=existing_results,
            base_model_calls=int(segment.get("model_calls") or 0),
            base_cache_hits=int(segment.get("cache_hits") or 0),
            base_model_failures=int(segment.get("model_failures") or 0),
        )

    def _execute_segment(self, context: _SegmentRunContext) -> None:
        task = context.task
        segment = context.segment
        snapshot = json_value(task.get("snapshot_json"), {})
        scope_mode = str(snapshot.get("scope", {}).get("mode", "manual"))
        data_started = time.perf_counter()
        dataset = load_cached_dataset(
            str(task["return_file_path"]),
            str(task["product_file_path"]),
            str(task["store"]),
            task["listing"],
            scope_mode,
            str(task["return_sha256"]),
            str(task["product_sha256"]),
            analysis_context_from_snapshot(snapshot),
        )
        data_ms = (time.perf_counter() - data_started) * 1000
        setup_started = time.perf_counter()
        all_keys = {
            str(key) for key in json_value(segment["classification_keys_json"], [])
        }
        context.existing_results = {
            key: value
            for key, value in context.existing_results.items()
            if key in all_keys
        }
        remaining_keys = all_keys - set(context.existing_results)
        selected = dataset.unique_comments.loc[
            dataset.unique_comments["classification_key"]
            .astype(str)
            .isin(remaining_keys)
        ].reset_index(drop=True)

        capability = self._capability_for_segment(segment)
        taxonomy = self._taxonomy_for_segment(segment, capability)
        base_settings = self._snapshot_model_settings(task, snapshot)
        runtime = self._build_segment_runtime(
            segment,
            base_settings,
            str(task["config_version_id"]),
            str(task["store"]),
            task["listing"],
        )
        setup_ms = (time.perf_counter() - setup_started) * 1000
        model_started = time.perf_counter()
        run = self._classify_segment(
            context,
            selected,
            taxonomy,
            runtime,
            len(all_keys),
        )
        model_ms = (time.perf_counter() - model_started) * 1000
        context.latest_run = run
        persist_started = time.perf_counter()
        self._complete_segment_run(context, dataset, all_keys, taxonomy, run)
        persist_ms = (time.perf_counter() - persist_started) * 1000
        performance_logger.info(
            "segment_stages task_id=%s segment_id=%s records=%s "
            "data_ms=%.2f setup_ms=%.2f model_ms=%.2f persist_ms=%.2f",
            context.task_id,
            context.segment_id,
            len(all_keys),
            data_ms,
            setup_ms,
            model_ms,
            persist_ms,
        )

    def _save_segment_checkpoint(
        self,
        context: _SegmentRunContext,
        run: PipelineRun,
    ) -> None:
        context.latest_run = run
        combined = {**context.existing_results, **run.classifications}
        self._write_checkpoint(context.checkpoint_path, combined)
        self._update_segment_runtime_metrics(
            context.segment_id,
            *context.runtime_totals(),
        )

    def _complete_segment_run(
        self,
        context: _SegmentRunContext,
        dataset: ReturnDataset,
        all_keys: set[str],
        taxonomy: TaxonomyConfig,
        run: PipelineRun,
    ) -> None:
        results = {**context.existing_results, **run.classifications}
        if set(results) != all_keys:
            missing_count = len(all_keys - set(results))
            raise ValueError(f"Listing 片段仍缺少 {missing_count} 组分类结果")
        self._write_checkpoint(context.checkpoint_path, results)
        segment_dataset = self._subset_dataset(dataset, all_keys)
        result_version = int(context.segment["result_version"] or 0) + 1
        output_path = (
            self.settings.data_dir
            / "results"
            / context.task_id
            / "segments"
            / f"{context.segment_id}-analysis-v{result_version}.xlsx"
        )
        model_calls, cache_hits, model_failures = context.runtime_totals()
        self._complete_segment(
            task_id=context.task_id,
            segment_id=context.segment_id,
            status=(
                "completed_with_errors"
                if self._results_have_quality_errors(results)
                else "completed"
            ),
            progress_total=len(all_keys),
            model_calls=model_calls,
            cache_hits=cache_hits,
            model_failures=model_failures,
            checkpoint_path=context.checkpoint_path,
            result_version=result_version,
            dataset=segment_dataset,
            results=results,
            taxonomy=taxonomy,
        )
        self._export_legacy_segment_result(
            context,
            output_path,
            segment_dataset,
            results,
            taxonomy,
        )
        self._refresh_parent(context.task_id, dataset)

    def _snapshot_model_settings(
        self,
        task: dict[str, Any],
        snapshot: dict[str, Any],
    ) -> Any:
        model_settings = self.config_service.build_model_settings(
            str(task["config_version_id"])
        )
        snapshot_config = snapshot.get("config", {})
        if snapshot_config.get("primary_model") and is_dataclass(model_settings):
            return replace(
                model_settings,
                model=str(snapshot_config["primary_model"]),
                reasoning_effort=str(
                    snapshot_config.get(
                        "primary_effort",
                        model_settings.reasoning_effort,
                    )
                ),
                cheap_model=snapshot_config.get("cheap_model"),
                cheap_reasoning_effort=str(
                    snapshot_config.get(
                        "cheap_effort",
                        model_settings.cheap_reasoning_effort,
                    )
                ),
                cheap_model_audit_percent=int(
                    snapshot_config.get(
                        "cheap_audit_percent",
                        model_settings.cheap_model_audit_percent,
                    )
                ),
                secondary_model=snapshot_config.get("secondary_model"),
                secondary_reasoning_effort=str(
                    snapshot_config.get(
                        "secondary_effort",
                        model_settings.secondary_reasoning_effort,
                    )
                ),
            )
        return model_settings

    def _load_segment(self, segment_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM task_segments WHERE id = ?",
                (segment_id,),
            ).fetchone()
        return dict(row) if row else None

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

    def _capability_for_segment(
        self,
        segment: dict[str, Any],
    ) -> CategoryCapability:
        standard_version_id = str(segment.get("standard_version_id") or "")
        if standard_version_id:
            return self.standard_service.capability_for_version(standard_version_id)
        agent_key = str(segment["agent_key"])
        capability = next(
            (
                item
                for item in self.capability_registry.capabilities
                if item.key == agent_key
            ),
            None,
        )
        if capability is None:
            raise ValueError(f"品类能力不存在: {agent_key}")
        return capability

    def _taxonomy_for_segment(
        self,
        segment: dict[str, Any],
        capability: CategoryCapability,
    ) -> TaxonomyConfig:
        standard_version_id = str(segment.get("standard_version_id") or "")
        if standard_version_id:
            return self.standard_service.taxonomy_for_version(standard_version_id)
        return self.capability_registry.load_taxonomy(capability)

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
