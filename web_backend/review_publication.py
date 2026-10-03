from __future__ import annotations

from builtins import list as builtin_list
from typing import Any

from web_backend.classification_result_service import ClassificationResultService
from web_backend.classification_standard_service import ClassificationStandardService
from web_backend.common import json_text
from web_backend.database import Database
from web_backend.review_contracts import (
    ReviewBatchConflict,
    RevisionConflict,
    _BatchPublishRequest,
)
from web_backend.reviews.publication_content import ReviewPublicationContentMixin
from web_backend.reviews.publication_persistence import (
    ReviewPublicationPersistenceMixin,
)
from web_backend.security import utc_now


class ReviewPublicationMixin(
    ReviewPublicationContentMixin,
    ReviewPublicationPersistenceMixin,
):
    database: Database
    result_service: ClassificationResultService
    standard_service: ClassificationStandardService

    def publish_batch(
        self,
        batch_id: str,
        expected_revision: int,
        actor_id: str,
        reason: str,
    ) -> dict[str, Any]:
        clean_reason = reason.strip()
        if not clean_reason:
            raise ValueError("请填写发布原因")
        request = _BatchPublishRequest(
            batch_id=batch_id,
            expected_revision=expected_revision,
            actor_id=actor_id,
            reason=clean_reason,
            now=utc_now(),
        )
        try:
            with self.database.transaction(immediate=True) as connection:
                batch = self._load_publish_batch(connection, request)
                taxonomy = self.standard_service.taxonomy_config_for_result_version(
                    str(batch["base_result_version_id"])
                )
                label_map = {label.code: label for label in taxonomy.labels}
                changes = self._load_completed_review_changes(
                    connection,
                    request.batch_id,
                    taxonomy,
                )
                content = self._build_derived_result_content(
                    connection,
                    batch,
                    changes,
                    label_map,
                )
                published_version = self._publish_derived_result_version(
                    connection,
                    batch,
                    content,
                    request,
                )
                self._finalize_batch_publication(
                    connection,
                    batch,
                    request,
                    published_version,
                )
                version_id, _version_no = published_version
        except (RevisionConflict, ReviewBatchConflict) as exc:
            self._record_batch_conflict(batch_id, actor_id, str(exc))
            raise
        return self.result_service.get(version_id)

    @staticmethod
    def _version_quality(qualities: builtin_list[str]) -> str:
        if qualities and all(value == "unusable" for value in qualities):
            return "unusable"
        if any(value not in {"ready", "excluded"} for value in qualities):
            return "review_required"
        return "ready"

    def _record_batch_conflict(
        self,
        batch_id: str,
        actor_id: str,
        message: str,
    ) -> None:
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            batch = connection.execute(
                """
                SELECT b.revision, r.source_task_id
                FROM review_batches b
                JOIN classification_results r ON r.id = b.result_id
                WHERE b.id = ?
                """,
                (batch_id,),
            ).fetchone()
            if batch is None:
                return
            data = {"batch_id": batch_id, "message": message[:500]}
            connection.execute(
                """
                INSERT INTO task_events(
                    task_id, event_type, stage, message, actor_id,
                    data_json, created_at
                ) VALUES (?, 'review_batch_conflict', '人工复核',
                          '复核批次操作冲突', ?, ?, ?)
                """,
                (
                    batch["source_task_id"],
                    actor_id,
                    json_text(data),
                    now,
                ),
            )
            self._insert_audit(
                connection,
                batch_id,
                "conflict",
                actor_id,
                {"revision": int(batch["revision"])},
                data,
                now,
            )
