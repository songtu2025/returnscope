from __future__ import annotations

from typing import Literal

from pydantic import Field

from return_semantics.schemas import (
    DimensionDecision,
    FactMapping,
    FactRelationType,
    SemanticDisposition,
    StrictModel,
)


class FactMappings(StrictModel):
    mappings: list[FactMapping]


class ModelFactMapping(StrictModel):
    """模型只可填写语义映射字段，程序审计字段由编译阶段维护。"""

    fact_id: str = Field(min_length=1)
    label_codes: list[str] = Field(default_factory=list, max_length=1)
    reason: str = ""
    disposition: SemanticDisposition | None = None
    relation_type: FactRelationType = FactRelationType.NONE
    related_fact_ids: list[str] = Field(default_factory=list)
    evidence_relation: Literal["DIRECT", "EQUIVALENT", "INFERRED"] = "DIRECT"
    fallback_is_independent: bool = False


class ModelFactMappings(StrictModel):
    mappings: list[ModelFactMapping]


class EvidenceLabelAdjudication(StrictModel):
    fact_id: str
    action: Literal["ACCEPT", "REPLACE", "ABSTAIN", "REVIEW"]
    label_code: str | None = None
    reason: str


class EvidenceLabelAdjudications(StrictModel):
    adjudications: list[EvidenceLabelAdjudication]


class FactDecisions(StrictModel):
    decisions: list[DimensionDecision]
