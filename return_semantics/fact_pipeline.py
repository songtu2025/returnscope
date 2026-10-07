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
from return_semantics.fact_coverage_audit import (
    _audit_fact_coverage as _audit_fact_coverage,
)
from return_semantics.fact_coverage_audit import _extract_audited_facts
from return_semantics.fact_execution import (
    _extract_primary_facts as _extract_primary_facts,
)
from return_semantics.fact_execution import _FactExecutionContext
from return_semantics.fact_execution import (
    _ModelCallAccumulator as _ModelCallAccumulator,
)
from return_semantics.fact_execution import (
    _validated_stage as _validated_stage,
)
from return_semantics.fact_extraction import (
    CoverageMergeResult as CoverageMergeResult,
)
from return_semantics.fact_extraction import (
    FactPipelineCancelled as FactPipelineCancelled,
)
from return_semantics.fact_extraction import (
    _messages as _messages,
)
from return_semantics.fact_extraction import (
    _normalize_fact_branch_codes as _normalize_fact_branch_codes,
)
from return_semantics.fact_extraction import (
    _restore_evidence_spans as _restore_evidence_spans,
)
from return_semantics.fact_extraction import (
    _validate_facts as _validate_facts,
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
    _adjudication_messages as _adjudication_messages,
)
from return_semantics.fact_mapping import (
    _adjudication_payload as _adjudication_payload,
)
from return_semantics.fact_mapping import (
    _decision_payload as _decision_payload,
)
from return_semantics.fact_mapping import (
    _mapping_messages as _mapping_messages,
)
from return_semantics.fact_mapping import (
    _mapping_payload as _mapping_payload,
)
from return_semantics.fact_mapping import (
    _overlapping_fact_identity as _overlapping_fact_identity,
)
from return_semantics.fact_mapping import (
    _parse_model_fact_mappings as _parse_model_fact_mappings,
)
from return_semantics.fact_mapping import (
    _retain_fact_unit as _retain_fact_unit,
)
from return_semantics.fact_stages import (
    _adjudicate_classification as _adjudicate_classification,
)
from return_semantics.fact_stages import (
    _classify_fact_stages,
    _finalize_fact_review,
)
from return_semantics.fact_stages import (
    _dimension_decision_messages as _dimension_decision_messages,
)
from return_semantics.model_client import ModelCallResult, ModelClient
from return_semantics.schemas import (
    ListingClaimsConfig,
    ModelClassification,
    TaxonomyConfig,
)


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
    coverage_merge = _extract_audited_facts(
        comment=comment,
        taxonomy=taxonomy,
        call=call,
        metrics=metrics,
    )
    facts = coverage_merge.facts
    classification = ModelClassification()
    if facts:
        context = _FactExecutionContext(
            comment=comment, taxonomy=taxonomy, call=call, metrics=metrics
        )
        classification = _classify_fact_stages(facts, context=context)
    _finalize_fact_review(classification, coverage_merge, claims)

    metrics["fact_model_calls"] = caller.calls
    return ModelCallResult(classification, model_name, caller.usage, metrics)


# 保留原辅助入口的模块归属及可调用签名。
for _entry in (
    _ModelCallAccumulator,
    _extract_primary_facts,
    _validated_stage,
    _audit_fact_coverage,
    _adjudicate_classification,
    _dimension_decision_messages,
):
    _entry.__module__ = __name__
del _entry
