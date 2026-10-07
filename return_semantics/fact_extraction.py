from __future__ import annotations

from return_semantics.fact_coverage import (
    CoverageFactRejection as CoverageFactRejection,
)
from return_semantics.fact_coverage import CoverageMergeResult as CoverageMergeResult
from return_semantics.fact_coverage import (
    _coverage_fact_identity as _coverage_fact_identity,
)
from return_semantics.fact_coverage import (
    _coverage_failure_diagnostic as _coverage_failure_diagnostic,
)
from return_semantics.fact_coverage import merge_coverage_facts as merge_coverage_facts
from return_semantics.fact_coverage import (
    validate_coverage_correction as validate_coverage_correction,
)
from return_semantics.fact_evidence import _SCOPE_DEFAULTS as _SCOPE_DEFAULTS
from return_semantics.fact_evidence import (
    _UNCERTAIN_STATEMENT_TYPES as _UNCERTAIN_STATEMENT_TYPES,
)
from return_semantics.fact_evidence import _decision_evidence as _decision_evidence
from return_semantics.fact_evidence import (
    _decision_evidence_source as _decision_evidence_source,
)
from return_semantics.fact_evidence import _evidence as _evidence
from return_semantics.fact_evidence import _evidence_source as _evidence_source
from return_semantics.fact_evidence import _fact_assertion as _fact_assertion
from return_semantics.fact_evidence import _fact_context as _fact_context
from return_semantics.fact_evidence import (
    _restore_evidence_spans as _restore_evidence_spans,
)
from return_semantics.fact_evidence import (
    _validate_decision_scope as _validate_decision_scope,
)
from return_semantics.fact_evidence import _validate_facts as _validate_facts
from return_semantics.fact_evidence import _validate_reference as _validate_reference
from return_semantics.fact_prompts import _messages as _messages
from return_semantics.fact_prompts import (
    coverage_audit_messages as coverage_audit_messages,
)
from return_semantics.fact_prompts import (
    coverage_correction_messages as coverage_correction_messages,
)
from return_semantics.fact_prompts import extraction_messages as extraction_messages
from return_semantics.fact_routing import (
    _allowed_labels_by_fact as _allowed_labels_by_fact,
)
from return_semantics.fact_routing import _branch_catalog as _branch_catalog
from return_semantics.fact_routing import (
    _normalize_fact_branch_codes as _normalize_fact_branch_codes,
)


class FactPipelineCancelled(RuntimeError):
    pass


# 保留已有入口的模块归属，避免移动实现影响反射和序列化。
for _entry in (
    CoverageFactRejection,
    CoverageMergeResult,
    validate_coverage_correction,
    _coverage_fact_identity,
    _coverage_failure_diagnostic,
    merge_coverage_facts,
    _restore_evidence_spans,
    _validate_facts,
    _validate_reference,
    _evidence,
    _evidence_source,
    _fact_context,
    _validate_decision_scope,
    _decision_evidence,
    _decision_evidence_source,
    _fact_assertion,
    _messages,
    extraction_messages,
    coverage_audit_messages,
    coverage_correction_messages,
    _branch_catalog,
    _allowed_labels_by_fact,
    _normalize_fact_branch_codes,
):
    _entry.__module__ = __name__
del _entry
