from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import pandas as pd

from return_semantics.pipeline import PipelineRun
from return_semantics.schemas import ProcessingStatus, ValidatedClassification


@dataclass
class _PipelineTotals:
    classifications: dict[str, ValidatedClassification] = field(default_factory=dict)
    usage: dict[str, int] = field(default_factory=dict)
    usage_by_model: dict[str, dict[str, int]] = field(default_factory=dict)
    cache_hits_by_model: dict[str, int] = field(default_factory=dict)
    model_calls_by_model: dict[str, int] = field(default_factory=dict)
    request_metrics: dict[str, int] = field(default_factory=dict)
    routing: dict[str, int] = field(default_factory=dict)
    cache_hits: int = 0
    model_calls: int = 0
    processed: int = 0

    def add(self, run: PipelineRun, selected_count: int) -> None:
        self.classifications.update(run.classifications)
        _add_counts(self.usage, run.usage)
        _add_nested_counts(self.usage_by_model, run.usage_by_model)
        _add_counts(self.cache_hits_by_model, run.cache_hits_by_model)
        _add_counts(self.model_calls_by_model, run.model_calls_by_model)
        _add_counts(self.request_metrics, run.request_metrics)
        _add_counts(self.routing, run.routing)
        self.cache_hits += run.cache_hits
        self.model_calls += run.model_calls
        self.processed += selected_count

    def build(self) -> PipelineRun:
        return PipelineRun(
            classifications=self.classifications,
            usage=self.usage,
            usage_by_model=self.usage_by_model,
            cache_hits=self.cache_hits,
            cache_hits_by_model=self.cache_hits_by_model,
            model_calls=self.model_calls,
            model_calls_by_model=self.model_calls_by_model,
            request_metrics=self.request_metrics,
            routing=self.routing,
        )


def _add_counts(target: dict[str, int], source: dict[str, int]) -> None:
    for key, value in source.items():
        target[key] = target.get(key, 0) + value


def _add_nested_counts(
    target: dict[str, dict[str, int]],
    source: dict[str, dict[str, int]],
) -> None:
    for key, values in source.items():
        _add_counts(target.setdefault(key, {}), values)


def _failed_segment(
    segment: dict[str, object],
    selected_count: int,
    error: Exception,
) -> dict[str, object]:
    return {
        **segment,
        "status": "failed",
        "progress_current": 0,
        "progress_total": selected_count,
        "model_calls": 0,
        "cache_hits": 0,
        "error": str(error),
    }


def _completed_segment(
    segment: dict[str, object],
    selected_count: int,
    run: PipelineRun,
) -> dict[str, object]:
    has_errors = any(
        result.status == ProcessingStatus.MODEL_ERROR
        for result in run.classifications.values()
    )
    return {
        **segment,
        "model_calls": run.model_calls,
        "cache_hits": run.cache_hits,
        "status": "completed_with_errors" if has_errors else "completed",
        "progress_current": selected_count,
        "progress_total": selected_count,
    }


@dataclass
class _SegmentResultRecorder:
    totals: _PipelineTotals
    segments: list[dict[str, object]]
    segment_update: Callable[[dict[str, object]], None] | None
    segment_completed: Callable[[str, dict[str, ValidatedClassification]], None] | None

    def failed(
        self, segment: dict[str, object], selected: pd.DataFrame, error: Exception
    ) -> None:
        failed_segment = _failed_segment(segment, len(selected), error)
        if self.segment_update is not None:
            self.segment_update(failed_segment)
        self.segments.append(failed_segment)
        self.totals.processed += len(selected)

    def completed(
        self, segment: dict[str, object], selected: pd.DataFrame, run: PipelineRun
    ) -> None:
        self.totals.add(run, len(selected))
        completed_segment = _completed_segment(segment, len(selected), run)
        self.segments.append(completed_segment)
        if self.segment_completed is not None:
            self.segment_completed(str(segment["segment_key"]), run.classifications)
        if self.segment_update is not None:
            self.segment_update(completed_segment)


def _report_running_segment(
    segment_update: Callable[[dict[str, object]], None] | None,
    segment: dict[str, object],
    current: int,
    total: int,
) -> None:
    if segment_update is not None:
        segment_update(
            {
                **segment,
                "status": "running",
                "progress_current": current,
                "progress_total": total,
            }
        )


def _report_segment_start(
    segment_update: Callable[[dict[str, object]], None] | None,
    segment: dict[str, object],
    total: int,
) -> None:
    if segment_update is not None:
        segment_update(
            {
                **segment,
                "status": "running",
                "progress_current": 0,
                "progress_total": total,
                "model_calls": 0,
                "cache_hits": 0,
            }
        )
