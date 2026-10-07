from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from return_semantics.dimension_decisions import compile_dimension_decisions
from return_semantics.fact_classification import (
    compile_evidence_label_adjudications,
    compile_fact_classification,
)
from return_semantics.fact_execution import _validated_stage
from return_semantics.fact_extraction import CoverageMergeResult, _messages
from return_semantics.fact_mapping import (
    EvidenceLabelAdjudication,
    EvidenceLabelAdjudications,
    FactDecisions,
    _adjudication_messages,
    _adjudication_payload,
    _decision_payload,
    _mapping_messages,
    _mapping_payload,
    _parse_model_fact_mappings,
)
from return_semantics.schemas import (
    ExtractedFact,
    ListingClaimsConfig,
    ModelClassification,
    TaxonomyConfig,
)


@dataclass(frozen=True, kw_only=True)
class _FactStageContext:
    comment: str
    taxonomy: TaxonomyConfig
    call: Callable
    metrics: dict[str, int]


def _adjudications_for_review(
    response: dict, adjudication_payload: dict
) -> EvidenceLabelAdjudications:
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
    return safe_review


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
            safe_review = _adjudications_for_review(response, adjudication_payload)
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


def _map_fact_classification(
    facts: list[ExtractedFact],
    payload: dict,
    *,
    context: _FactStageContext,
) -> ModelClassification:
    def compile_mapping(response: dict) -> ModelClassification:
        return compile_fact_classification(
            facts,
            _parse_model_fact_mappings(response),
            comment=context.comment,
            taxonomy=context.taxonomy,
            allowed=payload["allowed_labels_by_fact"],
        )

    def recover_mapping(response: dict) -> ModelClassification:
        return compile_fact_classification(
            facts,
            _parse_model_fact_mappings(response),
            comment=context.comment,
            taxonomy=context.taxonomy,
            allowed=payload["allowed_labels_by_fact"],
            recover_mapping_errors=True,
        )

    return _validated_stage(
        _mapping_messages(payload), context.call, compile_mapping, recover_mapping
    )


def _decide_fact_dimensions(
    classification: ModelClassification,
    facts: list[ExtractedFact],
    *,
    context: _FactStageContext,
) -> ModelClassification:
    decision_payload = _decision_payload(
        facts, classification.fact_mappings, context.taxonomy
    )

    def compile_decisions(response: dict) -> ModelClassification:
        return compile_dimension_decisions(
            classification,
            FactDecisions.model_validate(response),
            comment=context.comment,
            taxonomy=context.taxonomy,
        )

    def recover_decisions(response: dict) -> ModelClassification:
        return compile_dimension_decisions(
            classification,
            FactDecisions.model_validate(response),
            comment=context.comment,
            taxonomy=context.taxonomy,
            recover_invalid_decisions=True,
        )

    return _validated_stage(
        _dimension_decision_messages(decision_payload),
        context.call,
        compile_decisions,
        recover_decisions,
    )


def _classify_fact_stages(
    facts: list[ExtractedFact],
    *,
    context: _FactStageContext,
) -> ModelClassification:
    payload = _mapping_payload(facts, context.taxonomy)
    classification = _map_fact_classification(facts, payload, context=context)
    classification = _adjudicate_classification(
        classification,
        payload=payload,
        comment=context.comment,
        taxonomy=context.taxonomy,
        call=context.call,
        metrics=context.metrics,
    )
    if context.taxonomy.validation_rules.dimension_contracts:
        classification = _decide_fact_dimensions(classification, facts, context=context)
    return classification


def _finalize_fact_review(
    classification: ModelClassification,
    coverage_merge: CoverageMergeResult,
    claims: ListingClaimsConfig | None,
) -> None:
    if claims and claims.claims:
        classification.needs_review = True
        classification.review_reasons.append(
            "fact_v2尚未完成Listing承诺关系核验，需人工确认；未推断承诺关系"
        )
    if coverage_merge.diagnostics:
        classification.needs_review = True
        classification.review_reasons.append("覆盖审计失败，分析结果尚未完成")
        classification.review_diagnostics.extend(coverage_merge.diagnostics)


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
