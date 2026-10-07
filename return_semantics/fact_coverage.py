from __future__ import annotations

from dataclasses import dataclass

from return_semantics.schemas import ExtractedFact, ReviewDiagnostic


@dataclass(frozen=True)
class CoverageFactRejection:
    raw_fact: object
    diagnostic: ReviewDiagnostic


@dataclass(frozen=True)
class CoverageMergeResult:
    facts: list[ExtractedFact]
    added: int
    rejected: int
    diagnostics: list[ReviewDiagnostic]
    rejections: tuple[CoverageFactRejection, ...] = ()
