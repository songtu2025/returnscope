"""人工修正只接收完整观点列表，版本和反馈组由路径限定。"""

from pydantic import BaseModel, Field

from web_backend.api_contracts.reviews import AddedSemanticItemRequest


class ManualCorrectionRequest(BaseModel):
    semantic_items: list[AddedSemanticItemRequest] = Field(max_length=100)
