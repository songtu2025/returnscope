from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict


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


# 保留原模块标识，兼容既有模型序列化和导入入口。
for _schema_type in (
    StrictModel,
    _validated_variant_ref,
    SubjectCode,
    SentimentCode,
    AssertionCode,
    FactSpecificity,
    ExperiencerResolution,
    FactExtractionSource,
    ClaimRelation,
    EvidenceSource,
    ReferenceBasis,
    FactRole,
    CausalAttributionCode,
    FactRelationType,
    SemanticDisposition,
    CommentSummaryStatus,
    SemanticRelationType,
    ProcessingStatus,
    _migrate_semantic_refs,
):
    _schema_type.__module__ = "return_semantics.schemas"
del _schema_type
