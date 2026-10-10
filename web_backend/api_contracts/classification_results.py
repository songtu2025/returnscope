from typing import Annotated, Literal

from pydantic import (
    BeforeValidator,
    ConfigDict,
    PlainSerializer,
    SerializeAsAny,
)

from return_semantics.schemas import LabelDefinition, TaxonomyConfig
from web_backend.api_contracts.classification_result_records import (
    ClassificationPayloadResponse as ClassificationPayloadResponse,
)
from web_backend.api_contracts.classification_result_records import (
    ClassificationResultGroupMemberResponse as ClassificationResultGroupMemberResponse,
)
from web_backend.api_contracts.classification_result_records import (
    ClassificationResultGroupResponse as ClassificationResultGroupResponse,
)
from web_backend.api_contracts.classification_result_records import (
    ClassificationResultGroupsResponse as ClassificationResultGroupsResponse,
)
from web_backend.api_contracts.classification_result_records import (
    ClassificationResultRecordResponse as ClassificationResultRecordResponse,
)
from web_backend.api_contracts.classification_result_records import (
    ClassificationResultRecordsResponse as ClassificationResultRecordsResponse,
)
from web_backend.api_contracts.classification_result_records import (
    ClassificationSemanticFactResponse as ClassificationSemanticFactResponse,
)
from web_backend.api_contracts.classification_result_records import (
    ClassificationTopicSummaryResponse as ClassificationTopicSummaryResponse,
)
from web_backend.api_contracts.classification_result_records import (
    ClassificationUnknownSemanticResponse as ClassificationUnknownSemanticResponse,
)
from web_backend.api_contracts.classification_result_records import (
    CommentSummaryStatusValue as CommentSummaryStatusValue,
)
from web_backend.api_contracts.classification_result_records import (
    CompatibleResponse as CompatibleResponse,
)
from web_backend.api_contracts.classification_result_records import (
    SemanticReviewCoverageResponse as SemanticReviewCoverageResponse,
)
from web_backend.api_contracts.classification_result_records import (
    SemanticReviewItemResponse as SemanticReviewItemResponse,
)
from web_backend.api_contracts.classification_result_records import (
    SemanticReviewResponse as SemanticReviewResponse,
)


class ClassificationResultBlockingReasonResponse(CompatibleResponse):
    code: str
    message: str


class ClassificationResultVersionResponse(CompatibleResponse):
    version_id: str
    result_id: str
    version: int
    content_hash: str
    quality_status: Literal["ready", "review_required", "unusable"]
    publish_status: Literal["publishing", "published", "failed"]
    unit_count: int
    record_count: int
    created_at: str
    published_at: str | None
    parent_version_id: str | None
    version_reason: str
    created_by: str | None
    created_by_name: str | None
    source_review_batch_id: str | None
    parent_version_no: int | None
    changed_unit_count: int
    inherited_unit_count: int
    source_task_id: str
    source_segment_id: str
    analysis_context: Literal["returns", "review", "user_feedback"]
    dataset_version_id: str
    product_version_id: str
    store_site: str | None
    listing: str | None
    agent_key: str
    agent_family: str
    logic_version: str | None
    taxonomy_version: str
    model_policy_version: str | None
    standard_version_id: str | None
    standard_id: str | None
    standard_name: str | None
    standard_version: int | None
    claims_version: str | None
    dataset_name: str
    dataset_version: int
    product_dataset_name: str
    product_version: int
    product_names: list[str]
    delivery_status: Literal["ready", "needs_review", "review-derived", "unusable"]
    publish_origin: Literal["original-classification", "review-derived"]
    dashboard_eligibility: bool
    blocking_reasons: list[ClassificationResultBlockingReasonResponse]


class ClassificationResultListResponse(CompatibleResponse):
    items: list[ClassificationResultVersionResponse]
    total: int
    page: int
    page_size: int


class ClassificationResultTaxonomyLabelResponse(LabelDefinition):
    model_config = ConfigDict(extra="allow")

    label_path: list[str]


def _validate_result_taxonomy_label(
    value: object,
) -> ClassificationResultTaxonomyLabelResponse:
    return ClassificationResultTaxonomyLabelResponse.model_validate(value)


def _serialize_result_taxonomy_label(
    value: LabelDefinition,
) -> ClassificationResultTaxonomyLabelResponse:
    if isinstance(value, ClassificationResultTaxonomyLabelResponse):
        return value
    return ClassificationResultTaxonomyLabelResponse.model_validate(value)


ClassificationResultTaxonomyLabel = Annotated[
    SerializeAsAny[LabelDefinition],
    BeforeValidator(
        _validate_result_taxonomy_label,
        json_schema_input_type=ClassificationResultTaxonomyLabelResponse,
    ),
    PlainSerializer(
        _serialize_result_taxonomy_label,
        return_type=ClassificationResultTaxonomyLabelResponse,
    ),
]


class ClassificationResultTaxonomyResponse(TaxonomyConfig):
    model_config = ConfigDict(extra="allow")

    labels: list[ClassificationResultTaxonomyLabel]
    standard_id: str
    standard_version_id: str
    standard_name: str
    standard_version: int


class ClassificationResultMetricsResponse(CompatibleResponse):
    primary_unit: Literal["comment"]
    comment_count: int
    source_record_count: int
    fact_count: int
    event_count: int


class ClassificationResultQualityCountResponse(CompatibleResponse):
    quality_status: str
    unit_count: int
    record_count: int
    comment_count: int


class ClassificationResultProcessingCountResponse(CompatibleResponse):
    processing_status: str
    unit_count: int
    record_count: int
    comment_count: int


class ClassificationResultDispositionCountResponse(CompatibleResponse):
    semantic_disposition: str
    comment_count: int
    record_count: int


class ClassificationResultCommentStatusCountResponse(CompatibleResponse):
    status: CommentSummaryStatusValue
    comment_count: int


class ClassificationResultTopicAggregateResponse(CompatibleResponse):
    topic_code: str
    topic_name: str
    topic_code_path: list[str]
    topic_path: list[str]
    comment_count: int
    fact_count: int
    event_count: int
    status_counts: dict[str, int]


class ClassificationResultProblemCountResponse(CompatibleResponse):
    label_code: str
    label_name: str | None
    label_group: str | None
    record_count: int
    unit_count: int
    comment_count: int
    label_path: list[str]


class ClassificationResultDrilldownItemResponse(CompatibleResponse):
    value: str | None
    record_count: int
    unit_count: int
    label_code: str | None = None
    label_name: str | None = None
    label_group: str | None = None
    label_path: list[str] | None = None
    parent_code: str | None = None


class ClassificationResultDrilldownResponse(CompatibleResponse):
    group_by: Literal["category", "problem", "product_name", "product_sku"]
    items: list[ClassificationResultDrilldownItemResponse]
    total: int
    page: int
    page_size: int


class ClassificationResultSummaryResponse(CompatibleResponse):
    version_id: str
    comment_count: int
    total_comment_count: int
    metrics: ClassificationResultMetricsResponse
    quality: list[ClassificationResultQualityCountResponse]
    processing_statuses: list[ClassificationResultProcessingCountResponse]
    comment_statuses: list[ClassificationResultCommentStatusCountResponse]
    semantic_dispositions: list[ClassificationResultDispositionCountResponse]
    topic_summaries: list[ClassificationResultTopicAggregateResponse]
    top_problems: list[ClassificationResultProblemCountResponse]
    hierarchy_problems: list[ClassificationResultDrilldownItemResponse]
