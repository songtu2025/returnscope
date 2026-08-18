from typing import Literal

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)


class UserCreateRequest(BaseModel):
    email: str
    display_name: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=10, max_length=200)


class UserStatusRequest(BaseModel):
    active: bool
    expected_active: bool
    note: str = Field(min_length=1, max_length=500)


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=200)


class ModelDefinitionRequest(BaseModel):
    model_key: str = Field(min_length=1, max_length=120)
    display_name: str = Field(default="", max_length=80)
    supported_efforts: list[str] = Field(
        default_factory=lambda: ["low", "medium", "high"],
        min_length=1,
        max_length=3,
    )
    active: bool = True


class ModelUpdateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    supported_efforts: list[str] = Field(min_length=1, max_length=3)
    active: bool


class ModelValidateRequest(BaseModel):
    effort: str | None = None


class ConfigVersionRequest(BaseModel):
    connection_id: str | None = None
    name: str = Field(min_length=1, max_length=80)
    provider: str = Field(default="responses-compatible", max_length=50)
    base_url: str = Field(min_length=1, max_length=500)
    api_key: str = Field(default="", max_length=2000)
    primary_model: str = Field(min_length=1, max_length=120)
    primary_effort: str = "medium"
    cheap_model: str | None = Field(default=None, max_length=120)
    cheap_effort: str = "medium"
    secondary_model: str | None = Field(default=None, max_length=120)
    secondary_effort: str = "high"
    cheap_audit_percent: int = Field(default=5, ge=0, le=100)
    requests_per_minute: int = Field(default=60, ge=1, le=10000)
    max_workers: int = Field(default=4, ge=1, le=16)
    timeout_seconds: int = Field(default=120, ge=5, le=600)
    change_note: str = Field(min_length=1, max_length=500)
    models: list[ModelDefinitionRequest] | None = Field(
        default=None,
        max_length=50,
    )


class ModelPolicyRequest(BaseModel):
    connection_id: str = Field(min_length=1, max_length=100)
    cheap_model: str | None = Field(default=None, max_length=120)
    cheap_effort: str = "low"
    primary_model: str = Field(min_length=1, max_length=120)
    primary_effort: str = "medium"
    secondary_model: str | None = Field(default=None, max_length=120)
    secondary_effort: str = "high"
    cheap_audit_percent: int = Field(default=5, ge=0, le=100)


class UserModelPreferenceRequest(ModelPolicyRequest):
    pass


class TaskCreateRequest(BaseModel):
    title: str = Field(default="", max_length=120)
    dataset_version_id: str = Field(min_length=1, max_length=100)
    product_version_id: str = Field(min_length=1, max_length=100)
    store: str | None = Field(default=None, max_length=100)
    listing: str | None = Field(default=None, max_length=100)
    config_version_id: str | None = None
    model_policy: ModelPolicyRequest | None = None
    plan_hash: str | None = Field(default=None, min_length=64, max_length=64)
    unresolved_policy: Literal["block_all", "run_ready"] | None = None
    segment_order: list[str] | None = Field(default=None, max_length=500)
    max_parallel_segments: int = Field(default=3, ge=1, le=3)


class TaskPreflightRequest(BaseModel):
    dataset_version_id: str = Field(min_length=1, max_length=100)
    product_version_id: str = Field(min_length=1, max_length=100)
    store: str | None = Field(default=None, max_length=100)
    listing: str | None = Field(default=None, max_length=100)
    config_version_id: str | None = None
    model_policy: ModelPolicyRequest | None = None


class TaskReplanPreflightRequest(BaseModel):
    product_version_id: str = Field(min_length=1, max_length=100)


class TaskReplanRequest(BaseModel):
    product_version_id: str = Field(min_length=1, max_length=100)
    expected_revision: int = Field(ge=1)
    plan_hash: str = Field(min_length=64, max_length=64)
    unresolved_policy: Literal["block_all", "run_ready"]
    reason: str = Field(min_length=1, max_length=500)


class TaskSegmentRetryRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=500)


class TaskSegmentActionRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    note: str = Field(default="", max_length=500)


class TaskParallelismRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    max_parallel_segments: int = Field(ge=1, le=3)


class TaskSegmentOrderRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    segment_keys: list[str] = Field(min_length=1, max_length=500)


class TaskRenameRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=120)
    note: str = Field(min_length=1, max_length=500)


class TaskActionRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    note: str = Field(min_length=1, max_length=500)


class ReviewResolveRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    label_code: str | None = Field(default=None, max_length=100)
    note: str = Field(min_length=1, max_length=500)


class ReviewBatchCreateRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class ReviewBatchRecordUpdateRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    action: Literal["confirm", "modify", "exclude"] = "confirm"
    label_code: str | None = Field(default=None, max_length=100)
    reason: str = Field(min_length=1, max_length=500)


class ReviewBatchRecordRevision(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    expected_revision: int = Field(ge=1)


class ReviewBatchRecordBulkUpdateRequest(BaseModel):
    records: list[ReviewBatchRecordRevision] = Field(min_length=1, max_length=100)
    action: Literal["confirm", "modify", "exclude"]
    label_code: str | None = Field(default=None, max_length=100)
    reason: str = Field(min_length=1, max_length=500)


class ReviewBatchPublishRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=500)


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


class InsightReportFromResultsRequest(DashboardPlanRequest):
    plan_hash: str = Field(min_length=64, max_length=64)
    model_id: str = Field(min_length=1, max_length=120)
    reasoning_effort: str = Field(min_length=1, max_length=20)


class DimensionRowUpdateRequest(BaseModel):
    row_index: int = Field(ge=0)
    expected_version: int = Field(ge=1)
    changes: dict[str, str]
    change_note: str = Field(min_length=1, max_length=500)


class CategoryCompletionItem(BaseModel):
    store: str = Field(default="", max_length=100)
    msku: str = Field(min_length=1, max_length=200)
    listing: str = Field(min_length=1, max_length=100)
    category_a: str = Field(min_length=1, max_length=100)
    category_b: str = Field(min_length=1, max_length=100)
    product_name: str = Field(default="", max_length=500)


class CategoryCompletionRequest(BaseModel):
    expected_version: int = Field(ge=1)
    store: str = Field(default="", max_length=100)
    items: list[CategoryCompletionItem] = Field(min_length=1, max_length=500)
    change_note: str = Field(min_length=1, max_length=500)
