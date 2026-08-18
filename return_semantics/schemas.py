from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SubjectCode(StrEnum):
    PRODUCT = "PRODUCT"
    CUSTOMER = "CUSTOMER"
    DELIVERY = "DELIVERY"
    ORDER = "ORDER"
    UNKNOWN = "UNKNOWN"


class SentimentCode(StrEnum):
    NEGATIVE = "NEGATIVE"
    POSITIVE = "POSITIVE"
    NEUTRAL = "NEUTRAL"


class AssertionCode(StrEnum):
    AFFIRMED = "AFFIRMED"
    NEGATED = "NEGATED"
    UNCERTAIN = "UNCERTAIN"


class PartCode(StrEnum):
    OUTSOLE = "OUTSOLE"
    TOE = "TOE"
    HEEL = "HEEL"
    INSOLE = "INSOLE"
    OPENING = "OPENING"
    UPPER = "UPPER"
    SOLE_UPPER_SEAM = "SOLE_UPPER_SEAM"
    HEEL_TAB = "HEEL_TAB"
    ARCH = "ARCH"
    WHOLE_SHOE = "WHOLE_SHOE"
    CROWN = "CROWN"
    BRIM = "BRIM"
    CHIN_STRAP = "CHIN_STRAP"
    SIZE_ADJUSTER = "SIZE_ADJUSTER"
    LINING = "LINING"
    FRAME = "FRAME"
    LENS = "LENS"
    NOSE_PAD = "NOSE_PAD"
    TEMPLE = "TEMPLE"
    HINGE = "HINGE"
    STRAP = "STRAP"
    CUFF = "CUFF"
    PALM = "PALM"
    FINGER = "FINGER"
    THUMB = "THUMB"
    CLOSURE = "CLOSURE"
    UNSPECIFIED = "UNSPECIFIED"


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
    part: PartCode
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


class LabelDefinition(StrictModel):
    code: str
    name: str
    group: str
    description: str
    allowed_sentiments: list[SentimentCode]
    allowed_claim_ids: list[str] = Field(default_factory=list)


class TaxonomyConfig(StrictModel):
    version: str
    agent_family: str = "鞋履智能体"
    product_context: str = "涉水鞋"
    allowed_parts: list[PartCode] = Field(
        default_factory=lambda: [
            PartCode.OUTSOLE,
            PartCode.TOE,
            PartCode.HEEL,
            PartCode.INSOLE,
            PartCode.OPENING,
            PartCode.UPPER,
            PartCode.SOLE_UPPER_SEAM,
            PartCode.HEEL_TAB,
            PartCode.ARCH,
            PartCode.WHOLE_SHOE,
            PartCode.UNSPECIFIED,
        ]
    )
    instructions: list[str] = Field(default_factory=list)
    labels: list[LabelDefinition]


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
