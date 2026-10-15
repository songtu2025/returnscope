"""旧复核批次保留明确停用的服务入口，历史数据通过查询服务读取。"""

from __future__ import annotations

from typing import Any

from web_backend.review_batches.classification import _ReviewClassification
from web_backend.review_contracts import LegacyReviewBatchClosed


class ReviewBatchEditingMixin(_ReviewClassification):
    def create_batch(self, *_args: object, **_kwargs: object) -> dict[str, Any]:
        raise LegacyReviewBatchClosed()

    def publish_batch(self, *_args: object, **_kwargs: object) -> dict[str, Any]:
        raise LegacyReviewBatchClosed()

    def update_batch_record(self, *_args: object, **_kwargs: object) -> dict[str, Any]:
        raise LegacyReviewBatchClosed()

    def update_batch_records(self, *_args: object, **_kwargs: object) -> dict[str, Any]:
        raise LegacyReviewBatchClosed()
