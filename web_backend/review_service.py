from __future__ import annotations

from web_backend import review_contracts as _contracts
from web_backend import review_queries as _queries
from web_backend.classification_result_service import ClassificationResultService
from web_backend.classification_standard_service import ClassificationStandardService
from web_backend.database import Database
from web_backend.review_batch_editing import ReviewBatchEditingMixin
from web_backend.review_resolution import ReviewResolutionMixin
from web_backend.reviews.publication_content import ReviewPublicationContentMixin

_TASK_LOCKS = _contracts._TASK_LOCKS
_LOCKS_GUARD = _contracts._LOCKS_GUARD
_BATCH_SUMMARY_SELECT = _queries._BATCH_SUMMARY_SELECT
_task_lock = _contracts._task_lock
RevisionConflict = _contracts.RevisionConflict
ReviewBatchConflict = _contracts.ReviewBatchConflict
ReviewQueriesMixin = _queries.ReviewQueriesMixin

_task_lock.__module__ = __name__
RevisionConflict.__module__ = __name__
ReviewBatchConflict.__module__ = __name__


class ReviewService(
    ReviewQueriesMixin,
    ReviewBatchEditingMixin,
    ReviewPublicationContentMixin,
    ReviewResolutionMixin,
):
    def __init__(
        self,
        database: Database,
        result_service: ClassificationResultService | None = None,
        standard_service: ClassificationStandardService | None = None,
    ) -> None:
        self.database = database
        self.result_service = result_service or ClassificationResultService(database)
        self.standard_service = standard_service or ClassificationStandardService(
            database
        )
        self.capability_registry = self.standard_service.active_registry()
