from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, cast

AnalysisContext = Literal["returns", "review", "user_feedback"]

RETURNS_CONTEXT: AnalysisContext = "returns"
REVIEW_CONTEXT: AnalysisContext = "review"
USER_FEEDBACK_CONTEXT: AnalysisContext = "user_feedback"
VALID_ANALYSIS_CONTEXTS = frozenset(
    {RETURNS_CONTEXT, REVIEW_CONTEXT, USER_FEEDBACK_CONTEXT}
)


def validate_analysis_context(value: str) -> AnalysisContext:
    if value not in VALID_ANALYSIS_CONTEXTS:
        raise ValueError("不支持的分析场景")
    return cast(AnalysisContext, value)


def analysis_context_from_snapshot(snapshot: Mapping[str, object]) -> AnalysisContext:
    return validate_analysis_context(
        str(snapshot.get("analysis_context") or RETURNS_CONTEXT)
    )
