from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
