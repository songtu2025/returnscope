from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from return_semantics.fact_schemas import (
    EvidenceSpan as EvidenceSpan,
)
from return_semantics.fact_schemas import (
    ExtractedFact as ExtractedFact,
)
from return_semantics.fact_schemas import (
    FactExtraction as FactExtraction,
)
from return_semantics.fact_schemas import (
    FactMapping as FactMapping,
)
from return_semantics.schema_vocabulary import (
    AssertionCode as AssertionCode,
)
from return_semantics.schema_vocabulary import (
    CausalAttributionCode as CausalAttributionCode,
)
from return_semantics.schema_vocabulary import (
    ClaimRelation as ClaimRelation,
)
from return_semantics.schema_vocabulary import (
    CommentSummaryStatus as CommentSummaryStatus,
)
from return_semantics.schema_vocabulary import (
    DimensionScopeField as DimensionScopeField,
)
from return_semantics.schema_vocabulary import (
    EvidenceSource as EvidenceSource,
)
from return_semantics.schema_vocabulary import (
    ExperiencerResolution as ExperiencerResolution,
)
from return_semantics.schema_vocabulary import (
    FactExtractionSource as FactExtractionSource,
)
from return_semantics.schema_vocabulary import (
    FactRelationType as FactRelationType,
)
from return_semantics.schema_vocabulary import (
    FactRole as FactRole,
)
from return_semantics.schema_vocabulary import (
    FactSpecificity as FactSpecificity,
)
from return_semantics.schema_vocabulary import (
    ProcessingStatus as ProcessingStatus,
)
from return_semantics.schema_vocabulary import (
    ReferenceBasis as ReferenceBasis,
)
from return_semantics.schema_vocabulary import (
    SemanticDisposition as SemanticDisposition,
)
from return_semantics.schema_vocabulary import (
    SemanticRelationType as SemanticRelationType,
)
from return_semantics.schema_vocabulary import (
    SentimentCode as SentimentCode,
)
from return_semantics.schema_vocabulary import (
    StrictModel as StrictModel,
)
from return_semantics.schema_vocabulary import (
    SubjectCode as SubjectCode,
)
from return_semantics.schema_vocabulary import (
    _migrate_semantic_refs as _migrate_semantic_refs,
)
from return_semantics.schema_vocabulary import (
    _validated_variant_ref as _validated_variant_ref,
)
from return_semantics.taxonomy_schemas import (
    CategoryDefinition as CategoryDefinition,
)
from return_semantics.taxonomy_schemas import (
    ClaimEvidenceRequirement as ClaimEvidenceRequirement,
)
from return_semantics.taxonomy_schemas import (
    DimensionContract as DimensionContract,
)
from return_semantics.taxonomy_schemas import (
    EvidenceRequirement as EvidenceRequirement,
)
from return_semantics.taxonomy_schemas import (
    ImplicitEvidenceRule as ImplicitEvidenceRule,
)
from return_semantics.taxonomy_schemas import (
    LabelDefinition as LabelDefinition,
)
from return_semantics.taxonomy_schemas import (
    LabelExample as LabelExample,
)
from return_semantics.taxonomy_schemas import (
    TaxonomyConfig as TaxonomyConfig,
)
from return_semantics.taxonomy_schemas import (
    TaxonomyValidationRules as TaxonomyValidationRules,
)


class SemanticUnit(StrictModel):
    subject: SubjectCode
    label_code: str = Field(min_length=1)
    opinion: str = Field(min_length=1)
    sentiment: SentimentCode
    assertion: AssertionCode
    part: str = Field(min_length=1)
    evidence: str = Field(min_length=1)
    implicit: bool
    claim_relation: ClaimRelation = ClaimRelation.NONE
    claim_id: str | None = None
    fact_id: str | None = None
    fact_ids: list[str] = Field(default_factory=list)
    actor_ref: str = "REVIEWER"
    source_ref: str = "REVIEWER"
    experiencer_ref: str = "REVIEWER"
    product_ref: str = "CURRENT"
    variant_ref: str = "UNSPECIFIED"
    event_ref: str = "UNSPECIFIED"
    reference_basis: ReferenceBasis = ReferenceBasis.NONE
    statement_type: Literal[
        "EXPERIENCE",
        "EVALUATION",
        "RECOMMENDATION",
        "INTENT",
        "PREDICTION",
        "HYPOTHESIS",
        "PRODUCT_CLAIM",
        "APPEARANCE_INFERENCE",
        "REPORTED",
        "NEGATED",
        "NOT_TESTED",
        "ADVICE",
    ] = "EVALUATION"
    operation: str = ""
    condition: str = ""
    evidence_source: EvidenceSource = EvidenceSource.COMMENT
    fact_role: FactRole = FactRole.CONCLUSION
    causal_attribution: CausalAttributionCode = CausalAttributionCode.UNKNOWN
    causal_attribution_reason: str = ""
    decision_reason: str = ""
    context_fact_ids: list[str] = Field(default_factory=list)

    _migrate_refs = model_validator(mode="before")(_migrate_semantic_refs)
    _validate_variant = field_validator("variant_ref")(_validated_variant_ref)


class UnknownSemantic(StrictModel):
    opinion: str = Field(min_length=1)
    evidence: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    disposition: SemanticDisposition = SemanticDisposition.TAXONOMY_GAP
    fact_id: str | None = None
    actor_ref: str = "REVIEWER"
    source_ref: str = "REVIEWER"
    experiencer_ref: str = "REVIEWER"
    product_ref: str = "CURRENT"
    variant_ref: str = "UNSPECIFIED"
    event_ref: str = "UNSPECIFIED"
    reference_basis: ReferenceBasis = ReferenceBasis.NONE
    statement_type: str = ""
    operation: str = ""
    condition: str = ""
    evidence_source: EvidenceSource = EvidenceSource.COMMENT
    fact_role: FactRole = FactRole.CONCLUSION
    causal_attribution: CausalAttributionCode = CausalAttributionCode.UNKNOWN
    causal_attribution_reason: str = ""

    _migrate_refs = model_validator(mode="before")(_migrate_semantic_refs)
    _validate_variant = field_validator("variant_ref")(_validated_variant_ref)


class DimensionScope(StrictModel):
    source_ref: str = "REVIEWER"
    experiencer_ref: str = "REVIEWER"
    product_ref: str = "CURRENT"
    variant_ref: str = "UNSPECIFIED"
    event_ref: str = "UNSPECIFIED"
    reference_basis: ReferenceBasis = ReferenceBasis.NONE
    part: str = "UNSPECIFIED"
    operation: str = ""
    condition: str = ""

    _validate_variant = field_validator("variant_ref")(_validated_variant_ref)


class DimensionDecision(StrictModel):
    parent_code: str = Field(min_length=1)
    scope: DimensionScope
    verdict_label_code: str = Field(min_length=1)
    supporting_fact_ids: list[str] = Field(min_length=1)
    context_fact_ids: list[str] = Field(default_factory=list)
    reason: str = Field(min_length=1)


class SemanticRelation(StrictModel):
    relation_type: SemanticRelationType
    fact_ids: list[str] = Field(min_length=2)
    label_codes: list[str] = Field(min_length=1)
    reason: str = Field(min_length=1)


class CommentSummary(StrictModel):
    status: CommentSummaryStatus = CommentSummaryStatus.NO_CONFIRMED
    fact_ids: list[str] = Field(default_factory=list)
    positive_label_codes: list[str] = Field(default_factory=list)
    negative_label_codes: list[str] = Field(default_factory=list)


class ReviewDiagnostic(StrictModel):
    """记录系统复核异常的可追溯证据和处理动作。"""

    code: str = Field(min_length=1)
    evidence_text: str = ""
    primary_result: str = ""
    secondary_result: str = ""
    detail: str = ""
    action: str = Field(default="SYSTEM_RERUN", min_length=1)


class ClassificationTrace(StrictModel):
    extracted_facts: list[ExtractedFact] = Field(default_factory=list)
    fact_mappings: list[FactMapping] = Field(default_factory=list)
    dimension_decisions: list[DimensionDecision] = Field(default_factory=list)
    semantic_relations: list[SemanticRelation] = Field(default_factory=list)
    comment_summary: CommentSummary = Field(default_factory=CommentSummary)


class ModelClassification(ClassificationTrace):
    semantic_units: list[SemanticUnit] = Field(default_factory=list)
    unknown_semantics: list[UnknownSemantic] = Field(default_factory=list)
    primary_label_codes: list[str] = Field(default_factory=list)
    needs_review: bool = False
    review_reasons: list[str] = Field(default_factory=list)
    review_diagnostics: list[ReviewDiagnostic] = Field(default_factory=list)


class ClaimDefinition(StrictModel):
    claim_id: str
    text: str
    source: str
    allowed_label_codes: list[str]


class ListingClaimsConfig(StrictModel):
    version: str
    claims: list[ClaimDefinition]


class ValidatedClassification(ClassificationTrace):
    classification_key: str
    semantic_units: list[SemanticUnit]
    unknown_semantics: list[UnknownSemantic]
    problem_label_codes: list[str]
    positive_label_codes: list[str]
    primary_label_codes: list[str]
    status: ProcessingStatus
    review_reasons: list[str]
    review_diagnostics: list[ReviewDiagnostic] = Field(default_factory=list)
    model_name: str
    prompt_version: str
    taxonomy_version: str
