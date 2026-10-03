from __future__ import annotations

from typing import Any

from return_semantics.semantic_review import (
    requires_business_review,
)
from web_backend.common import json_text, json_value, new_id
from web_backend.review_batches.editing_context import _ReviewEditingContext
from web_backend.review_contracts import ReviewBatchConflict
from web_backend.security import utc_now


class _ReviewBatchCreation(_ReviewEditingContext):
    def create_batch(
        self,
        base_result_version_id: str,
        actor_id: str,
        reason: str,
    ) -> dict[str, Any]:
        clean_reason = reason.strip()
        if not clean_reason:
            raise ValueError("请填写创建复核批次原因")
        now = utc_now()
        batch_id = new_id("review_batch")
        with self.database.transaction(immediate=True) as connection:
            base = connection.execute(
                """
                SELECT v.*, r.source_task_id
                FROM classification_result_versions v
                JOIN classification_results r ON r.id = v.result_id
                WHERE v.id = ? AND v.publish_status = 'published'
                """,
                (base_result_version_id,),
            ).fetchone()
            if base is None:
                raise ValueError("基准分类结果版本不存在或尚未发布")
            existing_draft = connection.execute(
                """
                SELECT id FROM review_batches
                WHERE base_result_version_id = ? AND status = 'draft'
                LIMIT 1
                """,
                (base_result_version_id,),
            ).fetchone()
            if existing_draft is not None:
                raise ReviewBatchConflict("该分类结果版本已有未发布的复核批次")
            candidate_units = connection.execute(
                """
                SELECT classification_key, comment, classification_json
                FROM classification_units
                WHERE result_version_id = ? AND quality_status != 'ready'
                ORDER BY classification_key
                """,
                (base_result_version_id,),
            ).fetchall()
            units = [
                unit
                for unit in candidate_units
                if requires_business_review(
                    json_value(unit["classification_json"], {}),
                    str(unit["comment"] or ""),
                )
            ]
            if not units:
                raise ValueError("该结果版本没有需要业务判断的分类单元")
            connection.execute(
                """
                INSERT INTO review_batches(
                    id, base_result_version_id, result_id, status,
                    revision, created_by, created_at, updated_at
                ) VALUES (?, ?, ?, 'draft', 1, ?, ?, ?)
                """,
                (
                    batch_id,
                    base_result_version_id,
                    base["result_id"],
                    actor_id,
                    now,
                    now,
                ),
            )
            connection.executemany(
                """
                INSERT INTO review_records(
                    id, task_id, batch_id, base_result_version_id,
                    classification_key, comment, workflow_status,
                    classification_json, revision, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, 1, ?)
                """,
                [
                    (
                        new_id("review"),
                        base["source_task_id"],
                        batch_id,
                        base_result_version_id,
                        unit["classification_key"],
                        str(unit["comment"] or ""),
                        unit["classification_json"],
                        now,
                    )
                    for unit in units
                ],
            )
            event_data = {
                "batch_id": batch_id,
                "base_result_version_id": base_result_version_id,
                "record_count": len(units),
                "reason": clean_reason,
            }
            connection.execute(
                """
                INSERT INTO task_events(
                    task_id, event_type, stage, message, actor_id,
                    data_json, created_at
                ) VALUES (?, 'review_batch_created', '人工复核',
                          '已创建分类结果复核批次', ?, ?, ?)
                """,
                (
                    base["source_task_id"],
                    actor_id,
                    json_text(event_data),
                    now,
                ),
            )
            self._insert_audit(
                connection,
                batch_id,
                "create",
                actor_id,
                {},
                event_data,
                now,
            )
        return self.get_batch(batch_id)
