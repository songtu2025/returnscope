"""分类结果查询参数，复用同一分页与筛选契约。"""

from pydantic import BaseModel, Field

from web_backend.classification_result_payload import PAGE_SIZE_DEFAULT, PAGE_SIZE_MAX


class ResultPaginationQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=PAGE_SIZE_DEFAULT, ge=1, le=PAGE_SIZE_MAX)


class ResultVersionQuery(ResultPaginationQuery):
    q: str | None = None
    store_site: str | None = None
    listing: str | None = None
    quality_status: str | None = None


class ResultRecordQuery(ResultPaginationQuery):
    order_id: str | None = None
    listing: str | None = None
    product_name: str | None = None
    source_sku: str | None = None
    matched_msku: str | None = None
    product_sku: str | None = None
    asin: str | None = None
    problem: str | None = None
    quality_status: str | None = None
    comment_status: str | None = None
    system_rerun_required: str | None = None


class ResultDrilldownQuery(BaseModel):
    group_by: str
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=PAGE_SIZE_DEFAULT, ge=1, le=PAGE_SIZE_MAX)
    problem: str | None = None
    product_name: str | None = None
    product_sku: str | None = None
    order_id: str | None = None
