from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from threading import Event, Lock

import pandas as pd

from return_semantics.model_client import (
    JsonlCache,
    ModelCallResult,
    ModelClient,
    ModelHTTPError,
)
from return_semantics.prompt import PROMPT_VERSION, build_messages
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
) -> str:
    payload = {
        "comment": comment.lower(),
        "model": f"{model_name}:thinking" if thinking else model_name,
        "prompt": PROMPT_VERSION,
        "taxonomy": taxonomy_version,
        "claims": claims_version,
        "scope": classification_scope,
        "effort": reasoning_effort,
        "model_policy": model_policy_version,
    }
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
        thinking=thinking,
        classification_scope=classification_scope,
        reasoning_effort=str(reasoning_effort),
        model_policy_version=model_policy_version,
    )
    with cache.lock_for(cache_key):
        cached = None if force else cache.get(cache_key)
        if cached is not None:
            return cached, True

        result = client.classify(
            messages=messages,
            model=model_name,
            thinking=thinking,
        )
        cache.put(cache_key, result)
        return result, False


def _add_usage(total: dict[str, int], usage: dict[str, int]) -> None:
    for key, value in usage.items():
        total[key] = total.get(key, 0) + value


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
) -> PipelineRun:
    selected = unique_comments.iloc[offset:]
    if limit is not None:
        selected = selected.head(limit)

    results: dict[str, ValidatedClassification] = {}
    usage: dict[str, int] = {}
    usage_by_model: dict[str, dict[str, int]] = {}
    cache_hits = 0
    cache_hits_by_model: dict[str, int] = {}
    model_calls = 0
    model_calls_by_model: dict[str, int] = {}
    model_failures = 0
    consecutive_service_failures = 0
    last_service_error = ""
    request_metrics: dict[str, int] = {}
    routing: dict[str, int] = {}
    cheap_model = getattr(client.settings, "cheap_model", None)
    cheap_model_audit_percent = int(
        getattr(client.settings, "cheap_model_audit_percent", 0)
    )
    total = len(selected)

    max_workers = max(
        1,
        int(getattr(client.settings, "max_workers", 1)),
    )
    tracking_lock = Lock()
    service_breaker = Event()

    def increment_routing(route_name: str) -> None:
        with tracking_lock:
            routing[route_name] = routing.get(route_name, 0) + 1

    def record_call(
        requested_model: str,
        call_result: ModelCallResult,
        cache_hit: bool,
    ) -> None:
        nonlocal cache_hits, model_calls, consecutive_service_failures
        with tracking_lock:
            if cache_hit:
                cache_hits += 1
                cache_hits_by_model[requested_model] = (
                    cache_hits_by_model.get(requested_model, 0) + 1
                )
                return

            consecutive_service_failures = 0
            model_calls += 1
            model_calls_by_model[requested_model] = (
                model_calls_by_model.get(requested_model, 0) + 1
            )
            _add_usage(usage, call_result.usage)
            model_usage = usage_by_model.setdefault(requested_model, {})
            _add_usage(model_usage, call_result.usage)
            _add_usage(request_metrics, call_result.metrics)

    def record_failure(exc: Exception) -> int:
        nonlocal model_failures, consecutive_service_failures, last_service_error
        is_service_error = _is_model_service_error(exc)
        with tracking_lock:
            model_failures += 1
            if is_service_error:
                consecutive_service_failures += 1
                last_service_error = str(exc)
            else:
                consecutive_service_failures = 0
            failure_count = consecutive_service_failures
        if failure_count >= 3 and on_model_degraded is not None:
            on_model_degraded(snapshot_run(), failure_count, str(exc))
        return failure_count

    def classify_row(row) -> tuple[str, ValidatedClassification]:
        if should_cancel is not None and should_cancel():
            raise PipelineCancelled("分析任务已取消")
        classification_key = row.classification_key
        comment = row.comment_normalized
        category_a = str(getattr(row, "category_a", ""))
        category_b = str(getattr(row, "category_b", ""))
        classification_scope = f"{category_a}\x1f{category_b}"
        messages = build_messages(
            comment,
            taxonomy,
            claims,
            category_context={
                "品类A": category_a,
                "品类B": category_b,
            },
        )
        input_has_semantic_risk = has_input_semantic_risk(comment)
        use_cheap_model = bool(cheap_model and not input_has_semantic_risk)
        initial_model = str(cheap_model) if use_cheap_model else client.settings.model
        if use_cheap_model:
            increment_routing("cheap_first_pass")
        elif cheap_model and input_has_semantic_risk:
            increment_routing("input_risk_primary")

        def call_and_track(
            model_name: str,
            thinking: bool = False,
        ) -> ModelCallResult:
            if should_cancel is not None and should_cancel():
                raise PipelineCancelled("分析任务已取消")
            if service_breaker.is_set():
                with tracking_lock:
                    failure_count = consecutive_service_failures
                    error = last_service_error
                raise ModelServiceUnavailable(
                    f"模型服务连续失败 {failure_count} 次，已自动暂停：{error}",
                    failure_count,
                )
            try:
                call_result, cache_hit = _call_with_cache(
                    comment=comment,
                    model_name=model_name,
                    thinking=thinking,
                    messages=messages,
                    taxonomy=taxonomy,
                    claims=claims,
                    client=client,
                    cache=cache,
                    force=force,
                    classification_scope=classification_scope,
                    model_policy_version=model_policy_version,
                )
            except PipelineCancelled:
                raise
            except Exception as exc:
                failure_count = record_failure(exc)
                if failure_count >= 5:
                    service_breaker.set()
                    raise ModelServiceUnavailable(
                        f"模型服务连续失败 {failure_count} 次，已自动暂停：{exc}",
                        failure_count,
                    ) from exc
                raise
            record_call(model_name, call_result, cache_hit)
            return call_result

        try:
            try:
                call_result = call_and_track(initial_model)
            except (PipelineCancelled, ModelServiceUnavailable):
                raise
            except Exception:
                if not use_cheap_model:
                    raise
                increment_routing("cheap_error_fallback")
                use_cheap_model = False
                initial_model = client.settings.model
                call_result = call_and_track(initial_model)

            validated = validate_classification(
                classification_key=classification_key,
                comment=comment,
                reason=row.reason,
                model_result=call_result.classification,
                taxonomy=taxonomy,
                claims=claims,
                model_name=call_result.model_name,
                prompt_version=PROMPT_VERSION,
            )

            if use_cheap_model:
                cheap_result_accepted = can_accept_cheap_result(validated)
                audit_cheap_result = cheap_result_accepted and should_audit_cheap_model(
                    comment,
                    cheap_model_audit_percent,
                )
                fallback_to_primary = not cheap_result_accepted
                if audit_cheap_result or fallback_to_primary:
                    route_name = (
                        "cheap_audited"
                        if audit_cheap_result
                        else "cheap_result_fallback"
                    )
                    increment_routing(route_name)
                    primary_result = call_and_track(client.settings.model)
                    primary_validated = validate_classification(
                        classification_key=classification_key,
                        comment=comment,
                        reason=row.reason,
                        model_result=primary_result.classification,
                        taxonomy=taxonomy,
                        claims=claims,
                        model_name=primary_result.model_name,
                        prompt_version=PROMPT_VERSION,
                    )
                    if not audit_cheap_result:
                        validated = primary_validated
                    elif primary_validated.status != ProcessingStatus.AUTO_APPROVED:
                        increment_routing("cheap_audit_primary_rejected")
                        validated = primary_validated
                    elif classifications_match(
                        validated,
                        primary_validated,
                    ):
                        increment_routing("cheap_audit_agreement")
                        validated = primary_validated.model_copy(
                            update={
                                "model_name": (
                                    f"{call_result.model_name} + "
                                    f"{primary_result.model_name}"
                                ),
                            }
                        )
                    else:
                        increment_routing("cheap_disagreement")
                        validated = primary_validated.model_copy(
                            update={
                                "status": ProcessingStatus.SECONDARY_REVIEW,
                                "review_reasons": (
                                    primary_validated.review_reasons
                                    + ["低成本模型与主模型结果不一致"]
                                ),
                                "model_name": (
                                    f"{call_result.model_name} + "
                                    f"{primary_result.model_name}"
                                ),
                            }
                        )
                else:
                    increment_routing("cheap_result_accepted")

            if secondary_model and should_run_secondary(validated):
                try:
                    review_result = call_and_track(
                        secondary_model,
                        thinking=True,
                    )
                    review_validated = validate_classification(
                        classification_key=classification_key,
                        comment=comment,
                        reason=row.reason,
                        model_result=review_result.classification,
                        taxonomy=taxonomy,
                        claims=claims,
                        model_name=review_result.model_name,
                        prompt_version=PROMPT_VERSION,
                    )
                    validated = reconcile_secondary(
                        validated,
                        review_validated,
                    )
                    if secondary_is_fallback:
                        validated = validated.model_copy(
                            update={
                                "status": ProcessingStatus.MANUAL_REVIEW,
                                "review_reasons": validated.review_reasons
                                + ["风险复核模型缺失，已使用主模型复核"],
                            }
                        )
                except (PipelineCancelled, ModelServiceUnavailable):
                    raise
                except Exception as exc:
                    validated = validated.model_copy(
                        update={
                            "status": ProcessingStatus.MANUAL_REVIEW,
                            "review_reasons": validated.review_reasons
                            + [f"二次模型调用失败: {exc}"],
                        }
                    )
        except (PipelineCancelled, ModelServiceUnavailable):
            raise
        except Exception as exc:
            validated = ValidatedClassification(
                classification_key=classification_key,
                semantic_units=[],
                unknown_semantics=[],
                problem_label_codes=[],
                positive_label_codes=[],
                primary_label_codes=[],
                status=ProcessingStatus.MODEL_ERROR,
                review_reasons=[str(exc)],
                model_name=client.settings.model,
                prompt_version=PROMPT_VERSION,
                taxonomy_version=taxonomy.version,
            )

        return classification_key, validated

    def snapshot_run() -> PipelineRun:
        with tracking_lock:
            return PipelineRun(
                classifications=dict(results),
                usage=dict(usage),
                usage_by_model={
                    key: dict(values) for key, values in usage_by_model.items()
                },
                cache_hits=cache_hits,
                cache_hits_by_model=dict(cache_hits_by_model),
                model_calls=model_calls,
                model_calls_by_model=dict(model_calls_by_model),
                request_metrics=dict(request_metrics),
                routing=dict(routing),
                model_failures=model_failures,
            )

    rows = list(selected.itertuples(index=False))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        classified_rows = executor.map(classify_row, rows)
        for position, item in enumerate(classified_rows, start=1):
            classification_key, validated = item
            with tracking_lock:
                results[classification_key] = validated
            if progress is not None:
                progress(position, total)
            if checkpoint is not None and (
                position == 1 or position == total or position % 5 == 0
            ):
                checkpoint(snapshot_run())

    return snapshot_run()
