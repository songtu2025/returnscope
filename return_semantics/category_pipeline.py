from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from return_semantics.capabilities import CapabilityRegistry
from return_semantics.claims import NO_CLAIMS_VERSION
from return_semantics.data import ReturnDataset
from return_semantics.model_client import JsonlCache, ModelClient
from return_semantics.pipeline import (
    PipelineCancelled,
    PipelineRun,
    classify_comments,
)
from return_semantics.schemas import (
    ListingClaimsConfig,
    ProcessingStatus,
    TaxonomyConfig,
    ValidatedClassification,
)
from return_semantics.task_plan import (
    CategoryExecutionPlan,
    build_category_execution_plan,
)


@dataclass(frozen=True)
class CategoryPipelineRun:
    pipeline: PipelineRun
    taxonomy: TaxonomyConfig
    segments: list[dict[str, object]]


@dataclass(frozen=True)
class CategorySegmentRuntime:
    client: ModelClient
    claims: ListingClaimsConfig
    secondary_model: str | None
    model_policy: dict[str, Any]


@dataclass(frozen=True)
class _ResolvedSegmentRuntime:
    client: ModelClient
    claims: ListingClaimsConfig
    secondary_model: str | None
    model_policy: dict[str, Any] | None


@dataclass(frozen=True)
class _SegmentProgress:
    segment_update: Callable[[dict[str, object]], None] | None
    progress: Callable[[int, int], None] | None
    segment: dict[str, object]
    progress_base: int
    selected_count: int
    total: int

    def __call__(self, current: int, _segment_total: int) -> None:
        _report_running_segment(
            self.segment_update,
            self.segment,
            current,
            self.selected_count,
        )
        if self.progress is not None:
            self.progress(self.progress_base + current, self.total)


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


def _ready_segments(
    plan: CategoryExecutionPlan,
    allowed_agent_keys: set[str] | None,
) -> list[dict[str, object]]:
    return [
        segment
        for segment in plan.summary["segments"]
        if segment["status"] == "ready"
        and (
            allowed_agent_keys is None
            or str(segment["agent_key"]) in allowed_agent_keys
        )
    ]


def _selected_comments(
    unique_comments: pd.DataFrame,
    assignments: pd.Series,
    segment_key: str,
    allowed_classification_keys: set[str] | None,
) -> pd.DataFrame:
    selected = unique_comments.loc[assignments.eq(segment_key)].reset_index(drop=True)
    if allowed_classification_keys is not None:
        selected = selected.loc[
            selected["classification_key"].isin(allowed_classification_keys)
        ].reset_index(drop=True)
    return selected


def _resolve_runtime(
    capability_key: str,
    client: ModelClient,
    secondary_model: str | None,
    runtimes: dict[str, CategorySegmentRuntime] | None,
) -> _ResolvedSegmentRuntime:
    runtime = (runtimes or {}).get(capability_key)
    if runtime is not None:
        return _ResolvedSegmentRuntime(
            runtime.client,
            runtime.claims,
            runtime.secondary_model,
            runtime.model_policy,
        )
    return _ResolvedSegmentRuntime(
        client,
        ListingClaimsConfig(version=NO_CLAIMS_VERSION, claims=[]),
        secondary_model,
        None,
    )


def _runtime_segment(
    planned_segment: dict[str, object],
    capability_key: str,
    segment_key_by_agent: dict[str, str] | None,
    runtime: _ResolvedSegmentRuntime,
) -> dict[str, object]:
    model_policy = runtime.model_policy
    return {
        **planned_segment,
        "segment_key": (segment_key_by_agent or {}).get(
            capability_key, planned_segment["segment_key"]
        ),
        "claims_version": runtime.claims.version,
        "model_policy_version": (model_policy.get("version") if model_policy else None),
        "model_policy": model_policy,
    }


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


def _secondary_is_fallback(model_policy: dict[str, object] | None) -> bool:
    if not model_policy:
        return False
    actual: Any = model_policy["actual"]
    return bool(
        actual.get("review") and actual["review"].get("fallback_from") == "secondary"
    )


def classify_category_segments(
    dataset: ReturnDataset,
    registry: CapabilityRegistry,
    client: ModelClient,
    cache: JsonlCache,
    secondary_model: str | None = None,
    progress: Callable[[int, int], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    plan: CategoryExecutionPlan | None = None,
    segment_update: Callable[[dict[str, object]], None] | None = None,
    allowed_agent_keys: set[str] | None = None,
    allowed_classification_keys: set[str] | None = None,
    segment_key_by_agent: dict[str, str] | None = None,
    segment_completed: Callable[
        [str, dict[str, ValidatedClassification]],
        None,
    ]
    | None = None,
    runtimes: dict[str, CategorySegmentRuntime] | None = None,
) -> CategoryPipelineRun:
    unique_comments = dataset.unique_comments
    execution_plan = plan or build_category_execution_plan(dataset, registry)
    assignments = pd.Series(
        execution_plan.assignments,
        index=unique_comments.index,
    )
    totals = _PipelineTotals()
    segments: list[dict[str, object]] = []
    total = int((assignments.notna() & assignments.ne("excluded")).sum())
    capabilities = {item.key: item for item in registry.capabilities}
    for planned_segment in _ready_segments(execution_plan, allowed_agent_keys):
        capability = capabilities[str(planned_segment["agent_key"])]
        selected = _selected_comments(
            unique_comments,
            assignments,
            str(planned_segment["segment_key"]),
            allowed_classification_keys,
        )
        if selected.empty:
            continue
        taxonomy = registry.load_taxonomy(capability)
        runtime = _resolve_runtime(
            capability.key,
            client,
            secondary_model,
            runtimes,
        )
        runtime_segment = _runtime_segment(
            planned_segment,
            capability.key,
            segment_key_by_agent,
            runtime,
        )
        _report_segment_start(segment_update, runtime_segment, len(selected))
        segment_progress = _SegmentProgress(
            segment_update,
            progress,
            runtime_segment,
            totals.processed,
            len(selected),
            total,
        )

        try:
            run = classify_comments(
                unique_comments=selected,
                taxonomy=taxonomy,
                claims=runtime.claims,
                client=runtime.client,
                cache=cache,
                secondary_model=runtime.secondary_model,
                model_policy_version=(
                    str(runtime.model_policy["version"])
                    if runtime.model_policy is not None
                    else "legacy-model-policy-v1"
                ),
                secondary_is_fallback=_secondary_is_fallback(runtime.model_policy),
                progress=segment_progress,
                should_cancel=should_cancel,
            )
        except PipelineCancelled:
            raise
        except Exception as exc:
            failed_segment = _failed_segment(runtime_segment, len(selected), exc)
            if segment_update is not None:
                segment_update(failed_segment)
            segments.append(failed_segment)
            totals.processed += len(selected)
            continue
        totals.add(run, len(selected))
        completed_segment = _completed_segment(runtime_segment, len(selected), run)
        segments.append(completed_segment)
        if segment_completed is not None:
            segment_completed(str(runtime_segment["segment_key"]), run.classifications)
        if segment_update is not None:
            segment_update(completed_segment)

    return CategoryPipelineRun(
        pipeline=totals.build(),
        taxonomy=registry.combined_taxonomy(),
        segments=segments,
    )
