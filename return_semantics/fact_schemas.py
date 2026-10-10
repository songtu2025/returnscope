from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from return_semantics.schema_vocabulary import (
    AssertionCode,
    CausalAttributionCode,
    EvidenceSource,
    ExperiencerResolution,
    FactExtractionSource,
    FactRelationType,
    FactRole,
    FactSpecificity,
    ReferenceBasis,
    SemanticDisposition,
    SentimentCode,
    StrictModel,
    SubjectCode,
    _migrate_semantic_refs,
    _validated_variant_ref,
)


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


# 保留原模块标识，兼容既有模型序列化和导入入口。
for _schema_type in (
    EvidenceSpan,
    ExtractedFact,
    FactExtraction,
    FactMapping,
):
    _schema_type.__module__ = "return_semantics.schemas"
del _schema_type
