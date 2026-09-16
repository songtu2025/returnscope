from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

V5_PROMPT_VERSION = "ai-return-insight-v5"
PROMPT_VERSION = "ai-return-insight-v6"


class ReportSummaryItem(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    statement: str = Field(min_length=1, max_length=500)
    tone: Literal["primary", "neutral", "warning"] = "neutral"
    evidence_ids: list[str] = Field(min_length=1)


class ReportFinding(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    kind: Literal["structure", "diagnostic", "information"]
    title: str = Field(min_length=1, max_length=120)
    conclusion: str = Field(min_length=1, max_length=500)
    interpretation: str = Field(min_length=1, max_length=800)
    implication: str = Field(min_length=1, max_length=500)
    evidence_ids: list[str] = Field(min_length=1)


class ReportAction(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    priority: Literal["P0", "P1", "P2"]
    target: str = Field(min_length=1, max_length=160)
    action: str = Field(min_length=1, max_length=300)
    rationale: str = Field(min_length=1, max_length=500)
    success_signal: str = Field(min_length=1, max_length=300)
    evidence_ids: list[str] = Field(min_length=1)


class InsightReportContent(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    executive_summary: list[ReportSummaryItem] = Field(min_length=2, max_length=4)
    findings: list[ReportFinding] = Field(min_length=2, max_length=6)
    actions: list[ReportAction] = Field(min_length=2, max_length=6)
    further_questions: list[str] = Field(default_factory=list, max_length=5)
    caveats: list[str] = Field(min_length=1)


class ReportIssueScope(BaseModel):
    category: str | None = Field(default=None, max_length=120)
    listing: str | None = Field(default=None, max_length=200)
    product: str | None = Field(default=None, max_length=300)
    sku: str | None = Field(default=None, max_length=200)


class ReportIssueMetrics(BaseModel):
    matched_return_samples: int = Field(ge=0)
    scoped_return_samples: int = Field(ge=0)
    return_sample_share: float = Field(ge=0, le=100)
    baseline_return_sample_share: float | None = Field(default=None, ge=0, le=100)
    gap_percentage_points: float | None = None
    lift: float | None = Field(default=None, ge=0)
    recent_change_percentage_points: float | None = None
    trend_direction: Literal["rising", "stable", "falling", "insufficient"]


class ReportIssueReadiness(BaseModel):
    status: Literal["unusable", "diagnostic_only", "verification_ready"]
    label: str = Field(min_length=1, max_length=40)
    reason: str = Field(min_length=1, max_length=500)


class ReportIssueRecommendation(BaseModel):
    label: Literal["建议验证"] = "建议验证"
    validation_question: str = Field(min_length=1, max_length=300)
    rationale: str = Field(min_length=1, max_length=500)
    suggested_evidence: list[str] = Field(min_length=1, max_length=5)


class ReportIssue(BaseModel):
    id: str = Field(min_length=1, max_length=160)
    rank: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=200)
    scope: ReportIssueScope
    metrics: ReportIssueMetrics
    known: list[str] = Field(min_length=1, max_length=6)
    evidence_explanation: str = Field(min_length=1, max_length=800)
    unknown: list[str] = Field(min_length=1, max_length=5)
    recommendation: ReportIssueRecommendation
    readiness: ReportIssueReadiness
    evidence_ids: list[str] = Field(min_length=1)


class InsightDecisionReportContent(BaseModel):
    report_type: Literal["problem_decision"] = "problem_decision"
    title: str = Field(min_length=1, max_length=120)
    issues: list[ReportIssue] = Field(min_length=1, max_length=8)
    caveats: list[str] = Field(min_length=1, max_length=8)


class ReportQualityIssue(BaseModel):
    code: Literal[
        "report_consistency",
        "text_quality",
        "product_mapping",
        "pending_review",
    ]
    label: str = Field(min_length=1, max_length=80)
    detail: str = Field(min_length=1, max_length=500)
    evidence_ids: list[str] = Field(default_factory=list)


class ReportDecisionReadiness(BaseModel):
    status: Literal["actionable", "diagnostic_only", "unusable"]
    label: str = Field(min_length=1, max_length=40)
    reason: str = Field(min_length=1, max_length=500)


class ReportQualityGate(BaseModel):
    status: Literal["passed", "warning", "blocked"]
    issues: list[ReportQualityIssue]
    text_quality: dict[str, Any]
    product_mapping: dict[str, Any]
    consistency: dict[str, Any]
    decision_readiness: ReportDecisionReadiness


class DecisionReportQualityGate(BaseModel):
    status: Literal["passed", "warning", "blocked"]
    issues: list[ReportQualityIssue]
    text_quality: dict[str, Any]
    product_mapping: dict[str, Any]
    consistency: dict[str, Any]
    decision_readiness: ReportIssueReadiness
