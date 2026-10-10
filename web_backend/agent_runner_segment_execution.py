from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pandas import DataFrame

from return_semantics.analysis_context import analysis_context_from_snapshot
from return_semantics.category_pipeline import CategorySegmentRuntime
from return_semantics.data import ReturnDataset
from return_semantics.pipeline import PipelineRun
from return_semantics.schemas import TaxonomyConfig, ValidatedClassification
from return_semantics.semantic_review import requires_system_rerun
from web_backend.common import json_value
from web_backend.dataset_cache import load_cached_dataset
from web_backend.settings import Settings
from web_backend.task_execution.contracts import _SegmentRunContext
from web_backend.task_execution.effective_results import current_inherited_results
from web_backend.task_execution.segment_configuration import SegmentConfigurationMixin
from web_backend.task_execution.segment_state import SegmentStateMixin

performance_logger = logging.getLogger("uvicorn.error.performance")


@dataclass(frozen=True)
class _SegmentRunSetup:
    all_keys: set[str]
    selected: DataFrame
    taxonomy: TaxonomyConfig
    runtime: CategorySegmentRuntime


class SegmentExecutionMixin(SegmentStateMixin, SegmentConfigurationMixin):
    _build_segment_runtime: Callable[..., CategorySegmentRuntime]
    _classify_segment: Callable[..., PipelineRun]
    _complete_segment: Callable[..., None]
    _export_legacy_segment_result: Callable[..., None]
    _load_checkpoint: Callable[..., dict[str, ValidatedClassification]]
    _refresh_parent: Callable[..., None]
    _subset_dataset: Callable[..., ReturnDataset]
    _write_checkpoint: Callable[..., None]
    settings: Settings

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
        if segment.get("result_version_id"):
            existing_results = current_inherited_results(
                self.database, str(segment["result_version_id"])
            )
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
        setup = self._prepare_segment_run(
            context, dataset, snapshot, task=task, segment=segment
        )
        setup_ms = (time.perf_counter() - setup_started) * 1000
        model_started = time.perf_counter()
        run = self._classify_segment(
            context, setup.selected, setup.taxonomy, setup.runtime, len(setup.all_keys)
        )
        model_ms = (time.perf_counter() - model_started) * 1000
        context.latest_run = run
        persist_started = time.perf_counter()
        self._complete_segment_run(
            context, dataset, setup.all_keys, setup.taxonomy, run
        )
        persist_ms = (time.perf_counter() - persist_started) * 1000
        performance_logger.info(
            "segment_stages task_id=%s segment_id=%s records=%s data_ms=%.2f setup_ms=%.2f model_ms=%.2f persist_ms=%.2f",
            context.task_id,
            context.segment_id,
            len(setup.all_keys),
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
        self._complete_segment(
            context=context,
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

    def _prepare_segment_run(
        self,
        context: _SegmentRunContext,
        dataset: ReturnDataset,
        snapshot: dict[str, Any],
        *,
        task: dict[str, Any],
        segment: dict[str, Any],
    ) -> _SegmentRunSetup:
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
        return _SegmentRunSetup(
            all_keys=all_keys, selected=selected, taxonomy=taxonomy, runtime=runtime
        )
