from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _validated_variant_ref(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("规格引用不能为空")
    if normalized.upper().startswith("UNSPEC") and normalized != "UNSPECIFIED":
        raise ValueError("未明确规格必须精确使用UNSPECIFIED")
    return normalized


class SubjectCode(StrEnum):
    PRODUCT = "PRODUCT"
    CUSTOMER = "CUSTOMER"
    DELIVERY = "DELIVERY"
    ORDER = "ORDER"
    SERVICE = "SERVICE"
    UNKNOWN = "UNKNOWN"


class SentimentCode(StrEnum):
    NEGATIVE = "NEGATIVE"
    POSITIVE = "POSITIVE"
    NEUTRAL = "NEUTRAL"


class AssertionCode(StrEnum):
    AFFIRMED = "AFFIRMED"
    NEGATED = "NEGATED"
    UNCERTAIN = "UNCERTAIN"


class FactSpecificity(StrEnum):
    SPECIFIC = "SPECIFIC"
    GENERAL_EVALUATION = "GENERAL_EVALUATION"


class ExperiencerResolution(StrEnum):
    EXPLICIT = "EXPLICIT"
    INHERITED = "INHERITED"
    AMBIGUOUS = "AMBIGUOUS"


class FactExtractionSource(StrEnum):
    PRIMARY = "PRIMARY"
    COVERAGE = "COVERAGE"


class ClaimRelation(StrEnum):
    CONTRADICTS = "CONTRADICTS"
    SUPPORTS = "SUPPORTS"
    RELATED_UNCERTAIN = "RELATED_UNCERTAIN"
    NONE = "NONE"


class EvidenceSource(StrEnum):
    COMMENT = "COMMENT"
    TITLE = "TITLE"
    BODY = "BODY"
    TITLE_AND_BODY = "TITLE_AND_BODY"


class ReferenceBasis(StrEnum):
    NONE = "NONE"
    PERSONAL_PREFERENCE = "PERSONAL_PREFERENCE"
    SIZE_CHART = "SIZE_CHART"
    LISTING = "LISTING"
    MARKET_NORM = "MARKET_NORM"
    BARE_USE = "BARE_USE"
    OTHER_PRODUCT = "OTHER_PRODUCT"
    OTHER_PERSON = "OTHER_PERSON"


class FactRole(StrEnum):
    CONCLUSION = "CONCLUSION"
    EVIDENCE = "EVIDENCE"
    CONTEXT = "CONTEXT"


class CausalAttributionCode(StrEnum):
    UNKNOWN = "UNKNOWN"
    PRODUCT_INTRINSIC = "PRODUCT_INTRINSIC"
    NORMAL_USE = "NORMAL_USE"
    CUSTOMER_ACTION = "CUSTOMER_ACTION"
    DELIVERY = "DELIVERY"
    ORDER = "ORDER"
    SERVICE = "SERVICE"
    EXTERNAL_CONDITION = "EXTERNAL_CONDITION"


class FactRelationType(StrEnum):
    NONE = "NONE"
    COVERED_BY = "COVERED_BY"
    SUPPORTS = "SUPPORTS"
    QUALIFIES = "QUALIFIES"
    CAUSED_BY = "CAUSED_BY"


class SemanticDisposition(StrEnum):
    EXPECTED_ABSTENTION = "EXPECTED_ABSTENTION"
    EVIDENCE_ONLY = "EVIDENCE_ONLY"
    TAXONOMY_GAP = "TAXONOMY_GAP"
    MAPPING_UNCERTAIN = "MAPPING_UNCERTAIN"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


class CommentSummaryStatus(StrEnum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    MIXED = "MIXED"
    CONFLICT = "CONFLICT"
    NO_CONFIRMED = "NO_CONFIRMED"


class SemanticRelationType(StrEnum):
    CONFLICT = "CONFLICT"
    MIXED = "MIXED"
    MULTI_ACTOR = "MULTI_ACTOR"
    MULTI_PRODUCT = "MULTI_PRODUCT"


class ProcessingStatus(StrEnum):
    AUTO_APPROVED = "AUTO_APPROVED"
    MANUAL_RESOLVED = "MANUAL_RESOLVED"
    SECONDARY_REVIEW = "SECONDARY_REVIEW"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    NO_TEXT_EVIDENCE = "NO_TEXT_EVIDENCE"
    UNKNOWN_SEMANTIC = "UNKNOWN_SEMANTIC"
    MODEL_ERROR = "MODEL_ERROR"


def _migrate_semantic_refs(value: object) -> object:
    if not isinstance(value, dict):
        return value
    migrated = dict(value)
    actor_ref = str(
        migrated.get("actor_ref") or migrated.get("experiencer_ref") or "REVIEWER"
    )
    migrated.setdefault("actor_ref", actor_ref)
    migrated.setdefault("source_ref", actor_ref)
    migrated.setdefault("experiencer_ref", actor_ref)
    return migrated


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


class EvidenceSpan(StrictModel):
    text: str = Field(min_length=1)
    source: EvidenceSource = EvidenceSource.COMMENT


class ExtractedFact(StrictModel):
    fact_id: str = Field(min_length=1)
    extraction_source: FactExtractionSource = FactExtractionSource.PRIMARY
    actor_ref: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    experiencer_ref: str = Field(min_length=1)
    product_ref: str = Field(min_length=1)
    variant_ref: str = Field(default="UNSPECIFIED", min_length=1)
    event_ref: str = Field(min_length=1)
    reference_basis: ReferenceBasis = ReferenceBasis.NONE
    fact_role: FactRole = FactRole.CONCLUSION
    subject: SubjectCode = SubjectCode.PRODUCT
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
    ]
    assertion: AssertionCode = AssertionCode.AFFIRMED
    specificity: FactSpecificity = FactSpecificity.SPECIFIC
    experiencer_resolution: ExperiencerResolution = ExperiencerResolution.EXPLICIT
    opinion: str = Field(min_length=1)
    sentiment: SentimentCode
    part: str = Field(min_length=1)
    operation: str = ""
    condition: str = ""
    causal_attribution: CausalAttributionCode = CausalAttributionCode.UNKNOWN
    causal_attribution_reason: str = ""
    is_primary_reason: bool = False
    candidate_branch_codes: list[str] = Field(default_factory=list)
    evidence_spans: list[EvidenceSpan] = Field(min_length=1)

    _migrate_refs = model_validator(mode="before")(_migrate_semantic_refs)
    _validate_variant = field_validator("variant_ref")(_validated_variant_ref)

    @model_validator(mode="after")
    def validate_causal_attribution(self) -> "ExtractedFact":
        has_attribution = self.causal_attribution != CausalAttributionCode.UNKNOWN
        if has_attribution != bool(self.causal_attribution_reason.strip()):
            raise ValueError("因果归属与因果说明必须同时填写或同时留空")
        return self


class FactExtraction(StrictModel):
    facts: list[ExtractedFact]


class FactMapping(StrictModel):
    fact_id: str = Field(min_length=1)
    label_codes: list[str] = Field(default_factory=list, max_length=1)
    candidate_label_codes: list[str] = Field(default_factory=list, max_length=1)
    reason: str = ""
    disposition: SemanticDisposition | None = None
    relation_type: FactRelationType = FactRelationType.NONE
    related_fact_ids: list[str] = Field(default_factory=list)
    evidence_relation: Literal["DIRECT", "EQUIVALENT", "INFERRED"] = "DIRECT"
    fallback_is_independent: bool = False
    adjudication_action: Literal["ACCEPT", "REPLACE", "ABSTAIN", "REVIEW"] | None = None

    @model_validator(mode="before")
    @classmethod
    def migrate_candidate_labels(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        migrated = dict(value)
        if migrated.get("label_codes") and migrated.get("disposition") is not None:
            migrated.setdefault("candidate_label_codes", migrated["label_codes"])
            migrated["label_codes"] = []
        return migrated

    @model_validator(mode="after")
    def validate_disposition(self) -> "FactMapping":
        if self.label_codes and self.disposition is not None:
            raise ValueError("已有标签映射的事实不能同时指定未映射处置")
        if self.label_codes and self.candidate_label_codes:
            raise ValueError("终态标签与候选审计标签不能同时存在")
        if self.candidate_label_codes and self.disposition is None:
            raise ValueError("候选审计标签只能用于未形成终态的事实")
        if self.relation_type == FactRelationType.NONE and self.related_fact_ids:
            raise ValueError("无事实关系时不能引用关联事实")
        if self.relation_type != FactRelationType.NONE and not self.related_fact_ids:
            raise ValueError("事实关系必须引用至少一个关联事实")
        if self.fact_id in self.related_fact_ids:
            raise ValueError("事实关系不能引用自身")
        if len(self.related_fact_ids) != len(set(self.related_fact_ids)):
            raise ValueError("事实关系不能重复引用同一事实")
        return self


DimensionScopeField = Literal[
    "source_ref",
    "experiencer_ref",
    "product_ref",
    "variant_ref",
    "event_ref",
    "reference_basis",
    "part",
    "operation",
    "condition",
]


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


class LabelExample(StrictModel):
    text: str = Field(min_length=1, max_length=1000)
    applies: bool
    sentiment: SentimentCode | None = None
    explanation: str = Field(min_length=1, max_length=500)


class LabelDefinition(StrictModel):
    code: str
    name: str
    group: str = ""
    parent_code: str | None = None
    description: str = ""
    keywords: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list, max_length=10)
    examples: list[LabelExample] = Field(default_factory=list, max_length=10)
    allowed_sentiments: list[SentimentCode]
    allowed_claim_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_examples(self) -> "LabelDefinition":
        for example in self.examples:
            if example.applies and example.sentiment not in self.allowed_sentiments:
                raise ValueError("适用示例必须选择该标签允许的评价方向")
            if not example.applies and example.sentiment is not None:
                raise ValueError("不适用示例不指定评价方向")
        return self


class EvidenceRequirement(StrictModel):
    semantic_requirement: str = ""
    label_code: str = Field(min_length=1)
    cues: list[str] = Field(min_length=1)
    unknown_opinion: str = Field(min_length=1)
    unknown_reason: str = Field(min_length=1)


class ImplicitEvidenceRule(StrictModel):
    semantic_requirement: str = ""
    label_code: str = Field(min_length=1)
    cues: list[str] = Field(min_length=1)


class ClaimEvidenceRequirement(StrictModel):
    semantic_requirement: str = ""
    label_code: str = Field(min_length=1)
    claim_id: str = Field(min_length=1)
    cues: list[str] = Field(min_length=1)


class DimensionContract(StrictModel):
    parent_code: str = Field(min_length=1)
    verdict_label_codes: list[str] = Field(min_length=1)
    scope_fields: list[DimensionScopeField] = Field(min_length=1)


class TaxonomyValidationRules(StrictModel):
    allowed_groups: list[str] = Field(default_factory=list)
    neutral_reason_labels: list[str] | None = None
    required_review_labels: list[str] = Field(default_factory=list)
    boundary_required_labels: list[str] = Field(default_factory=list)
    fallback_label_codes: list[str] = Field(default_factory=list)
    conflict_scope: Literal["comment", "evidence"] = "comment"
    opposite_reason_labels: dict[str, list[str]] = Field(default_factory=dict)
    conflicting_label_sets: list[list[str]] = Field(default_factory=list)
    evidence_requirements: list[EvidenceRequirement] = Field(default_factory=list)
    implicit_evidence_rules: list[ImplicitEvidenceRule] = Field(default_factory=list)
    claim_evidence_requirements: list[ClaimEvidenceRequirement] = Field(
        default_factory=list
    )
    dimension_contracts: list[DimensionContract] = Field(default_factory=list)


class CategoryDefinition(StrictModel):
    code: str = Field(min_length=1)
    name: str = Field(min_length=1)
    parent_code: str | None = None


class TaxonomyConfig(StrictModel):
    version: str
    structure_version: Literal[1, 2] = 1
    categories: list[CategoryDefinition] = Field(default_factory=list)
    recognition_profile: Literal[
        "legacy_v3", "keyword_free_v1", "semantic_v1", "fact_v2"
    ] = "legacy_v3"
    agent_family: str
    product_context: str
    allowed_parts: list[str] = Field(default_factory=lambda: ["UNSPECIFIED"])
    instructions: list[str] = Field(default_factory=list)
    validation_rules: TaxonomyValidationRules = Field(
        default_factory=TaxonomyValidationRules
    )
    labels: list[LabelDefinition]

    @model_validator(mode="after")
    def validate_rule_labels(self) -> "TaxonomyConfig":
        if self.structure_version == 2:
            from return_semantics.taxonomy_hierarchy import (
                label_path_codes,
                validate_hierarchy,
            )

            validate_hierarchy(self)
        elif self.categories or any(label.parent_code for label in self.labels):
            raise ValueError("层级标签必须使用 structure_version=2")
        label_codes = {label.code for label in self.labels}
        groups = self.validation_rules.allowed_groups
        if (
            self.structure_version == 1
            and groups
            and any(label.group not in groups for label in self.labels)
        ):
            raise ValueError("标签分组必须来自标准规定的业务分组")
        rule_codes = {
            code
            for codes in self.validation_rules.opposite_reason_labels.values()
            for code in codes
        }
        rule_codes.update(
            code
            for codes in self.validation_rules.conflicting_label_sets
            for code in codes
        )
        rule_codes.update(
            rule.label_code for rule in self.validation_rules.evidence_requirements
        )
        rule_codes.update(
            rule.label_code for rule in self.validation_rules.implicit_evidence_rules
        )
        rule_codes.update(
            rule.label_code
            for rule in self.validation_rules.claim_evidence_requirements
        )
        rule_codes.update(self.validation_rules.neutral_reason_labels or [])
        rule_codes.update(self.validation_rules.required_review_labels)
        rule_codes.update(self.validation_rules.boundary_required_labels)
        rule_codes.update(self.validation_rules.fallback_label_codes)
        unknown_codes = sorted(rule_codes.difference(label_codes))
        if unknown_codes:
            raise ValueError(f"校验规则引用了未知标签: {unknown_codes}")
        contracts = self.validation_rules.dimension_contracts
        decision_parent_codes = [contract.parent_code for contract in contracts]
        category_codes = {category.code for category in self.categories}
        if decision_parent_codes and self.structure_version != 2:
            raise ValueError("维度裁决契约仅适用于层级标签")
        unknown_parent_codes = sorted(set(decision_parent_codes) - category_codes)
        if unknown_parent_codes:
            raise ValueError(f"维度裁决契约引用了未知分类: {unknown_parent_codes}")
        if len(decision_parent_codes) != len(set(decision_parent_codes)):
            raise ValueError("同一分类只能配置一条维度裁决契约")
        for contract in contracts:
            if len(contract.verdict_label_codes) != len(
                set(contract.verdict_label_codes)
            ):
                raise ValueError("维度裁决契约的结论标签不能重复")
            if len(contract.scope_fields) != len(set(contract.scope_fields)):
                raise ValueError("维度裁决契约的作用域字段不能重复")
            invalid_verdicts = [
                code for code in contract.verdict_label_codes if code not in label_codes
            ]
            if invalid_verdicts:
                raise ValueError(f"维度裁决契约引用了未知标签: {invalid_verdicts}")
            outside_parent = [
                code
                for code in contract.verdict_label_codes
                if contract.parent_code not in label_path_codes(self, code)[:-1]
            ]
            if outside_parent:
                raise ValueError(f"维度结论标签不属于配置父级: {outside_parent}")
        for label in self.labels:
            matching_contracts = [
                contract.parent_code
                for contract in contracts
                if contract.parent_code in label_path_codes(self, label.code)[:-1]
            ]
            if len(matching_contracts) > 1:
                raise ValueError(f"维度裁决契约不能重叠管理同一标签: {label.code}")
        if any(
            len(set(codes)) < 2
            for codes in self.validation_rules.conflicting_label_sets
        ):
            raise ValueError("冲突标签组至少需要两个不同标签")
        return self


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
