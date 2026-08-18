from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

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
    model_policy: dict[str, object]


def _add_counts(target: dict[str, int], source: dict[str, int]) -> None:
    for key, value in source.items():
        target[key] = target.get(key, 0) + value


def _add_nested_counts(
    target: dict[str, dict[str, int]],
    source: dict[str, dict[str, int]],
) -> None:
    for key, values in source.items():
        _add_counts(target.setdefault(key, {}), values)


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
    classifications: dict[str, ValidatedClassification] = {}
    segments: list[dict[str, object]] = []
    processed = 0
    total = int((assignments.notna() & assignments.ne("excluded")).sum())

    usage: dict[str, int] = {}
    usage_by_model: dict[str, dict[str, int]] = {}
    cache_hits_by_model: dict[str, int] = {}
    model_calls_by_model: dict[str, int] = {}
    request_metrics: dict[str, int] = {}
    routing: dict[str, int] = {}
    cache_hits = 0
    model_calls = 0

    capabilities = {item.key: item for item in registry.capabilities}
    ready_segments = [
        segment
        for segment in execution_plan.summary["segments"]
        if segment["status"] == "ready"
        and (
            allowed_agent_keys is None
            or str(segment["agent_key"]) in allowed_agent_keys
        )
    ]
    for planned_segment in ready_segments:
        capability = capabilities[str(planned_segment["agent_key"])]
        selected = unique_comments.loc[
            assignments.eq(str(planned_segment["segment_key"]))
        ].reset_index(drop=True)
        if allowed_classification_keys is not None:
            selected = selected.loc[
                selected["classification_key"].isin(allowed_classification_keys)
            ].reset_index(drop=True)
        if selected.empty:
            continue
        runtime_segment = {
            **planned_segment,
            "segment_key": (segment_key_by_agent or {}).get(
                capability.key, planned_segment["segment_key"]
            ),
        }
        taxonomy = registry.load_taxonomy(capability)
        runtime = (runtimes or {}).get(capability.key)
        segment_client = runtime.client if runtime is not None else client
        claims = (
            runtime.claims
            if runtime is not None
            else ListingClaimsConfig(version=NO_CLAIMS_VERSION, claims=[])
        )
        segment_secondary_model = (
            runtime.secondary_model if runtime is not None else secondary_model
        )
        model_policy = runtime.model_policy if runtime is not None else None
        runtime_segment.update(
            {
                "claims_version": claims.version,
                "model_policy_version": (
                    model_policy.get("version") if model_policy else None
                ),
                "model_policy": model_policy,
            }
        )
        base_progress = processed
        if segment_update is not None:
            segment_update(
                {
                    **runtime_segment,
                    "status": "running",
                    "progress_current": 0,
                    "progress_total": len(selected),
                    "model_calls": 0,
                    "cache_hits": 0,
                }
            )

        def segment_progress(
            current: int,
            _segment_total: int,
            progress_base: int = base_progress,
            segment_plan: dict[str, object] = runtime_segment,
            selected_count: int = len(selected),
        ) -> None:
            if segment_update is not None:
                segment_update(
                    {
                        **segment_plan,
                        "status": "running",
                        "progress_current": current,
                        "progress_total": selected_count,
                    }
                )
            if progress is not None:
                progress(progress_base + current, total)

        try:
            run = classify_comments(
                unique_comments=selected,
                taxonomy=taxonomy,
                claims=claims,
                client=segment_client,
                cache=cache,
                secondary_model=segment_secondary_model,
                model_policy_version=(
                    str(model_policy["version"])
                    if model_policy is not None
                    else "legacy-model-policy-v1"
                ),
                secondary_is_fallback=bool(
                    model_policy
                    and model_policy["actual"].get("review")
                    and model_policy["actual"]["review"].get("fallback_from")
                    == "secondary"
                ),
                progress=segment_progress,
                should_cancel=should_cancel,
            )
        except PipelineCancelled:
            raise
        except Exception as exc:
            failed_segment = {
                **runtime_segment,
                "status": "failed",
                "progress_current": 0,
                "progress_total": len(selected),
                "model_calls": 0,
                "cache_hits": 0,
                "error": str(exc),
            }
            if segment_update is not None:
                segment_update(failed_segment)
            segments.append(failed_segment)
            processed += len(selected)
            continue
        classifications.update(run.classifications)
        _add_counts(usage, run.usage)
        _add_nested_counts(usage_by_model, run.usage_by_model)
        _add_counts(cache_hits_by_model, run.cache_hits_by_model)
        _add_counts(model_calls_by_model, run.model_calls_by_model)
        _add_counts(request_metrics, run.request_metrics)
        _add_counts(routing, run.routing)
        cache_hits += run.cache_hits
        model_calls += run.model_calls
        processed += len(selected)
        has_errors = any(
            result.status == ProcessingStatus.MODEL_ERROR
            for result in run.classifications.values()
        )
        completed_segment = {
            **runtime_segment,
            "model_calls": run.model_calls,
            "cache_hits": run.cache_hits,
            "status": "completed_with_errors" if has_errors else "completed",
            "progress_current": len(selected),
            "progress_total": len(selected),
        }
        segments.append(completed_segment)
        if segment_completed is not None:
            segment_completed(str(runtime_segment["segment_key"]), run.classifications)
        if segment_update is not None:
            segment_update(completed_segment)

    pipeline = PipelineRun(
        classifications=classifications,
        usage=usage,
        usage_by_model=usage_by_model,
        cache_hits=cache_hits,
        cache_hits_by_model=cache_hits_by_model,
        model_calls=model_calls,
        model_calls_by_model=model_calls_by_model,
        request_metrics=request_metrics,
        routing=routing,
    )
    return CategoryPipelineRun(
        pipeline=pipeline,
        taxonomy=registry.combined_taxonomy(),
        segments=segments,
    )
