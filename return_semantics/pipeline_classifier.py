"""协调单条评论的模型路由、分类校验与复核。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from return_semantics.analysis_context import RETURNS_CONTEXT
from return_semantics.model_client import ModelCallResult
from return_semantics.pipeline_metrics import _RunTracker
from return_semantics.pipeline_models import (
    ModelServiceUnavailable,
    PipelineCancelled,
    _PipelineContext,
    _RowContext,
)
from return_semantics.pipeline_recovery import (
    _is_timeout_error,
    _mark_secondary_fallback,
    _model_error,
)
from return_semantics.pipeline_routing_policy import (
    can_accept_cheap_result,
    has_input_semantic_risk,
    should_audit_cheap_model,
)
from return_semantics.prompt import build_messages, prompt_version
from return_semantics.review import (
    build_model_difference_diagnostics,
    classifications_match,
    reconcile_secondary,
    should_run_secondary,
)
from return_semantics.schemas import (
    ProcessingStatus,
    ReviewDiagnostic,
    ValidatedClassification,
)
from return_semantics.validator import validate_classification


class _CommentClassifier:
    def __init__(
        self,
        context: _PipelineContext,
        tracker: _RunTracker,
        cached_call: Callable[
            [_RowContext, _PipelineContext, str, bool], tuple[ModelCallResult, bool]
        ],
    ) -> None:
        self.cached_call = cached_call
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
            validated = _model_error(self.context, row_context.classification_key, exc)
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
            call_result, cache_hit = self.cached_call(
                row, self.context, model_name, thinking
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
            return _mark_secondary_fallback(self.context, reviewed)
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
