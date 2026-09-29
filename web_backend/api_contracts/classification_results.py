from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    SerializeAsAny,
)

from return_semantics.schemas import LabelDefinition, TaxonomyConfig

CommentSummaryStatusValue = Literal[
    "POSITIVE",
    "NEGATIVE",
    "MIXED",
    "CONFLICT",
    "NO_CONFIRMED",
]


class CompatibleResponse(BaseModel):
    model_config = ConfigDict(extra="allow")


class ClassificationSemanticFactResponse(CompatibleResponse):
    fact_id: str | None = None
    label_code: str
    label_code_path: list[str] = Field(default_factory=list)
    label_path: list[str] = Field(default_factory=list)
    actor_ref: str | None = None
    product_ref: str | None = None
    event_ref: str | None = None
    statement_type: str | None = None
    condition: str | dict[str, object] = ""
    evidence: str = ""
    evidence_source: str = "UNKNOWN"
    opinion: str = ""
    sentiment: str = ""
    assertion: str = ""
    part: str = ""
    implicit: bool = False
    fact_text_zh: str = ""
    original_evidence: str = ""
    object_ref: str = "CURRENT"
    usage_task: str = ""
    scenario: str = ""
    certainty: str = "AFFIRMED"


class ClassificationUnknownSemanticResponse(CompatibleResponse):
    opinion: str = ""
    evidence: str = ""
    reason: str = ""
    disposition: str


class SemanticReviewItemResponse(CompatibleResponse):
    item_id: str
    fact_id: str = ""
    evidence_text: str = ""
    evidence_source: str = "COMMENT"
    opinion: str = ""
    label_code: str = ""
    label_path: list[str] = Field(default_factory=list)
    disposition: str
    reason: str = ""
    diagnostic_domain: str | None = None
    diagnostic_code: str | None = None
    diagnostic_title: str | None = None
    detail_status: str | None = None
    primary_result: str | None = None
    secondary_result: str | None = None
    detail: str | None = None
    action: str | None = None
    business_review_required: bool | None = None


class SemanticReviewCoverageResponse(CompatibleResponse):
    total: int = 0
    mapped: int = 0
    no_tag_needed: int = 0
    taxonomy_gap: int = 0
    true_ambiguity: int = 0
    analysis_failure: int = 0
    unexplained_fragment_count: int = 0
    complete: bool = False


class SemanticReviewResponse(CompatibleResponse):
    semantic_items: list[SemanticReviewItemResponse] = Field(default_factory=list)
    coverage_summary: SemanticReviewCoverageResponse
    unexplained_fragments: list[str] = Field(default_factory=list)


class ClassificationTopicSummaryResponse(CompatibleResponse):
    topic_code: str
    topic_name: str
    topic_code_path: list[str] = Field(default_factory=list)
    topic_path: list[str] = Field(default_factory=list)
    status: CommentSummaryStatusValue
    supporting_fact_ids: list[str] = Field(default_factory=list)
    label_codes: list[str] = Field(default_factory=list)
    fact_count: int = 0
    event_count: int = 0


class ClassificationPayloadResponse(CompatibleResponse):
    classification_key: str | None = None
    semantic_units: list[ClassificationSemanticFactResponse] = Field(
        default_factory=list
    )
    unknown_semantics: list[ClassificationUnknownSemanticResponse] = Field(
        default_factory=list
    )
    primary_label_codes: list[str] = Field(default_factory=list)
    problem_label_codes: list[str] = Field(default_factory=list)
    positive_label_codes: list[str] = Field(default_factory=list)
    review_reasons: list[str] = Field(default_factory=list)
    model_name: str | None = None
    prompt_version: str | None = None
    taxonomy_version: str | None = None
    status: str | None = None
    needs_review: bool | None = None
    extracted_facts: list[dict[str, object]] = Field(default_factory=list)
    fact_mappings: list[dict[str, object]] = Field(default_factory=list)
    dimension_decisions: list[dict[str, object]] = Field(default_factory=list)
    semantic_relations: list[dict[str, object]] = Field(default_factory=list)
    comment_summary: dict[str, object] | None = None
    semantic_review: SemanticReviewResponse | None = None


class ClassificationResultRecordResponse(CompatibleResponse):
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
    ignored_semantics: list[ClassificationUnknownSemanticResponse] = Field(
        default_factory=list
    )
    classification: ClassificationPayloadResponse
    result_version_id: str
    classification_key: str
    source_record_id: str
    source_row: int
    source_origin_id: str | None = None
    return_date: str | None = None
    order_id: str | None = None
    store_site: str | None = None
    listing: str | None = None
    product_name: str | None = None
    source_sku: str | None = None
    matched_msku: str | None = None
    product_sku: str | None = None
    asin: str | None = None
    fnsku: str | None = None
    category_a: str | None = None
    category_b: str | None = None
    reason: str | None = None
    comment: str | None = None
    product_match_status: str
    problem_labels: list[str] = Field(default_factory=list)


class ClassificationResultRecordsResponse(CompatibleResponse):
    taxonomy: TaxonomyConfig | None = None
    items: list[ClassificationResultRecordResponse]
    total: int
    page: int
    page_size: int


class ClassificationResultGroupMemberResponse(CompatibleResponse):
    source_record_id: str
    source_row: int
    source_origin_id: str | None = None
    return_date: str | None = None
    reason: str | None = None
    comment: str | None = None


class ClassificationResultGroupResponse(CompatibleResponse):
    record: ClassificationResultRecordResponse
    member_count: int
    members: list[ClassificationResultGroupMemberResponse]


class ClassificationResultGroupsResponse(CompatibleResponse):
    items: list[ClassificationResultGroupResponse]
    total: int
    source_total: int
    page: int
    page_size: int


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
