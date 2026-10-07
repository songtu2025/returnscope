from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from return_semantics.analysis_context import AnalysisContext
from return_semantics.schemas import (
    ClaimDefinition,
    CommentSummary,
    LabelDefinition,
    ListingClaimsConfig,
    ModelClassification,
    ReviewDiagnostic,
    SemanticRelation,
    SemanticUnit,
    TaxonomyConfig,
    UnknownSemantic,
)


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))


@dataclass
class _ValidationState:
    hard_reasons: list[str] = field(default_factory=list)
    soft_reasons: list[str] = field(default_factory=list)
    unknown_semantics: list[UnknownSemantic] = field(default_factory=list)
    guardrail_removed_codes: set[str] = field(default_factory=set)
    valid_units: list[SemanticUnit] = field(default_factory=list)
    problem_codes: list[str] = field(default_factory=list)
    positive_codes: list[str] = field(default_factory=list)
    primary_codes: list[str] = field(default_factory=list)
    semantic_relations: list[SemanticRelation] = field(default_factory=list)
    comment_summary: CommentSummary = field(default_factory=CommentSummary)
    review_diagnostics: list[ReviewDiagnostic] = field(default_factory=list)


@dataclass(frozen=True)
class _ValidationContext:
    comment: str
    taxonomy: TaxonomyConfig
    labels: dict[str, LabelDefinition]
    allowed_parts: set[str]
    claim_map: dict[str, ClaimDefinition]


@dataclass(frozen=True)
class _ValidationRequest:
    classification_key: str
    comment: str
    reason: str
    model_result: ModelClassification
    taxonomy: TaxonomyConfig
    claims: ListingClaimsConfig
    model_name: str
    prompt_version: str
    analysis_context: AnalysisContext
