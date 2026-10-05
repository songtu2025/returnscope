from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from return_semantics.analysis_context import AnalysisContext
from return_semantics.model_client import JsonlCache, ModelClient
from return_semantics.schemas import (
    ListingClaimsConfig,
    TaxonomyConfig,
    ValidatedClassification,
)


@dataclass(frozen=True)
class PipelineRun:
    classifications: dict[str, ValidatedClassification]
    usage: dict[str, int]
    usage_by_model: dict[str, dict[str, int]]
    cache_hits: int
    cache_hits_by_model: dict[str, int]
    model_calls: int
    model_calls_by_model: dict[str, int]
    request_metrics: dict[str, int]
    routing: dict[str, int]
    model_failures: int = 0


class PipelineCancelled(RuntimeError):
    pass


class ModelServiceUnavailable(RuntimeError):
    def __init__(self, message: str, consecutive_failures: int) -> None:
        super().__init__(message)
        self.consecutive_failures = consecutive_failures


@dataclass(frozen=True)
class _PipelineContext:
    taxonomy: TaxonomyConfig
    claims: ListingClaimsConfig
    client: ModelClient
    cache: JsonlCache
    force: bool
    secondary_model: str | None
    should_cancel: Callable[[], bool] | None
    model_policy_version: str
    secondary_is_fallback: bool
    analysis_context: AnalysisContext


@dataclass(frozen=True)
class _RowContext:
    classification_key: str
    comment: str
    reason: str
    classification_scope: str
    messages: list[dict[str, str]]
    use_cheap_model: bool
    initial_model: str
