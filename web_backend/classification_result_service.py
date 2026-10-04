from __future__ import annotations

from typing import Any

from return_semantics.data import ReturnDataset
from return_semantics.schemas import TaxonomyConfig, ValidatedClassification
from web_backend import classification_result_payload as _payload
from web_backend import classification_result_publication as _publication
from web_backend.classification_result_download import _ClassificationResultDownload
from web_backend.classification_result_queries import _ClassificationResultQueries
from web_backend.classification_result_records import _ClassificationResultRecords
from web_backend.classification_results.publication_transaction import (
    _publication_versions as _publication_versions,
)
from web_backend.classification_results.publication_transaction import (
    publish_with_connection,
)
from web_backend.database import Database
from web_backend.security import utc_now

CONFIRMED_STATEMENT_TYPES = _payload.CONFIRMED_STATEMENT_TYPES
PAGE_SIZE_DEFAULT = _payload.PAGE_SIZE_DEFAULT
PAGE_SIZE_MAX = _payload.PAGE_SIZE_MAX
QUALITY_STATUSES = _payload.QUALITY_STATUSES
REVIEW_DISPOSITIONS = _payload.REVIEW_DISPOSITIONS
SEMANTIC_DISPOSITIONS = _payload.SEMANTIC_DISPOSITIONS
_classification_disposition = _payload._classification_disposition
_classification_quality = _payload._classification_quality
_comment_summary_status = _payload._comment_summary_status
_fact_id_by_label = _payload._fact_id_by_label
_is_confirmed_fact = _payload._is_confirmed_fact
_normalize_semantic_facts = _payload._normalize_semantic_facts
_nullable_text = _payload._nullable_text
_prepare_classification_payload = _payload._prepare_classification_payload
_scope_key = _payload._scope_key
_topic_identity = _payload._topic_identity
_topic_summaries = _payload._topic_summaries
_unit_fact_ids = _payload._unit_fact_ids
_unknown_disposition = _payload._unknown_disposition
_version_quality = _payload._version_quality

ClassificationResultNotFound = _publication.ClassificationResultNotFound
ResultPublicationConflict = _publication.ResultPublicationConflict
ResultPublicationError = _publication.ResultPublicationError
_ClassificationResultPublication = _publication._ClassificationResultPublication

ClassificationResultNotFound.__module__ = __name__
ResultPublicationConflict.__module__ = __name__
ResultPublicationError.__module__ = __name__


class ClassificationResultService(
    _ClassificationResultPublication,
    _ClassificationResultQueries,
    _ClassificationResultRecords,
    _ClassificationResultDownload,
):
    def __init__(self, database: Database) -> None:
        self.database = database

    def publish_v1(
        self,
        *,
        dataset: ReturnDataset,
        results: dict[str, ValidatedClassification],
        taxonomy: TaxonomyConfig,
        segment_state: _publication.SegmentPublicationState,
    ) -> dict[str, Any]:
        prepared = self._prepare_publication(dataset, results, taxonomy)
        now = utc_now()
        conflict: str | None = None
        try:
            with self.database.transaction(immediate=True) as connection:
                existing, conflict = publish_with_connection(
                    self, connection, prepared, segment_state, now
                )
                if existing is not None:
                    return existing
            if conflict is not None:
                raise ResultPublicationConflict(conflict)
        except ResultPublicationConflict:
            raise
        except Exception as exc:
            self.mark_publish_failed(
                segment_state.task_id, segment_state.segment_id, str(exc)
            )
            raise ResultPublicationError(str(exc)) from exc
        version_id = self._published_version_id(segment_state.segment_id)
        return self.get(version_id)
