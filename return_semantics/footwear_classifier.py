from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace

from return_semantics.footwear_semantic import normalize_footwear_semantics
from return_semantics.model_client import ModelCallResult
from return_semantics.model_request_limit import (
    has_model_request_budget,
    model_request_limit,
)
from return_semantics.output_correction import _correction_errors, _correction_messages
from return_semantics.pipeline_classifier import _CommentClassifier
from return_semantics.pipeline_models import (
    ModelServiceUnavailable,
    PipelineCancelled,
    _RowContext,
)
from return_semantics.pipeline_recovery import (
    _is_timeout_error,
    _mark_secondary_fallback,
)
from return_semantics.pipeline_routing_policy import (
    can_accept_cheap_result,
    should_audit_cheap_model,
)
from return_semantics.review import should_run_secondary
from return_semantics.schemas import (
    ProcessingStatus,
    ReviewDiagnostic,
    ValidatedClassification,
)
from return_semantics.validator import collect_output_errors

_FIRST_PASS_RULES = """
鞋履首轮判定补充：
1. 分别确认穿脱动作与穿上后的合脚体验。明确说穿入或脱下费时、费力或无法完成，
   使用 FUNCTION_ON_OFF_U1；仅凭鞋口尺寸或没能穿进去，不推断穿上后偏紧。
2. 以当前穿着者实际体验判定尺码。仅比另一品牌或另一双鞋小，且原文只明确说明穿脱困难时，
   记录穿脱困难，不推断 FIT_TOO_SMALL_U1。明确整体偏小导致穿不进去时，按同一问题保留整体偏小。
3. 合读标题和正文。已明确说过宽或过松、整体偏大的说法只是同一问题的概括时，
   优先 FIT_TOO_LOOSE_WIDE_U1。只有独立的整体尺码偏大体验才另判 FIT_TOO_LARGE_U1。
4. 原文明确鞋体材料被撕开或撕碎，使用 QUALITY_TEAR_U1，附上支持撕裂方式的原文。
   只说散开且不明方式才用 QUALITY_FALLING_APART_U1。明确开线、分离或仅纤维磨散时，使用各自具体标签。
5. 明确抱怨鞋底过薄，能感觉到脚下石子只是同一体验的后果时，使用 EXPERIENCE_THIN_U1，部位用 OUTSOLE。
   单纯说鞋底薄不判负向。明确说足部未得到保护或发生伤害时，才按该观点使用 FUNCTION_PROTECTION_U1。
6. 先合读标题和正文，确认损坏已发生，再选择质量标签。
   - 已发生的故障有明确失效方式时，用该方式的具体标签。没有明确方式，但清楚说明正常使用很快失效时，
     使用 QUALITY_DURABILITY_U1，保留使用时长。例如首次穿着鞋底就失效，保留不耐用，不改成笼统质量评价。
   - 只有明确陈述鞋已损坏、且没有更具体的失效方式或寿命信息时，才用负向 QUALITY_UNSPECIFIED_U1。
     局部笔误不否定清楚的损坏陈述，也不据此推断部位、方式或发生阶段。
   - 正文只预测未来可能损坏、尚未使用或没有看到实际损坏时，不从“看起来脆弱”之类的标题单独打标。
     这种预测不输出负向质量或耐用性标签，不列为主因。原文明确报告的其他真实体验仍按相应规则处理。
""".strip()


@dataclass(frozen=True)
class _OutputRepair:
    model: str
    thinking: bool
    errors: list[str]


class _FootwearClassifier(_CommentClassifier):
    def _call_initial_model(self, row: _RowContext) -> tuple[ModelCallResult, bool]:
        system, *rest = row.messages
        initial_row = replace(
            row,
            messages=[
                {**system, "content": f"{system['content']}\n\n{_FIRST_PASS_RULES}"},
                *rest,
            ],
            classification_scope=f"{row.classification_scope}\x1f首轮判定",
        )
        return super()._call_initial_model(initial_row)

    def _normalize(self, row: _RowContext, result: ModelCallResult) -> ModelCallResult:
        return replace(
            result,
            classification=normalize_footwear_semantics(
                result.classification, row.comment, self.context.taxonomy
            ),
        )

    def _validate(
        self, row: _RowContext, call_result: ModelCallResult
    ) -> ValidatedClassification:
        return super()._validate(row, self._normalize(row, call_result))

    def _errors(self, row: _RowContext, result: ModelCallResult) -> list[str]:
        return collect_output_errors(
            result.classification,
            row.comment,
            self.context.taxonomy,
            self.context.claims,
        )

    def _cheap_needs_review(
        self, row: _RowContext, result: ValidatedClassification
    ) -> bool:
        return not can_accept_cheap_result(result) or should_audit_cheap_model(
            row.comment, self.cheap_model_audit_percent
        )

    def _classify_row(self, row: _RowContext) -> ValidatedClassification:
        with model_request_limit(2):
            return self._classify_with_budget(row)

    def _classify_with_budget(self, row: _RowContext) -> ValidatedClassification:
        original, used_cheap = self._call_initial_model(row)
        normalized = self._normalize(row, original)
        validated = super()._validate(row, normalized)
        if used_cheap and not self._cheap_needs_review(row, validated):
            self.tracker.increment_routing("cheap_result_accepted")
        # 低成本模型调用失败时，既有主模型兜底已用完本条额外调用。
        if not has_model_request_budget() or (row.use_cheap_model and not used_cheap):
            return validated
        baseline = super()._validate(row, original)
        if not self._baseline_buys_review(row, original, baseline, used_cheap):
            return validated
        return self._review_once(row, normalized, validated, used_cheap)

    def _baseline_buys_review(
        self,
        row: _RowContext,
        raw: ModelCallResult,
        validated: ValidatedClassification,
        used_cheap: bool,
    ) -> bool:
        return bool(
            self._errors(row, raw)
            or (used_cheap and self._cheap_needs_review(row, validated))
            or (self.context.secondary_model and should_run_secondary(validated))
        )

    def _review_once(
        self,
        row: _RowContext,
        result: ModelCallResult,
        validated: ValidatedClassification,
        used_cheap: bool,
    ) -> ValidatedClassification:
        errors = self._errors(row, result)
        cheap_review = used_cheap and self._cheap_needs_review(row, validated)
        if not errors or (cheap_review and can_accept_cheap_result(validated)):
            if cheap_review:
                return self._resolve_cheap_result(row, result, validated)
            return self._resolve_secondary(row, validated)
        secondary = (
            self.context.secondary_model if should_run_secondary(validated) else None
        )
        if cheap_review:
            self.tracker.increment_routing("cheap_result_fallback")
        repair = _OutputRepair(
            model=self.context.client.settings.model
            if cheap_review
            else secondary or row.initial_model,
            thinking=bool(secondary and not cheap_review),
            errors=errors,
        )
        return self._repair_output(row, result, validated, repair)

    def _repair_output(
        self,
        row: _RowContext,
        original: ModelCallResult,
        validated: ValidatedClassification,
        repair: _OutputRepair,
    ) -> ValidatedClassification:
        messages = _correction_messages(original, row.messages, repair.errors)
        payload = json.dumps(messages[-2:], ensure_ascii=False)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        repair_row = replace(
            row,
            messages=messages,
            classification_scope=f"{row.classification_scope}\x1f纠正:{digest}",
        )
        try:
            candidate = self._normalize(
                row, self._call_model(repair_row, repair.model, repair.thinking)
            )
        except (PipelineCancelled, ModelServiceUnavailable):
            raise
        except Exception as exc:
            return validated.model_copy(
                update={
                    "status": ProcessingStatus.MANUAL_REVIEW,
                    "review_diagnostics": [
                        *validated.review_diagnostics,
                        ReviewDiagnostic(
                            code="SECONDARY_MODEL_TIMEOUT"
                            if _is_timeout_error(exc)
                            else "SECONDARY_MODEL_CALL_FAILED",
                            detail="鞋履输出纠正模型调用失败",
                            action="SYSTEM_RERUN",
                        ),
                    ],
                }
            )
        remaining = _correction_errors(
            original, candidate, row.comment, self.context.taxonomy, self.context.claims
        )
        if _adds_more_units_than_repaired(original, validated, candidate):
            remaining.append("输出纠正增加了超出原错误范围的语义")
        if not set(validated.primary_label_codes).issubset(
            candidate.classification.primary_label_codes
        ):
            remaining.append("输出纠正丢失原有有效主因")
        if remaining:
            self.tracker.increment_routing("footwear_output_repair_rejected")
            return validated.model_copy(
                update={
                    "status": ProcessingStatus.MANUAL_REVIEW,
                    "review_reasons": [*validated.review_reasons, *remaining],
                }
            )
        self.tracker.increment_routing("footwear_output_repair_accepted")
        reviewed = super()._validate(row, candidate)
        return (
            _mark_secondary_fallback(self.context, reviewed)
            if repair.thinking
            else reviewed
        )


def _adds_more_units_than_repaired(
    original: ModelCallResult,
    validated: ValidatedClassification,
    candidate: ModelCallResult,
) -> bool:
    existing = {
        unit.model_dump_json()
        for unit in (*validated.semantic_units, *validated.unknown_semantics)
    }
    additions = sum(
        unit.model_dump_json() not in existing
        for unit in (
            *candidate.classification.semantic_units,
            *candidate.classification.unknown_semantics,
        )
    )
    repair_limit = (
        len(original.classification.semantic_units)
        + len(original.classification.unknown_semantics)
        - len(validated.semantic_units)
        - len(validated.unknown_semantics)
    )
    return additions > max(0, repair_limit)
