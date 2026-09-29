from datetime import date

from pydantic import BaseModel, Field


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
