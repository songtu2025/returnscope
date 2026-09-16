from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from threading import Event, Lock
from typing import Any, Literal, cast

import pandas as pd

from return_semantics.fact_pipeline import FactPipelineCancelled, classify_facts
from return_semantics.model_client import (
    JsonlCache,
    ModelCallResult,
    ModelClient,
    ModelHTTPError,
)
from return_semantics.output_correction import correct_invalid_output
from return_semantics.prompt import (
    PROMPT_VERSION,
    build_messages,
    prompt_version,
    recognition_fingerprint,
)
from return_semantics.review import (
    classifications_match,
    reconcile_secondary,
    should_run_secondary,
)
from return_semantics.schemas import (
    ClaimRelation,
    ListingClaimsConfig,
    ProcessingStatus,
    TaxonomyConfig,
    ValidatedClassification,
)
from return_semantics.taxonomy import adapt_claims_to_taxonomy
from return_semantics.validator import validate_classification

_SEMANTIC_RISK_PATTERNS = (
    re.compile(r"[|;/?&,]"),
    re.compile(r"[.!]\s+\S"),
    re.compile(
        r"\b(?:and|or|but|however|although|though|because|if|unless|"
        r"while|except|yet|also)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:no|not|never|neither|nor|without|cannot|can't|don't|"
        r"doesn't|didn't|isn't|wasn't|weren't|won't|wouldn't|"
        r"couldn't|shouldn't|barely|hardly)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:need|needed|want|wanted|expected|expecting|wish|"
        r"should|would)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:than|unlike|compared|previous|another|other|different|"
        r"maybe|perhaps|seems?|unsure|uncertain)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:size|sized|sizing|order|ordered)\s+(?:up|down)\b",
        re.IGNORECASE,
    ),
)


def has_input_semantic_risk(comment: str) -> bool:
    return any(pattern.search(comment) for pattern in _SEMANTIC_RISK_PATTERNS)


def can_accept_cheap_result(result: ValidatedClassification) -> bool:
    if result.status != ProcessingStatus.AUTO_APPROVED:
        return False
    if result.unknown_semantics:
        return False
    if len(result.semantic_units) != 1:
        return False
    if len(result.problem_label_codes) != 1:
        return False
    if len(result.primary_label_codes) != 1:
        return False

    unit = result.semantic_units[0]
    return (
        not unit.implicit
        and unit.claim_relation == ClaimRelation.NONE
        and unit.claim_id is None
    )


def should_audit_cheap_model(comment: str, percent: int) -> bool:
    if percent <= 0:
        return False
    if percent >= 100:
        return True
    digest = hashlib.sha256(comment.lower().encode("utf-8")).digest()
    bucket = int.from_bytes(digest[:4], "big") % 10_000
    return bucket < percent * 100


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


def _is_model_service_error(exc: Exception) -> bool:
    current: BaseException | None = exc
    while current is not None:
        if isinstance(current, ModelHTTPError):
            return current.status_code >= 500
        current = current.__cause__
    return False


def build_cache_key(
    comment: str,
    model_name: str,
    provider_name: str,
    taxonomy_version: str,
    claims_version: str,
    thinking: bool = False,
    classification_scope: str = "",
    reasoning_effort: str = "",
    model_policy_version: str = "legacy-model-policy-v1",
    recognition_key: str = "",
    effective_prompt_version: str = PROMPT_VERSION,
) -> str:
    payload = {
        "comment": comment.lower(),
        "model": f"{model_name}:thinking" if thinking else model_name,
        "prompt": effective_prompt_version,
        "taxonomy": taxonomy_version,
        "claims": claims_version,
        "scope": classification_scope,
        "effort": reasoning_effort,
        "model_policy": model_policy_version,
    }
    if recognition_key:
        payload["recognition"] = recognition_key
    payload["provider"] = provider_name
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _call_with_cache(
    comment: str,
    model_name: str,
    thinking: bool,
    messages: list[dict[str, str]],
    taxonomy: TaxonomyConfig,
    claims: ListingClaimsConfig,
    client: ModelClient,
    cache: JsonlCache,
    force: bool,
    classification_scope: str,
    model_policy_version: str,
    should_cancel: Callable[[], bool] | None = None,
) -> tuple[ModelCallResult, bool]:
    if thinking:
        reasoning_effort = getattr(
            client.settings,
            "secondary_reasoning_effort",
            "",
        )
    elif model_name == getattr(client.settings, "cheap_model", None):
        reasoning_effort = getattr(client.settings, "cheap_reasoning_effort", "")
    else:
        reasoning_effort = getattr(client.settings, "reasoning_effort", "")

    cache_key = build_cache_key(
        comment=comment,
        model_name=model_name,
        provider_name=client.settings.cache_namespace,
        taxonomy_version=taxonomy.version,
        claims_version=claims.version,
        effective_prompt_version=prompt_version(taxonomy),
        recognition_key=(
            recognition_fingerprint(taxonomy)
            if taxonomy.recognition_profile != "legacy_v3"
            else ""
        ),
        thinking=thinking,
        classification_scope=classification_scope,
        reasoning_effort=str(reasoning_effort),
        model_policy_version=model_policy_version,
    )
    with cache.lock_for(cache_key):
        cached = None if force else cache.get(cache_key)
        if cached is not None:
            return cached, True

        if taxonomy.recognition_profile == "fact_v2":
            try:
                result = classify_facts(
                    comment=comment,
                    taxonomy=taxonomy,
                    client=client,
                    model_name=model_name,
                    reasoning_effort=str(reasoning_effort),
                    should_cancel=should_cancel,
                    claims=claims,
                )
            except FactPipelineCancelled as exc:
                raise PipelineCancelled(str(exc)) from exc
        else:
            result = client.classify(
                messages=messages,
                model=model_name,
                thinking=thinking,
            )
            result = correct_invalid_output(
                result,
                comment=comment,
                messages=messages,
                taxonomy=taxonomy,
                claims=claims,
                client=client,
                model_name=model_name,
                thinking=thinking,
                should_cancel=should_cancel,
            )
        cache.put(cache_key, result)
        return result, False


def _add_usage(total: dict[str, int], usage: dict[str, int]) -> None:
    for key, value in usage.items():
        total[key] = total.get(key, 0) + value


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
    analysis_context: Literal["returns", "review"]


@dataclass(frozen=True)
class _RowContext:
    classification_key: str
    comment: str
    reason: str
    classification_scope: str
    messages: list[dict[str, str]]
    use_cheap_model: bool
    initial_model: str


class _RunTracker:
    def __init__(
        self,
        on_model_degraded: Callable[[PipelineRun, int, str], None] | None,
    ) -> None:
        self.results: dict[str, ValidatedClassification] = {}
        self.usage: dict[str, int] = {}
        self.usage_by_model: dict[str, dict[str, int]] = {}
        self.cache_hits = 0
        self.cache_hits_by_model: dict[str, int] = {}
        self.model_calls = 0
        self.model_calls_by_model: dict[str, int] = {}
        self.model_failures = 0
        self.consecutive_service_failures = 0
        self.last_service_error = ""
        self.request_metrics: dict[str, int] = {}
        self.routing: dict[str, int] = {}
        self._on_model_degraded = on_model_degraded
        self._lock = Lock()
        self._service_breaker = Event()

    def increment_routing(self, route_name: str) -> None:
        with self._lock:
            self.routing[route_name] = self.routing.get(route_name, 0) + 1

    def record_call(
        self,
        requested_model: str,
        call_result: ModelCallResult,
        cache_hit: bool,
    ) -> None:
        with self._lock:
            if cache_hit:
                self.cache_hits += 1
                self.cache_hits_by_model[requested_model] = (
                    self.cache_hits_by_model.get(requested_model, 0) + 1
                )
                return

            self.consecutive_service_failures = 0
            call_count = call_result.metrics.get(
                "fact_model_calls", 1
            ) + call_result.metrics.get("output_correction_calls", 0)
            self.model_calls += call_count
            self.model_calls_by_model[requested_model] = (
                self.model_calls_by_model.get(requested_model, 0) + call_count
            )
            _add_usage(self.usage, call_result.usage)
            model_usage = self.usage_by_model.setdefault(requested_model, {})
            _add_usage(model_usage, call_result.usage)
            _add_usage(self.request_metrics, call_result.metrics)

    def record_failure(self, exc: Exception) -> int:
        is_service_error = _is_model_service_error(exc)
        with self._lock:
            self.model_failures += 1
            if is_service_error:
                self.consecutive_service_failures += 1
                self.last_service_error = str(exc)
            else:
                self.consecutive_service_failures = 0
            failure_count = self.consecutive_service_failures
        if failure_count >= 3 and self._on_model_degraded is not None:
            self._on_model_degraded(self.snapshot(), failure_count, str(exc))
        return failure_count

    def raise_if_service_paused(self) -> None:
        if not self._service_breaker.is_set():
            return
        with self._lock:
            failure_count = self.consecutive_service_failures
            error = self.last_service_error
        raise ModelServiceUnavailable(
            f"模型服务连续失败 {failure_count} 次，已自动暂停：{error}",
            failure_count,
        )

    def pause_after_failure(self, failure_count: int, exc: Exception) -> None:
        if failure_count < 5:
            return
        self._service_breaker.set()
        raise ModelServiceUnavailable(
            f"模型服务连续失败 {failure_count} 次，已自动暂停：{exc}",
            failure_count,
        ) from exc

    def add_result(
        self,
        classification_key: str,
        validated: ValidatedClassification,
    ) -> None:
        with self._lock:
            self.results[classification_key] = validated

    def snapshot(self) -> PipelineRun:
        with self._lock:
            return PipelineRun(
                classifications=dict(self.results),
                usage=dict(self.usage),
                usage_by_model={
                    key: dict(values) for key, values in self.usage_by_model.items()
                },
                cache_hits=self.cache_hits,
                cache_hits_by_model=dict(self.cache_hits_by_model),
                model_calls=self.model_calls,
                model_calls_by_model=dict(self.model_calls_by_model),
                request_metrics=dict(self.request_metrics),
                routing=dict(self.routing),
                model_failures=self.model_failures,
            )


class _CommentClassifier:
    def __init__(self, context: _PipelineContext, tracker: _RunTracker) -> None:
        self.context = context
        self.tracker = tracker
        self.cheap_model = getattr(context.client.settings, "cheap_model", None)
        self.cheap_model_audit_percent = int(
            getattr(context.client.settings, "cheap_model_audit_percent", 0)
        )

    def classify(self, row: Any) -> tuple[str, ValidatedClassification]:
        self._raise_if_cancelled()
        row_context = self._build_row_context(row)
        try:
            call_result, used_cheap_model = self._call_initial_model(row_context)
            validated = self._validate(row_context, call_result)
            if used_cheap_model:
                validated = self._resolve_cheap_result(
                    row_context,
                    call_result,
                    validated,
                )
            validated = self._resolve_secondary(row_context, validated)
        except (PipelineCancelled, ModelServiceUnavailable):
            raise
        except Exception as exc:
            validated = self._model_error(row_context.classification_key, exc)
        return row_context.classification_key, validated

    def _raise_if_cancelled(self) -> None:
        if self.context.should_cancel is not None and self.context.should_cancel():
            raise PipelineCancelled("分析任务已取消")

    def _build_row_context(self, row: Any) -> _RowContext:
        comment = row.comment_normalized
        category_a = str(getattr(row, "category_a", ""))
        category_b = str(getattr(row, "category_b", ""))
        classification_scope = f"{category_a}\x1f{category_b}"
        if self.context.analysis_context == "review":
            classification_scope += "\x1freview"
        input_has_semantic_risk = has_input_semantic_risk(comment)
        use_cheap_model = bool(self.cheap_model and not input_has_semantic_risk)
        self._record_initial_route(use_cheap_model, input_has_semantic_risk)
        return _RowContext(
            classification_key=row.classification_key,
            comment=comment,
            reason=row.reason,
            classification_scope=classification_scope,
            messages=build_messages(
                comment,
                self.context.taxonomy,
                self.context.claims,
                analysis_context=self.context.analysis_context,
                category_context={"品类A": category_a, "品类B": category_b},
            ),
            use_cheap_model=use_cheap_model,
            initial_model=(
                str(self.cheap_model)
                if use_cheap_model
                else self.context.client.settings.model
            ),
        )

    def _record_initial_route(
        self,
        use_cheap_model: bool,
        input_has_semantic_risk: bool,
    ) -> None:
        if use_cheap_model:
            self.tracker.increment_routing("cheap_first_pass")
        elif self.cheap_model and input_has_semantic_risk:
            self.tracker.increment_routing("input_risk_primary")

    def _call_initial_model(
        self,
        row: _RowContext,
    ) -> tuple[ModelCallResult, bool]:
        try:
            return self._call_model(row, row.initial_model), row.use_cheap_model
        except (PipelineCancelled, ModelServiceUnavailable):
            raise
        except Exception:
            if not row.use_cheap_model:
                raise
            self.tracker.increment_routing("cheap_error_fallback")
            return self._call_model(row, self.context.client.settings.model), False

    def _call_model(
        self,
        row: _RowContext,
        model_name: str,
        thinking: bool = False,
    ) -> ModelCallResult:
        self._raise_if_cancelled()
        self.tracker.raise_if_service_paused()
        try:
            call_result, cache_hit = _call_with_cache(
                comment=row.comment,
                model_name=model_name,
                thinking=thinking,
                messages=row.messages,
                taxonomy=self.context.taxonomy,
                claims=self.context.claims,
                client=self.context.client,
                cache=self.context.cache,
                force=self.context.force,
                classification_scope=row.classification_scope,
                model_policy_version=self.context.model_policy_version,
                should_cancel=self.context.should_cancel,
            )
        except PipelineCancelled:
            raise
        except Exception as exc:
            failure_count = self.tracker.record_failure(exc)
            self.tracker.pause_after_failure(failure_count, exc)
            raise
        self.tracker.record_call(model_name, call_result, cache_hit)
        return call_result

    def _validate(
        self,
        row: _RowContext,
        call_result: ModelCallResult,
    ) -> ValidatedClassification:
        return validate_classification(
            classification_key=row.classification_key,
            comment=row.comment,
            reason=row.reason,
            model_result=call_result.classification,
            taxonomy=self.context.taxonomy,
            claims=self.context.claims,
            model_name=call_result.model_name,
            prompt_version=prompt_version(self.context.taxonomy),
            analysis_context=self.context.analysis_context,
        )

    def _resolve_cheap_result(
        self,
        row: _RowContext,
        cheap_call: ModelCallResult,
        validated: ValidatedClassification,
    ) -> ValidatedClassification:
        cheap_result_accepted = can_accept_cheap_result(validated)
        audit_cheap_result = cheap_result_accepted and should_audit_cheap_model(
            row.comment,
            self.cheap_model_audit_percent,
        )
        if cheap_result_accepted and not audit_cheap_result:
            self.tracker.increment_routing("cheap_result_accepted")
            return validated

        route_name = "cheap_audited" if audit_cheap_result else "cheap_result_fallback"
        self.tracker.increment_routing(route_name)
        primary_call = self._call_model(row, self.context.client.settings.model)
        primary_validated = self._validate(row, primary_call)
        if not audit_cheap_result:
            return primary_validated
        return self._resolve_cheap_audit(
            cheap_call,
            validated,
            primary_call,
            primary_validated,
        )

    def _resolve_cheap_audit(
        self,
        cheap_call: ModelCallResult,
        cheap_validated: ValidatedClassification,
        primary_call: ModelCallResult,
        primary_validated: ValidatedClassification,
    ) -> ValidatedClassification:
        combined_model_name = f"{cheap_call.model_name} + {primary_call.model_name}"
        if primary_validated.status != ProcessingStatus.AUTO_APPROVED:
            self.tracker.increment_routing("cheap_audit_primary_rejected")
            return primary_validated
        if classifications_match(cheap_validated, primary_validated):
            self.tracker.increment_routing("cheap_audit_agreement")
            return primary_validated.model_copy(
                update={"model_name": combined_model_name}
            )
        self.tracker.increment_routing("cheap_disagreement")
        return primary_validated.model_copy(
            update={
                "status": ProcessingStatus.SECONDARY_REVIEW,
                "review_reasons": primary_validated.review_reasons
                + ["低成本模型与主模型结果不一致"],
                "model_name": combined_model_name,
            }
        )

    def _resolve_secondary(
        self,
        row: _RowContext,
        validated: ValidatedClassification,
    ) -> ValidatedClassification:
        if not self.context.secondary_model or not should_run_secondary(validated):
            return validated
        try:
            review_call = self._call_model(
                row,
                self.context.secondary_model,
                thinking=True,
            )
            reviewed = reconcile_secondary(
                validated,
                self._validate(row, review_call),
            )
            return self._mark_secondary_fallback(reviewed)
        except (PipelineCancelled, ModelServiceUnavailable):
            raise
        except Exception as exc:
            return validated.model_copy(
                update={
                    "status": ProcessingStatus.MANUAL_REVIEW,
                    "review_reasons": validated.review_reasons
                    + [f"二次模型调用失败: {exc}"],
                }
            )

    def _mark_secondary_fallback(
        self,
        validated: ValidatedClassification,
    ) -> ValidatedClassification:
        if not self.context.secondary_is_fallback:
            return validated
        return validated.model_copy(
            update={
                "status": ProcessingStatus.MANUAL_REVIEW,
                "review_reasons": validated.review_reasons
                + ["风险复核模型缺失，已使用主模型复核"],
            }
        )

    def _model_error(
        self,
        classification_key: str,
        exc: Exception,
    ) -> ValidatedClassification:
        return ValidatedClassification(
            classification_key=classification_key,
            semantic_units=[],
            unknown_semantics=[],
            problem_label_codes=[],
            positive_label_codes=[],
            primary_label_codes=[],
            status=ProcessingStatus.MODEL_ERROR,
            review_reasons=[str(exc)],
            model_name=self.context.client.settings.model,
            prompt_version=prompt_version(self.context.taxonomy),
            taxonomy_version=self.context.taxonomy.version,
        )


def _classify_selected_comments(
    selected: pd.DataFrame,
    classifier: _CommentClassifier,
    max_workers: int,
    progress: Callable[[int, int], None] | None,
    checkpoint: Callable[[PipelineRun], None] | None,
) -> PipelineRun:
    total = len(selected)
    rows = list(selected.itertuples(index=False))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(classifier.classify, row) for row in rows]
        for position, future in enumerate(as_completed(futures), start=1):
            classification_key, validated = future.result()
            classifier.tracker.add_result(classification_key, validated)
            if progress is not None:
                progress(position, total)
            if checkpoint is not None and (
                position == 1 or position == total or position % 5 == 0
            ):
                checkpoint(classifier.tracker.snapshot())
    run = classifier.tracker.snapshot()
    ordered_results = {
        row.classification_key: run.classifications[row.classification_key]
        for row in rows
        if row.classification_key in run.classifications
    }
    return replace(run, classifications=ordered_results)


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
    if analysis_context not in {"returns", "review"}:
        raise ValueError("不支持的分析场景")
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
            analysis_context=cast(
                Literal["returns", "review"],
                analysis_context,
            ),
        ),
        tracker,
    )
    return _classify_selected_comments(
        selected,
        classifier,
        max_workers,
        progress,
        checkpoint,
    )
