from __future__ import annotations

from typing import Any

from web_backend import review_contracts as _contracts
from web_backend import review_queries as _queries
from web_backend.classification_result_service import ClassificationResultService
from web_backend.classification_standard_service import ClassificationStandardService
from web_backend.common import json_text, new_id
from web_backend.database import Database
from web_backend.review_batch_editing import ReviewBatchEditingMixin
from web_backend.review_publication import ReviewPublicationMixin
from web_backend.review_resolution import ReviewResolutionMixin

_TASK_LOCKS = _contracts._TASK_LOCKS
_LOCKS_GUARD = _contracts._LOCKS_GUARD
_BATCH_SUMMARY_SELECT = _queries._BATCH_SUMMARY_SELECT
_task_lock = _contracts._task_lock
RevisionConflict = _contracts.RevisionConflict
ReviewBatchConflict = _contracts.ReviewBatchConflict
_BatchPublishRequest = _contracts._BatchPublishRequest
_CompletedReviewChanges = _contracts._CompletedReviewChanges
_DerivedResultContent = _contracts._DerivedResultContent
ReviewQueriesMixin = _queries.ReviewQueriesMixin

_task_lock.__module__ = __name__
RevisionConflict.__module__ = __name__
ReviewBatchConflict.__module__ = __name__
_BatchPublishRequest.__module__ = __name__
_CompletedReviewChanges.__module__ = __name__
_DerivedResultContent.__module__ = __name__


class ReviewService(
    ReviewQueriesMixin,
    ReviewBatchEditingMixin,
    ReviewPublicationMixin,
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

    @staticmethod
    def _insert_audit(
        connection: Any,
        batch_id: str,
        action: str,
        actor_id: str,
        before: dict[str, Any],
        after: dict[str, Any],
        created_at: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO audit_logs(
                id, entity_type, entity_id, action, before_json,
                after_json, actor_id, created_at
            ) VALUES (?, 'review_batch', ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id("audit"),
                batch_id,
                action,
                json_text(before),
                json_text(after),
                actor_id,
                created_at,
            ),
        )
