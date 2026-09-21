from __future__ import annotations

from collections.abc import Callable

from return_semantics.dimension_decisions import (
    compile_dimension_decisions as compile_dimension_decisions,
)
from return_semantics.fact_classification import (
    compile_evidence_label_adjudications as compile_evidence_label_adjudications,
)
from return_semantics.fact_classification import (
    compile_fact_classification as compile_fact_classification,
)
from return_semantics.fact_extraction import (
    CoverageMergeResult as CoverageMergeResult,
)
from return_semantics.fact_extraction import (
    FactPipelineCancelled as FactPipelineCancelled,
)
from return_semantics.fact_extraction import (
    _messages,
    _normalize_fact_branch_codes,
    _restore_evidence_spans,
    _validate_facts,
)
from return_semantics.fact_extraction import (
    coverage_audit_messages as coverage_audit_messages,
)
from return_semantics.fact_extraction import (
    coverage_correction_messages as coverage_correction_messages,
)
from return_semantics.fact_extraction import (
    extraction_messages as extraction_messages,
)
from return_semantics.fact_extraction import (
    merge_coverage_facts as merge_coverage_facts,
)
from return_semantics.fact_extraction import (
    validate_coverage_correction as validate_coverage_correction,
)
from return_semantics.fact_mapping import (
    EvidenceLabelAdjudication as EvidenceLabelAdjudication,
)
from return_semantics.fact_mapping import (
    EvidenceLabelAdjudications as EvidenceLabelAdjudications,
)
from return_semantics.fact_mapping import (
    FactDecisions as FactDecisions,
)
from return_semantics.fact_mapping import (
    FactMappings as FactMappings,
)
from return_semantics.fact_mapping import (
    ModelFactMapping as ModelFactMapping,
)
from return_semantics.fact_mapping import (
    ModelFactMappings as ModelFactMappings,
)
from return_semantics.fact_mapping import (
    _adjudication_messages,
    _adjudication_payload,
    _decision_payload,
    _mapping_messages,
    _mapping_payload,
    _parse_model_fact_mappings,
)
from return_semantics.fact_mapping import (
    _overlapping_fact_identity as _overlapping_fact_identity,
)
from return_semantics.fact_mapping import (
    _retain_fact_unit as _retain_fact_unit,
)
from return_semantics.model_client import ModelCallResult, ModelClient
from return_semantics.schemas import (
    ExtractedFact,
    FactExtraction,
    FactExtractionSource,
    ListingClaimsConfig,
    ModelClassification,
    ReviewDiagnostic,
    TaxonomyConfig,
)


class _ModelCallAccumulator:
    def __init__(
        self,
        generate: Callable,
        *,
        model_name: str,
        reasoning_effort: str,
        should_cancel: Callable[[], bool] | None,
    ) -> None:
        self.generate = generate
        self.model_name = model_name
        self.reasoning_effort = reasoning_effort
        self.should_cancel = should_cancel
        self.usage: dict[str, int] = {}
        self.metrics: dict[str, int] = {}
        self.calls = 0

    def __call__(self, messages: list[dict[str, str]]) -> dict:
        if self.should_cancel is not None and self.should_cancel():
            raise FactPipelineCancelled("事实识别已取消")
        response = self.generate(
            messages,
            model=self.model_name,
            reasoning_effort=self.reasoning_effort,
        )
        self.calls += 1
        for target, values in (
            (self.usage, response.usage),
            (self.metrics, response.metrics),
        ):
            for key, value in values.items():
                target[key] = target.get(key, 0) + value
        return response.payload


def _extract_primary_facts(
    payload: dict,
    *,
    taxonomy: TaxonomyConfig,
    comment: str,
) -> list[ExtractedFact]:
    normalized = dict(payload)
    if isinstance(normalized.get("facts"), list):
        normalized["facts"] = [
            {
                **item,
                "extraction_source": FactExtractionSource.PRIMARY,
            }
            if isinstance(item, dict)
            else item
            for item in normalized["facts"]
        ]
    facts = _normalize_fact_branch_codes(
        FactExtraction.model_validate(normalized).facts,
        taxonomy,
    )
    facts = _restore_evidence_spans(facts, comment)
    _validate_facts(facts, comment, taxonomy)
    _mapping_payload(facts, taxonomy)
    return facts


def _audit_fact_coverage(
    facts: list[ExtractedFact],
    *,
    comment: str,
    taxonomy: TaxonomyConfig,
    call: Callable,
    metrics: dict[str, int],
) -> CoverageMergeResult:
    metrics["coverage_audit_added_facts"] = 0
    metrics["coverage_audit_rejected_facts"] = 0
    metrics["coverage_audit_failures"] = 0
    metrics["coverage_audit_repair_calls"] = 0
    metrics["coverage_audit_repaired_facts"] = 0
    try:
        response = call(coverage_audit_messages(comment, facts, taxonomy))
        merged = merge_coverage_facts(
            facts,
            response,
            comment=comment,
            taxonomy=taxonomy,
        )
    except FactPipelineCancelled:
        raise
    except Exception as exc:
        metrics["coverage_audit_failures"] += 1
        return CoverageMergeResult(
            facts=facts,
            added=0,
            rejected=0,
            diagnostics=[
                ReviewDiagnostic(
                    code="COVERAGE_AUDIT_FAILED",
                    detail=f"覆盖审计未完成：{exc}",
                    action="SYSTEM_RERUN",
                )
            ],
        )
    if merged.rejections:
        metrics["coverage_audit_repair_calls"] = 1
        try:
            response = call(
                coverage_correction_messages(
                    comment,
                    merged.facts,
                    merged.rejections,
                    taxonomy,
                )
            )
            validate_coverage_correction(response, merged.rejected)
            repaired = merge_coverage_facts(
                merged.facts,
                response,
                comment=comment,
                taxonomy=taxonomy,
            )
        except FactPipelineCancelled:
            raise
        except Exception as exc:
            merged = CoverageMergeResult(
                facts=merged.facts,
                added=merged.added,
                rejected=merged.rejected,
                diagnostics=[
                    diagnostic.model_copy(
                        update={
                            "detail": (
                                f"{diagnostic.detail}；覆盖审计自动修复未完成：{exc}"
                            )
                        }
                    )
                    for diagnostic in merged.diagnostics
                ],
                rejections=merged.rejections,
            )
        else:
            metrics["coverage_audit_repaired_facts"] = repaired.added
            merged = CoverageMergeResult(
                facts=repaired.facts,
                added=len(repaired.facts) - len(facts),
                rejected=repaired.rejected,
                diagnostics=repaired.diagnostics,
                rejections=repaired.rejections,
            )

    metrics["coverage_audit_added_facts"] = merged.added
    metrics["coverage_audit_rejected_facts"] = merged.rejected
    if merged.rejected:
        metrics["coverage_audit_failures"] = 1
    return merged


def _adjudicate_classification(
    classification: ModelClassification,
    *,
    payload: dict,
    comment: str,
    taxonomy: TaxonomyConfig,
    call: Callable,
    metrics: dict[str, int],
) -> ModelClassification:
    adjudication_payload = _adjudication_payload(
        classification,
        taxonomy,
        comment,
        payload["allowed_labels_by_fact"],
    )
    if adjudication_payload["facts"]:

        def compile_adjudications(response: dict) -> ModelClassification:
            return compile_evidence_label_adjudications(
                classification,
                EvidenceLabelAdjudications.model_validate(response),
                comment=comment,
                taxonomy=taxonomy,
                allowed=payload["allowed_labels_by_fact"],
                recovery_metrics=metrics,
            )

        def recover_adjudications(response: dict) -> ModelClassification:
            try:
                safe_review = EvidenceLabelAdjudications.model_validate(response)
            except ValueError:
                safe_review = EvidenceLabelAdjudications(
                    adjudications=[
                        EvidenceLabelAdjudication(
                            fact_id=fact["fact_id"],
                            action="REVIEW",
                            reason="证据-标签裁决输出未通过结构校验",
                        )
                        for fact in adjudication_payload["facts"]
                    ]
                )
            return compile_evidence_label_adjudications(
                classification,
                safe_review,
                comment=comment,
                taxonomy=taxonomy,
                allowed=payload["allowed_labels_by_fact"],
                recover_invalid_actions=True,
                recovery_metrics=metrics,
            )

        classification = _validated_stage(
            _adjudication_messages(adjudication_payload),
            call,
            compile_adjudications,
            recover_adjudications,
        )
    return classification


def classify_facts(
    *,
    comment: str,
    taxonomy: TaxonomyConfig,
    client: ModelClient,
    model_name: str,
    reasoning_effort: str,
    claims: ListingClaimsConfig | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> ModelCallResult:
    generate = getattr(client, "generate_json", None)
    if generate is None:
        raise ValueError("fact_v2需要支持JSON生成的模型客户端")
    caller = _ModelCallAccumulator(
        generate,
        model_name=model_name,
        reasoning_effort=reasoning_effort,
        should_cancel=should_cancel,
    )
    call = caller
    metrics = caller.metrics
    facts = _validated_stage(
        extraction_messages(comment, taxonomy),
        call,
        lambda payload: _extract_primary_facts(
            payload,
            taxonomy=taxonomy,
            comment=comment,
        ),
    )
    coverage_merge = _audit_fact_coverage(
        facts,
        comment=comment,
        taxonomy=taxonomy,
        call=call,
        metrics=metrics,
    )
    facts = coverage_merge.facts
    classification = ModelClassification()
    if facts:
        payload = _mapping_payload(facts, taxonomy)

        def compile_mapping(response: dict) -> ModelClassification:
            return compile_fact_classification(
                facts,
                _parse_model_fact_mappings(response),
                comment=comment,
                taxonomy=taxonomy,
                allowed=payload["allowed_labels_by_fact"],
            )

        def recover_mapping(response: dict) -> ModelClassification:
            return compile_fact_classification(
                facts,
                _parse_model_fact_mappings(response),
                comment=comment,
                taxonomy=taxonomy,
                allowed=payload["allowed_labels_by_fact"],
                recover_mapping_errors=True,
            )

        classification = _validated_stage(
            _mapping_messages(payload),
            call,
            compile_mapping,
            recover_mapping,
        )
        classification = _adjudicate_classification(
            classification,
            payload=payload,
            comment=comment,
            taxonomy=taxonomy,
            call=call,
            metrics=metrics,
        )
        if taxonomy.validation_rules.dimension_contracts:
            decision_payload = _decision_payload(
                facts,
                classification.fact_mappings,
                taxonomy,
            )

            def compile_decisions(response: dict) -> ModelClassification:
                return compile_dimension_decisions(
                    classification,
                    FactDecisions.model_validate(response),
                    comment=comment,
                    taxonomy=taxonomy,
                )

            def recover_decisions(response: dict) -> ModelClassification:
                return compile_dimension_decisions(
                    classification,
                    FactDecisions.model_validate(response),
                    comment=comment,
                    taxonomy=taxonomy,
                    recover_invalid_decisions=True,
                )

            classification = _validated_stage(
                _dimension_decision_messages(decision_payload),
                call,
                compile_decisions,
                recover_decisions,
            )
    if claims and claims.claims:
        classification.needs_review = True
        classification.review_reasons.append(
            "fact_v2尚未完成Listing承诺关系核验，需人工确认；未推断承诺关系"
        )
    if coverage_merge.diagnostics:
        classification.needs_review = True
        classification.review_reasons.append("覆盖审计失败，分析结果尚未完成")
        classification.review_diagnostics.extend(coverage_merge.diagnostics)
    metrics["fact_model_calls"] = caller.calls
    return ModelCallResult(classification, model_name, caller.usage, metrics)


def _validated_stage(
    messages: list[dict[str, str]],
    call: Callable,
    validate: Callable,
    recover: Callable | None = None,
):
    """只修复失败阶段一次，不重新支付已通过阶段的模型调用。"""
    try:
        return validate(call(messages))
    except ValueError as exc:
        correction = {
            "role": "user",
            "content": f"上次输出未通过校验：{exc}。请修复并重发完整JSON，不改写输入事实。",
        }
        repaired = call([*messages, correction])
        try:
            return validate(repaired)
        except ValueError:
            if recover is None:
                raise
            return recover(repaired)


def _dimension_decision_messages(payload: dict) -> list[dict[str, str]]:
    return _messages(
        "根据全部事实、候选映射与维度契约生成最终维度结论，输出schema规定JSON。"
        "候选标签不是终态标签；每个contract按scope_fields分组，同一父维度同一作用域只能一个verdict。"
        "同一decision中的事实必须属于同一contract管理的可比较业务维度；"
        "不能仅因共享更上层分类、相同方向或相似措辞而合并不同维度事实。"
        "scope中未由contract声明的字段必须保持schema默认值，不能通过填写operation、condition等字段拆分冲突。"
        "supporting_fact_ids只放直接支持verdict且已确认的事实，至少一个必须是CONCLUSION，"
        "或fact_mappings中已由adjudication_action=ACCEPT/REPLACE晋升的EVIDENCE；"
        "相反候选、最低能力、比较背景、转折前件与限定信息放context_fact_ids。"
        "context事实必须属于当前父维度并与decision的scope_fields完全一致；"
        "无独立标签但已被最终结论解释的事实也应放入context_fact_ids。"
        "转折让步按完整命题的最终立场裁决；基础可用不等于性能正向，明确的速度、准确性、稳定性或限制优先。"
        "比较基准不等于评价对象；尺码表标定偏差不能变成本人穿戴偏小，"
        "轻微偏差但明确接受或拒绝调整不能变成需要纠正的缺陷。"
        "所有受contract管理的已确认候选事实必须进入同父级、同作用域decision的supporting或context，"
        "不得静默丢弃，也不得跨使用者、商品、规格或作用域借用context覆盖。"
        "未来意图、预测、假设、否认和未测试事实不能支持已确认verdict。",
        payload,
    )
