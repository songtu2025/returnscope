from __future__ import annotations

from typing import TYPE_CHECKING, Any

from web_backend.classification_result_payload import _version_quality
from web_backend.classification_result_publication import SegmentPublicationState
from web_backend.classification_result_queries import system_rerun_count
from web_backend.classification_results.publication_writes import (
    PublicationVersion,
    insert_result,
    insert_version,
    publish_version,
    record_conflict,
)
from web_backend.common import new_id

if TYPE_CHECKING:
    from web_backend.classification_result_service import ClassificationResultService


def _publication_versions(connection: Any, segment: Any) -> tuple[Any, Any]:
    latest_version = connection.execute(
        """
        SELECT v.* FROM classification_result_versions v
        WHERE v.source_segment_id = ?
        ORDER BY v.version_no DESC
        LIMIT 1
        """,
        (segment["id"],),
    ).fetchone()
    active_system_rerun = (
        segment["result_version_id"] is not None and str(segment["status"]) == "running"
    )
    if not active_system_rerun:
        return latest_version, None
    if not system_rerun_count(connection, str(segment["result_version_id"])):
        raise ValueError("Listing 片段没有需要系统重跑的分类结果")
    parent_version = connection.execute(
        """
        SELECT * FROM classification_result_versions
        WHERE id = ? AND source_segment_id = ?
        """,
        (segment["result_version_id"], segment["id"]),
    ).fetchone()
    if parent_version is None:
        raise ValueError("Listing 片段当前结果版本不存在")
    return None, parent_version


def publish_with_connection(
    service: ClassificationResultService,
    connection: Any,
    prepared: dict[str, Any],
    segment_state: SegmentPublicationState,
    now: str,
) -> tuple[dict[str, Any] | None, str | None]:
    task, segment = publication_source(connection, segment_state)
    content_hash = service._content_hash(
        str(task["dataset_version_id"]),
        str(task["product_version_id"]),
        prepared["units"],
        prepared["records"],
    )
    latest, parent = _publication_versions(connection, segment)
    if latest is not None:
        if str(latest["content_hash"]) == content_hash:
            return service._get_version_with_connection(
                connection, str(latest["id"])
            ), None
        return None, record_conflict(
            connection, segment_state, latest, content_hash, now
        )
    version = new_publication_version(connection, parent, prepared, content_hash, now)
    if parent is None:
        insert_result(connection, task, segment, prepared, version)
    insert_version(connection, task, segment_state, prepared, version)
    service._insert_units(
        connection, version.version_id, prepared["units"], prepared["labels"]
    )
    service._insert_records(
        connection,
        version.version_id,
        str(task["dataset_version_id"]),
        prepared["records"],
    )
    publish_version(connection, segment_state, version)
    return None, None


def publication_source(
    connection: Any, segment_state: SegmentPublicationState
) -> tuple[Any, Any]:
    task = connection.execute(
        """
        SELECT id, dataset_version_id, product_version_id, owner_id, store, listing
        FROM tasks WHERE id = ?
        """,
        (segment_state.task_id,),
    ).fetchone()
    segment = connection.execute(
        "SELECT * FROM task_segments WHERE id = ? AND task_id = ?",
        (segment_state.segment_id, segment_state.task_id),
    ).fetchone()
    if task is None or segment is None:
        raise ValueError("任务或 Listing 片段不存在")
    return task, segment


def new_publication_version(
    connection: Any,
    parent: Any,
    prepared: dict[str, Any],
    content_hash: str,
    now: str,
) -> PublicationVersion:
    result_id = (
        str(parent["result_id"])
        if parent is not None
        else new_id("classification_result")
    )
    version_no = (
        int(
            connection.execute(
                """
                SELECT COALESCE(MAX(version_no), 0) + 1
                FROM classification_result_versions WHERE result_id = ?
                """,
                (result_id,),
            ).fetchone()[0]
        )
        if parent is not None
        else 1
    )
    return PublicationVersion(
        result_id=result_id,
        version_id=new_id("classification_version"),
        version_no=version_no,
        content_hash=content_hash,
        quality_status=_version_quality(
            [str(value["quality_status"]) for value in prepared["units"]]
        ),
        parent_version_id=str(parent["id"]) if parent is not None else None,
        now=now,
    )
