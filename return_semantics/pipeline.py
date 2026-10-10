from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pandas as pd

from return_semantics.analysis_context import (
    validate_analysis_context,
)
from return_semantics.fact_pipeline import FactPipelineCancelled, classify_facts
from return_semantics.model_client import (
    JsonlCache,
    ModelCallResult,
    ModelClient,
)
from return_semantics.output_correction import correct_invalid_output
from return_semantics.pipeline_cache import (
    build_cache_key as build_cache_key,
)
from return_semantics.pipeline_cache import (
    call_with_cache as _cached_model_call,
)
from return_semantics.pipeline_classifier import _CommentClassifier
from return_semantics.pipeline_execution import (
    _classify_selected_comments as _classify_selected_comments,
)
from return_semantics.pipeline_metrics import (
    _RunTracker as _RunTracker,
)
from return_semantics.pipeline_models import (
    ModelServiceUnavailable as ModelServiceUnavailable,
)
from return_semantics.pipeline_models import (
    PipelineCancelled as PipelineCancelled,
)
from return_semantics.pipeline_models import (
    PipelineRun as PipelineRun,
)
from return_semantics.pipeline_models import (
    _PipelineContext as _PipelineContext,
)
from return_semantics.pipeline_models import (
    _RowContext as _RowContext,
)
from return_semantics.pipeline_routing_policy import (
    can_accept_cheap_result as can_accept_cheap_result,
)
from return_semantics.pipeline_routing_policy import (
    has_input_semantic_risk as has_input_semantic_risk,
)
from return_semantics.pipeline_routing_policy import (
    should_audit_cheap_model as should_audit_cheap_model,
)
from return_semantics.schemas import (
    ListingClaimsConfig,
    TaxonomyConfig,
)
from return_semantics.taxonomy import adapt_claims_to_taxonomy


def _classify_uncached(
    row: _RowContext,
    context: _PipelineContext,
    model_name: str,
    thinking: bool,
    reasoning_effort: Any,
) -> ModelCallResult:
    if context.taxonomy.recognition_profile == "fact_v2":
        try:
            return classify_facts(
                comment=row.comment,
                taxonomy=context.taxonomy,
                client=context.client,
                model_name=model_name,
                reasoning_effort=str(reasoning_effort),
                should_cancel=context.should_cancel,
                claims=context.claims,
            )
        except FactPipelineCancelled as exc:
            raise PipelineCancelled(str(exc)) from exc
    result = context.client.classify(
        messages=row.messages,
        model=model_name,
        thinking=thinking,
    )
    return correct_invalid_output(
        result,
        comment=row.comment,
        messages=row.messages,
        taxonomy=context.taxonomy,
        claims=context.claims,
        client=context.client,
        model_name=model_name,
        thinking=thinking,
        should_cancel=context.should_cancel,
    )


def _call_with_cache(
    row: _RowContext,
    context: _PipelineContext,
    model_name: str,
    thinking: bool,
) -> tuple[ModelCallResult, bool]:
    # 保留现有模型分类替换入口；缓存模块不反向导入流水线。
    return _cached_model_call(
        row, context, model_name, thinking, classify_uncached=_classify_uncached
    )


def classify_comments(
    unique_comments: pd.DataFrame,
    taxonomy: TaxonomyConfig,
    claims: ListingClaimsConfig,
    client: ModelClient,
    cache: JsonlCache,
    offset: int = 0,
    limit: int | None = None,
    force: bool = False,
    secondary_model: str | None = None,
    progress: Callable[[int, int], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    checkpoint: Callable[[PipelineRun], None] | None = None,
    on_model_degraded: Callable[[PipelineRun, int, str], None] | None = None,
    model_policy_version: str = "legacy-model-policy-v1",
    secondary_is_fallback: bool = False,
    analysis_context: str = "returns",
) -> PipelineRun:
    validated_context = validate_analysis_context(analysis_context)
    claims = adapt_claims_to_taxonomy(claims, taxonomy)
    selected = unique_comments.iloc[offset:]
    if limit is not None:
        selected = selected.head(limit)
    max_workers = max(
        1,
        int(getattr(client.settings, "max_workers", 1)),
    )
    tracker = _RunTracker(on_model_degraded)
    classifier = _CommentClassifier(
        _PipelineContext(
            taxonomy=taxonomy,
            claims=claims,
            client=client,
            cache=cache,
            force=force,
            secondary_model=secondary_model,
            should_cancel=should_cancel,
            model_policy_version=model_policy_version,
            secondary_is_fallback=secondary_is_fallback,
            analysis_context=validated_context,
        ),
        tracker,
        _call_with_cache,
    )
    return _classify_selected_comments(
        selected,
        classifier,
        max_workers,
        progress,
        checkpoint,
    )


PipelineRun.__module__ = __name__
PipelineCancelled.__module__ = __name__
ModelServiceUnavailable.__module__ = __name__
_PipelineContext.__module__ = __name__
_RowContext.__module__ = __name__
_RunTracker.__module__ = __name__
has_input_semantic_risk.__module__ = __name__
can_accept_cheap_result.__module__ = __name__
should_audit_cheap_model.__module__ = __name__

build_cache_key.__module__ = __name__
_classify_selected_comments.__module__ = __name__
