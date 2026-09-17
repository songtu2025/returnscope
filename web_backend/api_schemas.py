from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from return_semantics.schemas import LabelExample


class ClassificationSemanticFactResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    fact_id: str | None = None
    label_code: str
    label_code_path: list[str] = Field(default_factory=list)
    label_path: list[str] = Field(default_factory=list)
    actor_ref: str | None = None
    product_ref: str | None = None
    event_ref: str | None = None
    statement_type: str | None = None
    condition: str | dict[str, Any] = ""
    evidence: str = ""
    evidence_source: str = "UNKNOWN"


class ClassificationUnknownSemanticResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    opinion: str = ""
    evidence: str = ""
    reason: str = ""
    disposition: str


class ClassificationTopicSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    topic_code: str
    topic_name: str
    topic_code_path: list[str] = Field(default_factory=list)
    topic_path: list[str] = Field(default_factory=list)
    status: Literal["POSITIVE", "NEGATIVE", "MIXED", "CONFLICT", "NO_CONFIRMED"]
    supporting_fact_ids: list[str] = Field(default_factory=list)
    label_codes: list[str] = Field(default_factory=list)
    fact_count: int = 0
    event_count: int = 0


class ClassificationResultRecordResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    processing_status: str
    semantic_disposition: str
    comment_summary_status: str
    quality_status: str
    fact_count: int
    event_count: int
    atomic_facts: list[ClassificationSemanticFactResponse] = Field(default_factory=list)
    comment_conclusions: list[ClassificationTopicSummaryResponse] = Field(
        default_factory=list
    )
    unknown_semantics: list[ClassificationUnknownSemanticResponse] = Field(
        default_factory=list
    )
    classification: dict[str, Any]


class ClassificationResultRecordsResponse(BaseModel):
    taxonomy: dict[str, Any] | None = None
    items: list[ClassificationResultRecordResponse]
    total: int
    page: int
    page_size: int


class ClassificationResultSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    version_id: str
    comment_count: int
    total_comment_count: int
    metrics: dict[str, int | str]
    comment_statuses: list[dict[str, int | str]] = Field(default_factory=list)
    semantic_dispositions: list[dict[str, int | str]] = Field(default_factory=list)
    topic_summaries: list[dict[str, Any]] = Field(default_factory=list)


class MySQLReturnImportRequest(BaseModel):
    mapping: dict[str, str] = Field(max_length=10)
    default_store: str = Field(default="", max_length=100)
    date_from: date | None = None
    date_to: date | None = None
    store: str = Field(default="", max_length=100)
    sku: str = Field(default="", max_length=200)


class ReturnImportRequest(BaseModel):
    inspection_id: str = Field(min_length=1, max_length=100)
    mode: str
    dataset_id: str = Field(default="", max_length=100)
    name: str = Field(default="", max_length=100)
    change_note: str = Field(default="", max_length=500)


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


class TaskArchiveRequest(BaseModel):
    task_ids: list[str] = Field(min_length=1, max_length=100)
    archived: bool


class ReviewResolveRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    label_code: str | None = Field(default=None, max_length=100)
    note: str = Field(min_length=1, max_length=500)


class ReviewBatchCreateRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class SemanticItemReviewRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    semantic_item_id: str = Field(min_length=1, max_length=200)
    action: Literal["change_label", "remove", "no_tag_needed"]
    label_code: str | None = Field(default=None, max_length=100)
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def require_changed_label(self) -> "SemanticItemReviewRequest":
        if self.action == "change_label" and not self.label_code:
            raise ValueError("修改语义项标签时必须选择目标标签")
        return self


class AddedSemanticItemRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    item_id: str | None = Field(default=None, max_length=200)
    evidence_text: str = Field(min_length=1, max_length=4000)
    opinion: str = Field(min_length=1, max_length=2000)
    label_code: str = Field(min_length=1, max_length=100)
    note: str | None = Field(default=None, max_length=500)


class ReviewBatchRecordUpdateRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    action: Literal["confirm", "modify", "exclude"] = "confirm"
    label_code: str | None = Field(default=None, max_length=100)
    reason: str = Field(min_length=1, max_length=500)
    label_correctness: (
        Literal["correct", "partial", "incorrect", "not_applicable"] | None
    ) = None
    evidence_completeness: Literal["complete", "partial", "missing"] | None = None
    review_routing: (
        Literal["correct", "should_auto_approve", "should_manual_review"] | None
    ) = None
    semantic_item_reviews: list[SemanticItemReviewRequest] | None = Field(
        default=None,
        max_length=200,
    )
    added_semantic_items: list[AddedSemanticItemRequest] | None = Field(
        default=None,
        max_length=100,
    )
    coverage_status: Literal["complete", "has_omission"] | None = None


class ReviewBatchRecordRevision(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    expected_revision: int = Field(ge=1)


class ReviewBatchRecordBulkUpdateRequest(BaseModel):
    records: list[ReviewBatchRecordRevision] = Field(min_length=1, max_length=100)
    action: Literal["confirm", "modify", "exclude"]
    label_code: str | None = Field(default=None, max_length=100)
    reason: str = Field(min_length=1, max_length=500)
    label_correctness: (
        Literal["correct", "partial", "incorrect", "not_applicable"] | None
    ) = None
    evidence_completeness: Literal["complete", "partial", "missing"] | None = None
    review_routing: (
        Literal["correct", "should_auto_approve", "should_manual_review"] | None
    ) = None


class ReviewBatchPublishRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=500)


class ClassificationStandardVariantRequest(BaseModel):
    category_a: str = Field(min_length=1, max_length=100)
    category_b: str = Field(min_length=1, max_length=100)
    attributes: dict[str, str] = Field(default_factory=dict)


class ClassificationStandardLabelRequest(BaseModel):
    code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=100)
    group: str = Field(default="", max_length=100)
    parent_code: str | None = None
    description: str = Field(default="", max_length=500)
    keywords: list[str] = Field(default_factory=list, max_length=100)
    exclusions: list[str] = Field(default_factory=list, max_length=10)
    examples: list[LabelExample] = Field(default_factory=list, max_length=10)
    allowed_sentiments: list[str] = Field(max_length=3)
    allowed_claim_ids: list[str] | None = None


class ClassificationStandardDraftContentRequest(BaseModel):
    structure_version: Literal[1, 2] = 1
    categories: list[dict[str, object]] = Field(default_factory=list)
    import_sources: list[dict[str, object]] = Field(default_factory=list)
    recognition_profile: Literal["legacy_v3", "semantic_v1", "fact_v2"] = "legacy_v3"
    name: str = Field(min_length=1, max_length=120)
    product_context: str = Field(min_length=1, max_length=500)
    instructions: list[str] = Field(max_length=100)
    allowed_parts: list[str] = Field(min_length=1, max_length=50)
    validation_rules: dict[str, object] = Field(default_factory=dict)
    variants: list[ClassificationStandardVariantRequest] = Field(
        min_length=1,
        max_length=200,
    )
    labels: list[ClassificationStandardLabelRequest] = Field(
        max_length=500,
    )


class ClassificationStandardCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    product_context: str = Field(min_length=1, max_length=500)
    category_a: str = Field(min_length=1, max_length=100)
    category_b: str = Field(min_length=1, max_length=100)


class ClassificationStandardDraftUpdateRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    content: ClassificationStandardDraftContentRequest
    change_reason: str = Field(default="", max_length=500)


class ClassificationStandardImportDocument(BaseModel):
    format: Literal["classification-standard"]
    format_version: Literal[1]
    content_hash: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    snapshot: dict[str, object]


class ClassificationStandardDraftImportRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    document: ClassificationStandardImportDocument
    change_reason: str = Field(min_length=1, max_length=500)


class ClassificationStandardDraftRevisionRequest(BaseModel):
    expected_revision: int = Field(ge=1)


class ClassificationStandardDraftActionRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=500)


class ClassificationStandardSampleValidationRequest(BaseModel):
    comparison_type: Literal["standard_version", "keyword_ab", "semantic_ab"] = (
        "standard_version"
    )
    expected_revision: int = Field(ge=1)
    source_result_version_id: str = Field(min_length=1, max_length=120)
    sample_size: Literal[20, 50, 100] = 20


class ClassificationStandardValidationApprovalRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    note: str = Field(min_length=1, max_length=500)


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


class DatasetStorageCleanupRequest(BaseModel):
    dataset_ids: list[str] = Field(min_length=1, max_length=100)
    retention_days: int = Field(default=30, ge=7, le=3650)
    retain_latest: int = Field(default=2, ge=1, le=50)
