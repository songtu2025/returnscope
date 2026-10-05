from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pandas as pd

from return_semantics.capabilities import CapabilityRegistry
from return_semantics.category_results import _add_counts as _add_counts
from return_semantics.category_results import _add_nested_counts as _add_nested_counts
from return_semantics.category_results import _completed_segment as _completed_segment
from return_semantics.category_results import _failed_segment as _failed_segment
from return_semantics.category_results import _PipelineTotals as _PipelineTotals
from return_semantics.category_results import (
    _report_running_segment as _report_running_segment,
)
from return_semantics.category_results import (
    _report_segment_start as _report_segment_start,
)
from return_semantics.category_results import _SegmentResultRecorder
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

    def classify(
        self,
        selected: pd.DataFrame,
        taxonomy: TaxonomyConfig,
        cache: JsonlCache,
        progress: Callable[[int, int], None],
        should_cancel: Callable[[], bool] | None,
    ) -> PipelineRun:
        return classify_comments(
            unique_comments=selected,
            taxonomy=taxonomy,
            claims=self.claims,
            client=self.client,
            cache=cache,
            secondary_model=self.secondary_model,
            model_policy_version=str(self.model_policy["version"])
            if self.model_policy is not None
            else "legacy-model-policy-v1",
            secondary_is_fallback=_secondary_is_fallback(self.model_policy),
            progress=progress,
            should_cancel=should_cancel,
        )


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
    recorder = _SegmentResultRecorder(
        totals, segments, segment_update, segment_completed
    )
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
            run = runtime.classify(
                selected, taxonomy, cache, segment_progress, should_cancel
            )
        except PipelineCancelled:
            raise
        except Exception as exc:
            recorder.failed(runtime_segment, selected, exc)
            continue
        recorder.completed(runtime_segment, selected, run)

    return CategoryPipelineRun(
        pipeline=totals.build(),
        taxonomy=registry.combined_taxonomy(),
        segments=segments,
    )


_PipelineTotals.__module__ = __name__
_add_counts.__module__ = __name__
_add_nested_counts.__module__ = __name__
_failed_segment.__module__ = __name__
_completed_segment.__module__ = __name__

_report_running_segment.__module__ = __name__
_report_segment_start.__module__ = __name__
