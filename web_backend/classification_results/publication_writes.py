from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from web_backend.classification_result_publication import SegmentPublicationState
from web_backend.common import json_text


@dataclass(frozen=True)
class PublicationVersion:
    """传递同一事务中已确定的版本信息，避免写回时重新计算。"""

    result_id: str
    version_id: str
    version_no: int
    content_hash: str
    quality_status: str
    parent_version_id: str | None
    now: str


def insert_result(
    connection: Any,
    task: Any,
    segment: Any,
    prepared: dict[str, Any],
    version: PublicationVersion,
) -> None:
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
            version.result_id,
            task["id"],
            segment["id"],
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
            version.now,
        ),
    )


def insert_version(
    connection: Any,
    task: Any,
    segment_state: SegmentPublicationState,
    prepared: dict[str, Any],
    version: PublicationVersion,
) -> None:
    connection.execute(
        """
        INSERT INTO classification_result_versions(
            id, result_id, source_segment_id, version_no,
            content_hash, quality_status, publish_status,
            unit_count, record_count, parent_version_id,
            version_reason, created_by, created_at, published_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'publishing', ?, ?, ?,
                  ?, ?, ?, NULL)
        """,
        (
            version.version_id,
            version.result_id,
            segment_state.segment_id,
            version.version_no,
            version.content_hash,
            version.quality_status,
            len(prepared["units"]),
            len(prepared["records"]),
            version.parent_version_id,
            (
                "系统异常局部重跑"
                if version.parent_version_id is not None
                else "首次发布"
            ),
            task["owner_id"],
            version.now,
        ),
    )


def publish_version(
    connection: Any,
    segment_state: SegmentPublicationState,
    version: PublicationVersion,
) -> None:
    connection.execute(
        """
        UPDATE classification_result_versions
        SET publish_status = 'published', published_at = ?
        WHERE id = ?
        """,
        (version.now, version.version_id),
    )
    update_segment(connection, segment_state, version)
    record_completion(connection, segment_state, version)


def update_segment(
    connection: Any, segment_state: SegmentPublicationState, version: PublicationVersion
) -> None:
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
            segment_state.segment_status,
            segment_state.progress_total,
            segment_state.progress_total,
            segment_state.model_calls,
            segment_state.cache_hits,
            segment_state.model_failures,
            segment_state.checkpoint_path,
            segment_state.legacy_result_version,
            version.version_id,
            version.quality_status,
            version.now,
            version.now,
            version.now,
            segment_state.segment_id,
            segment_state.task_id,
        ),
    )


def record_completion(
    connection: Any, segment_state: SegmentPublicationState, version: PublicationVersion
) -> None:
    connection.execute(
        """
        INSERT INTO task_events(
            task_id, event_type, stage, message,
            data_json, created_at
        ) VALUES (?, 'segment_completed', '语义分析',
                  'Listing 分类结果已发布', ?, ?)
        """,
        (
            segment_state.task_id,
            json_text(
                {
                    "segment_id": segment_state.segment_id,
                    "status": segment_state.segment_status,
                    "result_version_id": version.version_id,
                    "result_version": version.version_no,
                    "parent_version_id": version.parent_version_id,
                    "quality_status": version.quality_status,
                }
            ),
            version.now,
        ),
    )


def record_conflict(
    connection: Any,
    segment_state: SegmentPublicationState,
    latest: Any,
    content_hash: str,
    now: str,
) -> str:
    conflict = "Listing 片段已发布且内容哈希不同，拒绝覆盖"
    connection.execute(
        """
        UPDATE task_segments SET result_publish_error = ?, revision = revision + 1
        WHERE id = ?
        """,
        (conflict, segment_state.segment_id),
    )
    connection.execute(
        """
        INSERT INTO task_events(
            task_id, event_type, stage, message, data_json, created_at
        )
        VALUES (?, 'result_publish_conflict', '生成结果', ?, ?, ?)
        """,
        (
            segment_state.task_id,
            conflict,
            json_text(
                {
                    "segment_id": segment_state.segment_id,
                    "existing_content_hash": latest["content_hash"],
                    "incoming_content_hash": content_hash,
                }
            ),
            now,
        ),
    )
    return conflict
