from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ReviewResolveRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    label_code: str | None = Field(default=None, max_length=100)
    note: str = Field(min_length=1, max_length=500)


class AddedSemanticItemRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    item_id: str | None = Field(default=None, max_length=200)
    evidence_text: str = Field(min_length=1, max_length=4000)
    opinion: str = Field(min_length=1, max_length=2000)
    label_code: str = Field(min_length=1, max_length=100)
    note: str | None = Field(default=None, max_length=500)
    sentiment: Literal["POSITIVE", "NEGATIVE", "NEUTRAL"] | None = None
