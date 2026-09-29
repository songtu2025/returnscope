from typing import Literal

from pydantic import BaseModel, Field

from web_backend.api_contracts.models import ModelPolicyRequest


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


class TaskArchiveRequest(BaseModel):
    task_ids: list[str] = Field(min_length=1, max_length=100)
    archived: bool
