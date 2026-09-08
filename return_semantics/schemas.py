from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


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


class ClaimRelation(StrEnum):
    CONTRADICTS = "CONTRADICTS"
    SUPPORTS = "SUPPORTS"
    RELATED_UNCERTAIN = "RELATED_UNCERTAIN"
    NONE = "NONE"


class ProcessingStatus(StrEnum):
    AUTO_APPROVED = "AUTO_APPROVED"
    MANUAL_RESOLVED = "MANUAL_RESOLVED"
    SECONDARY_REVIEW = "SECONDARY_REVIEW"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    NO_TEXT_EVIDENCE = "NO_TEXT_EVIDENCE"
    UNKNOWN_SEMANTIC = "UNKNOWN_SEMANTIC"
    MODEL_ERROR = "MODEL_ERROR"


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


class UnknownSemantic(StrictModel):
    opinion: str = Field(min_length=1)
    evidence: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class ModelClassification(StrictModel):
    semantic_units: list[SemanticUnit] = Field(default_factory=list)
    unknown_semantics: list[UnknownSemantic] = Field(default_factory=list)
    primary_label_codes: list[str] = Field(default_factory=list)
    needs_review: bool = False
    review_reasons: list[str] = Field(default_factory=list)


class LabelExample(StrictModel):
    text: str = Field(min_length=1, max_length=1000)
    applies: bool
    sentiment: SentimentCode | None = None
    explanation: str = Field(min_length=1, max_length=500)


class LabelDefinition(StrictModel):
    code: str
    name: str
    group: str
    description: str
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


class TaxonomyValidationRules(StrictModel):
    allowed_groups: list[str] = Field(default_factory=list)
    neutral_reason_labels: list[str] | None = None
    required_review_labels: list[str] = Field(default_factory=list)
    conflict_scope: Literal["comment", "evidence"] = "comment"
    opposite_reason_labels: dict[str, list[str]] = Field(default_factory=dict)
    conflicting_label_sets: list[list[str]] = Field(default_factory=list)
    evidence_requirements: list[EvidenceRequirement] = Field(default_factory=list)
    implicit_evidence_rules: list[ImplicitEvidenceRule] = Field(default_factory=list)
    claim_evidence_requirements: list[ClaimEvidenceRequirement] = Field(
        default_factory=list
    )


class TaxonomyConfig(StrictModel):
    version: str
    recognition_profile: Literal["legacy_v3", "keyword_free_v1", "semantic_v1"] = (
        "legacy_v3"
    )
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
        label_codes = {label.code for label in self.labels}
        groups = self.validation_rules.allowed_groups
        if groups and any(label.group not in groups for label in self.labels):
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
        unknown_codes = sorted(rule_codes.difference(label_codes))
        if unknown_codes:
            raise ValueError(f"校验规则引用了未知标签: {unknown_codes}")
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


class ValidatedClassification(StrictModel):
    classification_key: str
    semantic_units: list[SemanticUnit]
    unknown_semantics: list[UnknownSemantic]
    problem_label_codes: list[str]
    positive_label_codes: list[str]
    primary_label_codes: list[str]
    status: ProcessingStatus
    review_reasons: list[str]
    model_name: str
    prompt_version: str
    taxonomy_version: str
