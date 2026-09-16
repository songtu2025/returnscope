from __future__ import annotations

from typing import Any

from return_semantics.data import ReturnDataset
from return_semantics.schemas import TaxonomyConfig, ValidatedClassification
from web_backend import classification_result_payload as _payload
from web_backend import classification_result_publication as _publication
from web_backend.classification_result_download import _ClassificationResultDownload
from web_backend.classification_result_queries import _ClassificationResultQueries
from web_backend.classification_result_records import _ClassificationResultRecords
from web_backend.common import json_text, new_id
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
        task_id: str,
        segment_id: str,
        dataset: ReturnDataset,
        results: dict[str, ValidatedClassification],
        taxonomy: TaxonomyConfig,
        segment_status: str,
        progress_total: int,
        model_calls: int,
        cache_hits: int,
        checkpoint_path: str,
        legacy_result_version: int,
        model_failures: int = 0,
    ) -> dict[str, Any]:
        prepared = self._prepare_publication(dataset, results, taxonomy)
        now = utc_now()
        conflict: str | None = None
        try:
            with self.database.transaction(immediate=True) as connection:
                task = connection.execute(
                    """
                    SELECT id, dataset_version_id, product_version_id,
                           owner_id, store, listing
                    FROM tasks WHERE id = ?
                    """,
                    (task_id,),
                ).fetchone()
                segment = connection.execute(
                    "SELECT * FROM task_segments WHERE id = ? AND task_id = ?",
                    (segment_id, task_id),
                ).fetchone()
                if task is None or segment is None:
                    raise ValueError("任务或 Listing 片段不存在")

                content_hash = self._content_hash(
                    str(task["dataset_version_id"]),
                    str(task["product_version_id"]),
                    prepared["units"],
                    prepared["records"],
                )
                existing = connection.execute(
                    """
                    SELECT v.* FROM classification_result_versions v
                    WHERE v.source_segment_id = ? AND v.version_no = 1
                    """,
                    (segment_id,),
                ).fetchone()
                if existing is not None:
                    if str(existing["content_hash"]) == content_hash:
                        return self._get_version_with_connection(
                            connection,
                            str(existing["id"]),
                        )
                    conflict = "Listing 片段 v1 已发布且内容哈希不同，拒绝覆盖"
                    connection.execute(
                        """
                        UPDATE task_segments
                        SET result_publish_error = ?, revision = revision + 1
                        WHERE id = ?
                        """,
                        (conflict, segment_id),
                    )
                    connection.execute(
                        """
                        INSERT INTO task_events(
                            task_id, event_type, stage, message,
                            data_json, created_at
                        ) VALUES (?, 'result_publish_conflict', '生成结果',
                                  ?, ?, ?)
                        """,
                        (
                            task_id,
                            conflict,
                            json_text(
                                {
                                    "segment_id": segment_id,
                                    "existing_content_hash": existing["content_hash"],
                                    "incoming_content_hash": content_hash,
                                }
                            ),
                            now,
                        ),
                    )
                else:
                    result_id = new_id("classification_result")
                    version_id = new_id("classification_version")
                    quality_status = _version_quality(
                        [str(value["quality_status"]) for value in prepared["units"]]
                    )
                    connection.execute(
                        """
                        INSERT INTO classification_results(
                            id, source_task_id, source_segment_id,
                            dataset_version_id, product_version_id,
                            store_site, listing, agent_key, agent_family,
                            logic_version, taxonomy_version,
                            model_policy_version, standard_version_id,
                            claims_version, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            result_id,
                            task_id,
                            segment_id,
                            task["dataset_version_id"],
                            task["product_version_id"],
                            prepared["store_site"] or task["store"],
                            prepared["listing"] or task["listing"],
                            segment["agent_key"],
                            segment["agent_family"],
                            segment["logic_version"],
                            segment["taxonomy_version"],
                            segment["model_policy_version"],
                            segment["standard_version_id"],
                            segment["claims_version"],
                            now,
                        ),
                    )
                    connection.execute(
                        """
                        INSERT INTO classification_result_versions(
                            id, result_id, source_segment_id, version_no,
                            content_hash, quality_status, publish_status,
                            unit_count, record_count, parent_version_id,
                            version_reason, created_by, created_at, published_at
                        ) VALUES (?, ?, ?, 1, ?, ?, 'publishing', ?, ?, NULL,
                                  '首次发布', ?, ?, NULL)
                        """,
                        (
                            version_id,
                            result_id,
                            segment_id,
                            content_hash,
                            quality_status,
                            len(prepared["units"]),
                            len(prepared["records"]),
                            task["owner_id"],
                            now,
                        ),
                    )
                    self._insert_units(
                        connection,
                        version_id,
                        prepared["units"],
                        prepared["labels"],
                    )
                    self._insert_records(
                        connection,
                        version_id,
                        str(task["dataset_version_id"]),
                        prepared["records"],
                    )
                    connection.execute(
                        """
                        UPDATE classification_result_versions
                        SET publish_status = 'published', published_at = ?
                        WHERE id = ?
                        """,
                        (now, version_id),
                    )
                    connection.execute(
                        """
                        UPDATE task_segments
                        SET status = ?, progress_current = ?, progress_total = ?,
                            model_calls = ?, cache_hits = ?, model_failures = ?,
                            error = NULL,
                            requested_action = NULL, result_json_path = ?,
                            result_version = ?, result_version_id = ?,
                            result_publish_status = 'published',
                            result_quality_status = ?, result_published_at = ?,
                            result_publish_error = NULL, completed_at = ?,
                            heartbeat_at = ?, revision = revision + 1
                        WHERE id = ? AND task_id = ?
                        """,
                        (
                            segment_status,
                            progress_total,
                            progress_total,
                            model_calls,
                            cache_hits,
                            model_failures,
                            checkpoint_path,
                            legacy_result_version,
                            version_id,
                            quality_status,
                            now,
                            now,
                            now,
                            segment_id,
                            task_id,
                        ),
                    )
                    connection.execute(
                        """
                        INSERT INTO task_events(
                            task_id, event_type, stage, message,
                            data_json, created_at
                        ) VALUES (?, 'segment_completed', '语义分析',
                                  'Listing 分类结果已发布', ?, ?)
                        """,
                        (
                            task_id,
                            json_text(
                                {
                                    "segment_id": segment_id,
                                    "status": segment_status,
                                    "result_version_id": version_id,
                                    "result_version": 1,
                                    "quality_status": quality_status,
                                }
                            ),
                            now,
                        ),
                    )
            if conflict is not None:
                raise ResultPublicationConflict(conflict)
        except ResultPublicationConflict:
            raise
        except Exception as exc:
            self.mark_publish_failed(task_id, segment_id, str(exc))
            raise ResultPublicationError(str(exc)) from exc
        version_id = self._published_version_id(segment_id)
        return self.get(version_id)
