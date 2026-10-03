from __future__ import annotations

from builtins import list as builtin_list
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from return_semantics.schemas import TaxonomyConfig
from web_backend.classification_result_service import ClassificationResultService
from web_backend.classification_standard_service import ClassificationStandardService
from web_backend.common import json_text, json_value, new_id
from web_backend.database import Database
from web_backend.review_contracts import (
    ReviewBatchConflict,
    RevisionConflict,
    _BatchPublishRequest,
    _CompletedReviewChanges,
    _DerivedResultContent,
)
from web_backend.review_label_corrections import apply_semantic_review_changes
from web_backend.reviews.publication_content import ReviewPublicationContentMixin
from web_backend.security import utc_now


class ReviewPublicationMixin(ReviewPublicationContentMixin):
    database: Database
    result_service: ClassificationResultService
    standard_service: ClassificationStandardService

    if TYPE_CHECKING:
        _insert_audit: Callable[
            [Any, str, str, str, dict[str, Any], dict[str, Any], str],
            None,
        ]

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

    def _load_publish_batch(
        self,
        connection: Any,
        request: _BatchPublishRequest,
    ) -> Any:
        batch = connection.execute(
            """
            SELECT b.*, v.source_segment_id, v.content_hash AS base_hash,
                   v.publish_status AS base_publish_status,
                   r.source_task_id, r.dataset_version_id,
                   r.product_version_id
            FROM review_batches b
            JOIN classification_result_versions v
              ON v.id = b.base_result_version_id
            JOIN classification_results r ON r.id = b.result_id
            WHERE b.id = ?
            """,
            (request.batch_id,),
        ).fetchone()
        if batch is None:
            raise ValueError("复核批次不存在")
        if int(batch["revision"]) != request.expected_revision:
            raise RevisionConflict("批次已被其他用户修改，请刷新后重试")
        if batch["status"] == "published":
            raise ReviewBatchConflict("复核批次已经发布，不能重复提交")
        if batch["base_publish_status"] != "published":
            raise ReviewBatchConflict("基准分类结果版本不可用")
        latest_version = connection.execute(
            """
            SELECT id FROM classification_result_versions
            WHERE result_id = ? AND publish_status = 'published'
            ORDER BY version_no DESC LIMIT 1
            """,
            (batch["result_id"],),
        ).fetchone()
        if latest_version is None or str(latest_version["id"]) != str(
            batch["base_result_version_id"]
        ):
            raise ReviewBatchConflict(
                "基准分类结果版本已过期，请基于最新版本重新创建复核批次"
            )
        return batch

    @staticmethod
    def _load_completed_review_changes(
        connection: Any,
        batch_id: str,
        taxonomy: TaxonomyConfig,
    ) -> _CompletedReviewChanges:
        review_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM review_records WHERE batch_id = ?",
                (batch_id,),
            ).fetchone()[0]
        )
        if review_count == 0:
            raise ReviewBatchConflict("复核批次没有可处理的复核记录")
        pending_count = int(
            connection.execute(
                """
                SELECT COUNT(*) FROM review_records
                WHERE batch_id = ?
                  AND workflow_status NOT IN ('resolved', 'excluded')
                """,
                (batch_id,),
            ).fetchone()[0]
        )
        if pending_count:
            raise ReviewBatchConflict(f"复核批次仍有 {pending_count} 条记录未完成")
        revisions = {
            str(row["classification_key"]): apply_semantic_review_changes(
                json_value(row["classification_json"], {}),
                taxonomy,
                str(row["comment"]),
            )
            for row in connection.execute(
                """
                SELECT classification_key, classification_json, comment
                FROM review_records
                WHERE batch_id = ? AND workflow_status = 'resolved'
                """,
                (batch_id,),
            ).fetchall()
        }
        excluded_keys = {
            str(row["classification_key"])
            for row in connection.execute(
                """
                SELECT classification_key FROM review_records
                WHERE batch_id = ? AND workflow_status = 'excluded'
                """,
                (batch_id,),
            ).fetchall()
        }
        return _CompletedReviewChanges(
            revisions=revisions,
            excluded_keys=excluded_keys,
        )

    def _publish_derived_result_version(
        self,
        connection: Any,
        batch: Any,
        content: _DerivedResultContent,
        request: _BatchPublishRequest,
    ) -> tuple[str, int]:
        next_version = int(
            connection.execute(
                """
                SELECT COALESCE(MAX(version_no), 0) + 1
                FROM classification_result_versions WHERE result_id = ?
                """,
                (batch["result_id"],),
            ).fetchone()[0]
        )
        version_id = new_id("classification_version")
        qualities = [str(unit["quality_status"]) for unit in content.units]
        quality_status = self._version_quality(qualities)
        content_hash = self.result_service._content_hash(
            str(batch["dataset_version_id"]),
            str(batch["product_version_id"]),
            content.units,
            content.records,
        )
        connection.execute(
            """
            INSERT INTO classification_result_versions(
                id, result_id, source_segment_id, version_no,
                content_hash, quality_status, publish_status,
                unit_count, record_count, parent_version_id,
                version_reason, created_by, created_at, published_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'publishing', ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                version_id,
                batch["result_id"],
                batch["source_segment_id"],
                next_version,
                content_hash,
                quality_status,
                len(content.units),
                len(content.records),
                batch["base_result_version_id"],
                request.reason,
                request.actor_id,
                request.now,
            ),
        )
        self.result_service._insert_units(
            connection,
            version_id,
            content.units,
            content.labels,
        )
        self.result_service._insert_records(
            connection,
            version_id,
            str(batch["dataset_version_id"]),
            content.records,
        )
        connection.execute(
            """
            UPDATE classification_result_versions
            SET publish_status = 'published', published_at = ?
            WHERE id = ?
            """,
            (request.now, version_id),
        )
        return version_id, next_version

    def _finalize_batch_publication(
        self,
        connection: Any,
        batch: Any,
        request: _BatchPublishRequest,
        published_version: tuple[str, int],
    ) -> None:
        version_id, version_no = published_version
        connection.execute(
            """
            UPDATE review_batches
            SET status = 'published', revision = revision + 1,
                updated_at = ?, published_version_id = ?, published_at = ?
            WHERE id = ? AND revision = ? AND status = 'draft'
            """,
            (
                request.now,
                version_id,
                request.now,
                request.batch_id,
                request.expected_revision,
            ),
        )
        event_data = {
            "batch_id": request.batch_id,
            "base_result_version_id": batch["base_result_version_id"],
            "result_version_id": version_id,
            "version": version_no,
            "reason": request.reason,
        }
        connection.execute(
            """
            INSERT INTO task_events(
                task_id, event_type, stage, message, actor_id,
                data_json, created_at
            ) VALUES (?, 'review_batch_published', '人工复核',
                      '复核批次已发布为新的分类结果版本', ?, ?, ?)
            """,
            (
                batch["source_task_id"],
                request.actor_id,
                json_text(event_data),
                request.now,
            ),
        )
        self._insert_audit(
            connection,
            request.batch_id,
            "publish",
            request.actor_id,
            {
                "status": "draft",
                "base_result_version_id": batch["base_result_version_id"],
            },
            {
                "status": "published",
                "result_version_id": version_id,
                "reason": request.reason,
            },
            request.now,
        )

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
