from typing import Literal

from pydantic import BaseModel, Field

DashboardFilterValue = str | list[str] | None


class DashboardPlanRequest(BaseModel):
    result_version_ids: list[str] = Field(min_length=1, max_length=200)
    filters: dict[str, DashboardFilterValue] = Field(default_factory=dict)


class DashboardCreateRequest(DashboardPlanRequest):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    plan_hash: str = Field(min_length=64, max_length=64)
    reason: str = Field(min_length=1, max_length=500)


class DashboardVersionCreateRequest(DashboardPlanRequest):
    expected_revision: int = Field(ge=1)
    plan_hash: str = Field(min_length=64, max_length=64)
    reason: str = Field(min_length=1, max_length=500)


class InsightReportGenerateRequest(BaseModel):
    model_id: str = Field(min_length=1, max_length=120)
    reasoning_effort: str = Field(min_length=1, max_length=20)


class InsightReportIssueDecisionRequest(BaseModel):
    status: Literal["pending", "ignored", "watching", "verify"]


class InsightReportFromResultsRequest(DashboardPlanRequest):
    plan_hash: str = Field(min_length=64, max_length=64)
    model_id: str = Field(min_length=1, max_length=120)
    reasoning_effort: str = Field(min_length=1, max_length=20)
