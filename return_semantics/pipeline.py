from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from typing import Any

import pandas as pd

from return_semantics.analysis_context import (
    RETURNS_CONTEXT,
    validate_analysis_context,
)
from return_semantics.fact_pipeline import FactPipelineCancelled, classify_facts
from return_semantics.model_client import (
    JsonlCache,
    ModelCallResult,
    ModelClient,
)
from return_semantics.output_correction import correct_invalid_output
from return_semantics.pipeline_metrics import (
    _add_usage as _add_usage,
)
from return_semantics.pipeline_metrics import (
    _is_model_service_error as _is_model_service_error,
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
    _SEMANTIC_RISK_PATTERNS as _SEMANTIC_RISK_PATTERNS,
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
from return_semantics.prompt import (
    PROMPT_VERSION,
    build_messages,
    prompt_version,
    recognition_fingerprint,
)
from return_semantics.review import (
    build_model_difference_diagnostics,
    classifications_match,
    reconcile_secondary,
    should_run_secondary,
)
from return_semantics.schemas import (
    ListingClaimsConfig,
    ProcessingStatus,
    ReviewDiagnostic,
    TaxonomyConfig,
    ValidatedClassification,
)
from return_semantics.semantic_review import requires_system_rerun
from return_semantics.taxonomy import adapt_claims_to_taxonomy
from return_semantics.validator import validate_classification


def _is_timeout_error(exc: Exception) -> bool:
    current: BaseException | None = exc
    while current is not None:
        message = str(current).casefold()
        if isinstance(current, TimeoutError) or any(
            marker in message for marker in ("timeout", "timed out", "超时")
        ):
            return True
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


def _model_reasoning_effort(
    client: ModelClient, model_name: str, thinking: bool
) -> Any:
    if thinking:
        return getattr(client.settings, "secondary_reasoning_effort", "")
    if model_name == getattr(client.settings, "cheap_model", None):
        return getattr(client.settings, "cheap_reasoning_effort", "")
    return getattr(client.settings, "reasoning_effort", "")


def _cache_key_for_row(
    row: _RowContext,
    context: _PipelineContext,
    model_name: str,
    thinking: bool,
    reasoning_effort: Any,
) -> str:
    return build_cache_key(
        comment=row.comment,
        model_name=model_name,
        provider_name=context.client.settings.cache_namespace,
        taxonomy_version=context.taxonomy.version,
        claims_version=context.claims.version,
        effective_prompt_version=prompt_version(context.taxonomy),
        recognition_key=(
            recognition_fingerprint(context.taxonomy)
            if context.taxonomy.recognition_profile != "legacy_v3"
            else ""
        ),
        thinking=thinking,
        classification_scope=row.classification_scope,
        reasoning_effort=str(reasoning_effort),
        model_policy_version=context.model_policy_version,
    )


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
    reasoning_effort = _model_reasoning_effort(context.client, model_name, thinking)
    cache_key = _cache_key_for_row(row, context, model_name, thinking, reasoning_effort)
    with context.cache.lock_for(cache_key):
        cached = None if context.force else context.cache.get(cache_key)
        if cached is not None and not requires_system_rerun(
            cached.classification,
            row.comment,
            context.taxonomy,
        ):
            return cached, True
        result = _classify_uncached(
            row, context, model_name, thinking, reasoning_effort
        )
        if not requires_system_rerun(
            result.classification, row.comment, context.taxonomy
        ):
            context.cache.put(cache_key, result)
        return result, False


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
        if self.context.analysis_context != RETURNS_CONTEXT:
            classification_scope += f"\x1f{self.context.analysis_context}"
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
                row=row,
                context=self.context,
                model_name=model_name,
                thinking=thinking,
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
                "review_diagnostics": primary_validated.review_diagnostics
                + build_model_difference_diagnostics(
                    primary_validated,
                    cheap_validated,
                ),
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
            error_text = str(exc)
            return validated.model_copy(
                update={
                    "status": ProcessingStatus.MANUAL_REVIEW,
                    "review_reasons": validated.review_reasons
                    + [f"二次模型调用失败: {exc}"],
                    "review_diagnostics": validated.review_diagnostics
                    + [
                        ReviewDiagnostic(
                            code=(
                                "SECONDARY_MODEL_TIMEOUT"
                                if _is_timeout_error(exc)
                                else "SECONDARY_MODEL_CALL_FAILED"
                            ),
                            detail=error_text or "二次模型调用失败",
                            action="SYSTEM_RERUN",
                        )
                    ],
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
                "review_diagnostics": validated.review_diagnostics
                + [
                    ReviewDiagnostic(
                        code="SECONDARY_MODEL_MISSING",
                        detail="风险复核模型缺失，已使用主模型复核",
                        action="ADMIN_CONFIG",
                    )
                ],
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
            review_diagnostics=[
                ReviewDiagnostic(
                    code=(
                        "MODEL_RUN_TIMEOUT"
                        if _is_timeout_error(exc)
                        else "MODEL_RUN_FAILED"
                    ),
                    detail=str(exc),
                    action="SYSTEM_RERUN",
                )
            ],
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
    ordered_results: dict[str, ValidatedClassification] = {
        str(row.classification_key): run.classifications[str(row.classification_key)]
        for row in rows
        if str(row.classification_key) in run.classifications
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
_add_usage.__module__ = __name__
_is_model_service_error.__module__ = __name__
_RunTracker.__module__ = __name__
has_input_semantic_risk.__module__ = __name__
can_accept_cheap_result.__module__ = __name__
should_audit_cheap_model.__module__ = __name__
