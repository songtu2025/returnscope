from typing import Literal

from pydantic import BaseModel, Field

from return_semantics.schemas import LabelExample


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
    review_role: Literal["primary", "secondary"] | None = None
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


class ClassificationStandardDraftPublishRequest(
    ClassificationStandardDraftActionRequest
):
    validation_run_id: str | None = Field(default=None, min_length=1, max_length=120)


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
