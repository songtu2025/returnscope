from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from web_backend.common import json_text
from web_backend.database import Database
from web_backend.security import utc_now
from web_backend.task_contracts import TaskResultPublishConflict


class TaskResultPublishMixin:
    database: Database
    result_publisher: Callable[[str, str], dict[str, Any]] | None
    get: Callable[..., dict[str, Any] | None]
    _insert_audit: Callable[..., None]
    _validate_task_revision: Callable[..., None]

    def retry_result_publish(
        self,
        task_id: str,
        segment_id: str,
        actor_id: str,
        expected_revision: int,
        reason: str,
    ) -> dict[str, Any]:
        clean_reason, publisher = self._validate_result_publish_retry(reason)
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            task, segment = self._result_publish_retry_target(
                connection,
                task_id,
                segment_id,
                expected_revision,
            )

            connection.execute(
                """
                UPDATE task_segments
                SET result_publish_status = 'publishing',
                    result_publish_error = NULL, revision = revision + 1,
                    heartbeat_at = ?
                WHERE id = ? AND task_id = ?
                """,
                (now, segment_id, task_id),
            )
            connection.execute(
                """
                UPDATE tasks
                SET revision = revision + 1, heartbeat_at = ?
                WHERE id = ? AND revision = ?
                """,
                (now, task_id, expected_revision),
            )
            event_data = {
                "segment_id": segment_id,
                "segment_key": segment["segment_key"],
                "before_status": "failed",
                "after_status": "publishing",
                "reason": clean_reason,
            }
            connection.execute(
                """
                INSERT INTO task_events(
                    task_id, event_type, stage, message, actor_id,
                    data_json, created_at
                ) VALUES (?, 'result_publish_retry', '生成结果',
                          '正在重试发布 Listing 分类结果', ?, ?, ?)
                """,
                (task_id, actor_id, json_text(event_data), now),
            )
            self._insert_audit(
                connection,
                task_id,
                "retry_result_publish",
                actor_id,
                {
                    "segment_id": segment_id,
                    "result_publish_status": "failed",
                },
                {
                    "segment_id": segment_id,
                    "result_publish_status": "publishing",
                    "reason": clean_reason,
                },
                now,
            )

        publisher(task_id, segment_id)
        return self.get(task_id) or {}

    def _validate_result_publish_retry(
        self,
        reason: str,
    ) -> tuple[str, Callable[[str, str], dict[str, Any]]]:
        clean_reason = reason.strip()
        if not clean_reason:
            raise ValueError("请填写结果发布重试原因")
        publisher = self.result_publisher
        if publisher is None:
            raise TaskResultPublishConflict("结果发布重试服务未配置")
        return clean_reason, publisher

    def _result_publish_retry_target(
        self,
        connection: Any,
        task_id: str,
        segment_id: str,
        expected_revision: int,
    ) -> tuple[Any, Any]:
        task = connection.execute(
            "SELECT revision, stage FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
        self._validate_task_revision(task, expected_revision)
        segment = connection.execute(
            """
            SELECT * FROM task_segments
            WHERE task_id = ? AND id = ?
            """,
            (task_id, segment_id),
        ).fetchone()
        if segment is None:
            raise ValueError("Listing 片段不存在")
        publish_status = str(segment["result_publish_status"] or "")
        if publish_status == "publishing":
            raise TaskResultPublishConflict("Listing 分类结果正在发布，请勿重复提交")
        if publish_status == "published" or segment["result_version_id"]:
            raise TaskResultPublishConflict("Listing 分类结果已经发布")
        if publish_status != "failed":
            raise TaskResultPublishConflict("Listing 分类结果不处于发布失败状态")
        if segment["status"] not in {"completed", "completed_with_errors"}:
            raise TaskResultPublishConflict("仅分类已完成的 Listing 可以重试发布")
        checkpoint_path = str(segment["result_json_path"] or "").strip()
        if not checkpoint_path or not Path(checkpoint_path).is_file():
            raise TaskResultPublishConflict("没有可用的分类检查点，不能重试发布")
        return task, segment
