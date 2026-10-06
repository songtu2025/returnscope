from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pandas as pd

from return_semantics.analysis_context import analysis_context_from_snapshot
from return_semantics.category_pipeline import CategorySegmentRuntime
from return_semantics.claims import NO_CLAIMS_VERSION, ClaimsResolver
from return_semantics.model_client import (
    JsonlCache,
    RequestRateLimiter,
    Sub2APIClient,
)
from return_semantics.pipeline import (
    PipelineRun,
    classify_comments,
)
from return_semantics.pipeline_metrics import MODEL_SERVICE_ALERT_FAILURES
from return_semantics.schemas import TaxonomyConfig
from web_backend.common import json_value
from web_backend.config_service import ConfigService
from web_backend.task_execution.contracts import _SegmentRunContext

_PROGRESS_UPDATE_INTERVAL = 5
_RAW_SAMPLE_SOURCE_KINDS = frozenset({"raw_dataset", "review_file"})


class ClassificationExecutionMixin:
    _build_segment_runtime: Callable[..., CategorySegmentRuntime]
    _get_cache: Callable[..., JsonlCache]
    _get_rate_limiter: Callable[..., RequestRateLimiter]
    _record_model_degraded: Callable[..., None]
    _save_segment_checkpoint: Callable[..., None]
    _segment_should_stop: Callable[..., bool]
    _settings_for_model_policy: Callable[..., Any]
    _snapshot_model_settings: Callable[..., Any]
    _update_segment_progress: Callable[..., None]
    claims_resolver: ClaimsResolver
    config_service: ConfigService

    def _classify_segment(
        self,
        context: _SegmentRunContext,
        selected: pd.DataFrame,
        taxonomy: TaxonomyConfig,
        runtime: CategorySegmentRuntime,
        total: int,
    ) -> PipelineRun:
        completed_base = len(context.existing_results)

        def progress(current: int, _total: int) -> None:
            completed = completed_base + current
            if (
                completed == total
                or completed == 1
                or completed % _PROGRESS_UPDATE_INTERVAL == 0
            ):
                self._update_segment_progress(
                    context.task_id,
                    context.segment_id,
                    completed,
                    total,
                )

        def checkpoint(run: PipelineRun) -> None:
            self._save_segment_checkpoint(context, run)

        def model_degraded(
            run: PipelineRun,
            consecutive_failures: int,
            error: str,
        ) -> None:
            self._save_segment_checkpoint(context, run)
            if consecutive_failures == MODEL_SERVICE_ALERT_FAILURES:
                self._record_model_degraded(
                    context.task_id,
                    context.segment_id,
                    error,
                    consecutive_failures,
                )

        if selected.empty:
            return PipelineRun(
                classifications={},
                usage={},
                usage_by_model={},
                cache_hits=0,
                cache_hits_by_model={},
                model_calls=0,
                model_calls_by_model={},
                request_metrics={},
                routing={},
            )
        task = context.task
        snapshot = json_value(task.get("snapshot_json"), {})
        return classify_comments(
            unique_comments=selected,
            taxonomy=taxonomy,
            claims=runtime.claims,
            client=runtime.client,
            cache=self._get_cache(f"{task['id']}-{task['config_version_id']}"),
            secondary_model=runtime.secondary_model,
            model_policy_version=str(runtime.model_policy["version"]),
            secondary_is_fallback=bool(
                runtime.model_policy["actual"].get("review")
                and runtime.model_policy["actual"]["review"].get("fallback_from")
                == "secondary"
            ),
            progress=progress,
            should_cancel=lambda: self._segment_should_stop(
                context.task_id,
                context.segment_id,
            ),
            checkpoint=checkpoint,
            on_model_degraded=model_degraded,
            analysis_context=analysis_context_from_snapshot(snapshot),
        )

    def classify_taxonomy_sample(
        self,
        *,
        taxonomy: TaxonomyConfig,
        samples: list[dict[str, Any]],
        source: dict[str, Any],
        progress: Callable[[int, int], None] | None = None,
    ) -> PipelineRun:
        unique_comments = pd.DataFrame(
            [
                {
                    "classification_key": str(item["classification_key"]),
                    "comment_normalized": str(item["comment"]),
                    "reason": item.get("reason"),
                    "category_a": str(item.get("category_a") or ""),
                    "category_b": str(item.get("category_b") or ""),
                }
                for item in samples
            ]
        )
        if source.get("kind") in _RAW_SAMPLE_SOURCE_KINDS:
            return self._classify_source_sample(
                unique_comments, taxonomy, source, progress
            )
        task = source["task"]
        segment = source["segment"]
        snapshot = json_value(task.get("snapshot_json"), {})
        base_settings = self._snapshot_model_settings(task, snapshot)
        runtime = self._build_segment_runtime(
            segment,
            base_settings,
            str(task["config_version_id"]),
            str(task["store"]),
            task.get("listing"),
        )
        review = runtime.model_policy["actual"].get("review")
        return classify_comments(
            unique_comments=unique_comments,
            taxonomy=taxonomy,
            claims=runtime.claims,
            client=runtime.client,
            cache=self._get_cache("classification-standard-validation"),
            secondary_model=runtime.secondary_model,
            progress=progress,
            model_policy_version=str(runtime.model_policy["version"]),
            secondary_is_fallback=bool(
                review and review.get("fallback_from") == "secondary"
            ),
            analysis_context=analysis_context_from_snapshot(snapshot),
        )

    def _classify_source_sample(
        self,
        unique_comments: pd.DataFrame,
        taxonomy: TaxonomyConfig,
        source: dict[str, Any],
        progress: Callable[[int, int], None] | None,
    ) -> PipelineRun:
        config_version_id = str(source["config_version_id"])
        settings = self.config_service.build_model_settings(config_version_id)
        model_policy = source.get("model_policy")
        if model_policy is not None:
            settings = self._settings_for_model_policy(settings, model_policy)
        claims = self.claims_resolver.resolve(
            str(source.get("store") or ""),
            source.get("listing"),
            str(source["standard_key"]),
            expected_version=NO_CLAIMS_VERSION,
        )
        client = Sub2APIClient(
            settings,
            rate_limiter=self._get_rate_limiter(
                config_version_id, settings.requests_per_minute
            ),
        )
        return classify_comments(
            unique_comments=unique_comments,
            taxonomy=taxonomy,
            claims=claims,
            client=client,
            cache=self._get_cache("classification-standard-validation"),
            secondary_model=str(model_policy["actual"]["review"]["model"])
            if model_policy and model_policy["actual"].get("review")
            else settings.secondary_model,
            progress=progress,
            model_policy_version=str(source["model_policy_version"]),
            secondary_is_fallback=bool(
                model_policy
                and model_policy["actual"].get("review")
                and (
                    model_policy["actual"]["review"].get("fallback_from") == "secondary"
                )
            ),
            analysis_context=source.get("analysis_context", "returns"),
        )
