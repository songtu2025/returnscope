from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from return_semantics.schemas import TaxonomyConfig

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
    system_rerun_required: bool
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


# 保留原模块标识，兼容既有响应模型和导入入口。
for _response_model in (
    CompatibleResponse,
    ClassificationSemanticFactResponse,
    ClassificationUnknownSemanticResponse,
    SemanticReviewItemResponse,
    SemanticReviewCoverageResponse,
    SemanticReviewResponse,
    ClassificationTopicSummaryResponse,
    ClassificationPayloadResponse,
    ClassificationResultRecordResponse,
    ClassificationResultRecordsResponse,
    ClassificationResultGroupMemberResponse,
    ClassificationResultGroupResponse,
    ClassificationResultGroupsResponse,
):
    _response_model.__module__ = "web_backend.api_contracts.classification_results"
del _response_model
