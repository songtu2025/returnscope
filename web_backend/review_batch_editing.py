from __future__ import annotations

from builtins import list as builtin_list
from typing import Any

from web_backend.common import json_text
from web_backend.review_batches.creation import _ReviewBatchCreation
from web_backend.review_batches.record_editing import _ReviewRecordEditing
from web_backend.review_contracts import (
    ReviewBatchConflict,
    ReviewRecordChange,
    RevisionConflict,
)
from web_backend.security import utc_now


class ReviewBatchEditingMixin(_ReviewBatchCreation, _ReviewRecordEditing):
    @staticmethod
    def _load_editable_batch(connection: Any, batch_id: str) -> Any:
        batch = connection.execute(
            "SELECT * FROM review_batches WHERE id = ?",
            (batch_id,),
        ).fetchone()
        if batch is None:
            raise ValueError("复核批次不存在")
        if batch["status"] != "draft":
            raise ReviewBatchConflict("已发布的复核批次不能修改")
        return batch

    def update_batch_record(
        self,
        batch_id: str,
        review_id: str,
        expected_revision: int,
        actor_id: str,
        label_code: str | None,
        note: str,
        action: str | None = None,
        review_assessment: dict[str, str | None] | None = None,
        semantic_item_reviews: list[dict[str, Any]] | None = None,
        added_semantic_items: list[dict[str, Any]] | None = None,
        coverage_status: str | None = None,
    ) -> dict[str, Any]:
        clean_note = note.strip()
        if not clean_note:
            raise ValueError("请填写修改原因")
        resolved_action = action or ("modify" if label_code else "confirm")
        now = utc_now()
        try:
            with self.database.transaction(immediate=True) as connection:
                batch = self._load_editable_batch(connection, batch_id)
                row = connection.execute(
                    """
                    SELECT * FROM review_records
                    WHERE id = ? AND batch_id = ?
                    """,
                    (review_id, batch_id),
                ).fetchone()
                if row is None:
                    raise ValueError("批次复核记录不存在")
                before, after = self._update_batch_record_row(
                    connection,
                    row,
                    result_version_id=str(batch["base_result_version_id"]),
                    change=ReviewRecordChange(
                        expected_revision=expected_revision,
                        actor_id=actor_id,
                        action=resolved_action,
                        label_code=label_code,
                        note=clean_note,
                        now=now,
                        review_assessment=review_assessment,
                        semantic_item_reviews=semantic_item_reviews,
                        added_semantic_items=added_semantic_items,
                        coverage_status=coverage_status,
                    ),
                )
                connection.execute(
                    """
                    UPDATE review_batches
                    SET revision = revision + 1, updated_at = ? WHERE id = ?
                    """,
                    (now, batch_id),
                )
                event_data = {
                    "batch_id": batch_id,
                    "review_id": review_id,
                    "classification_key": row["classification_key"],
                    "action": resolved_action,
                    "reason": clean_note,
                }
                connection.execute(
                    """
                    INSERT INTO task_events(
                        task_id, event_type, stage, message, actor_id,
                        data_json, created_at
                    ) VALUES (?, 'review_batch_record_updated', '人工复核',
                              '复核批次草稿已修改', ?, ?, ?)
                    """,
                    (row["task_id"], actor_id, json_text(event_data), now),
                )
                self._insert_audit(
                    connection,
                    batch_id,
                    "update_record",
                    actor_id,
                    {"review_id": review_id, "classification": before},
                    {
                        "review_id": review_id,
                        "classification": after,
                        "action": resolved_action,
                        "reason": clean_note,
                    },
                    now,
                )
        except (ReviewBatchConflict, RevisionConflict) as exc:
            self._record_batch_conflict(batch_id, actor_id, str(exc))
            raise
        return self.get(review_id) or {}

    def update_batch_records(
        self,
        batch_id: str,
        records: builtin_list[dict[str, Any]],
        actor_id: str,
        action: str,
        label_code: str | None,
        note: str,
        review_assessment: dict[str, str | None] | None = None,
    ) -> dict[str, Any]:
        clean_note = note.strip()
        if not clean_note:
            raise ValueError("请填写处理原因")
        if not records:
            raise ValueError("请选择至少一条复核记录")
        review_ids = [str(record["id"]) for record in records]
        if len(review_ids) != len(set(review_ids)):
            raise ValueError("批量复核记录不能重复")
        now = utc_now()
        try:
            with self.database.transaction(immediate=True) as connection:
                batch = self._load_editable_batch(connection, batch_id)
                placeholders = ",".join("?" for _ in review_ids)
                rows = connection.execute(
                    f"""
                    SELECT * FROM review_records
                    WHERE batch_id = ? AND id IN ({placeholders})
                    """,
                    (batch_id, *review_ids),
                ).fetchall()
                rows_by_id = {str(row["id"]): row for row in rows}
                if len(rows_by_id) != len(review_ids):
                    raise ValueError("部分复核记录不存在")
                expected_by_id = {
                    str(record["id"]): int(record["expected_revision"])
                    for record in records
                }
                changes = []
                for review_id in review_ids:
                    row = rows_by_id[review_id]
                    before, after = self._update_batch_record_row(
                        connection,
                        row,
                        result_version_id=str(batch["base_result_version_id"]),
                        change=ReviewRecordChange(
                            expected_revision=expected_by_id[review_id],
                            actor_id=actor_id,
                            action=action,
                            label_code=label_code,
                            note=clean_note,
                            now=now,
                            review_assessment=review_assessment,
                        ),
                    )
                    changes.append(
                        {
                            "review_id": review_id,
                            "classification_key": row["classification_key"],
                            "before": before,
                            "after": after,
                        }
                    )
                connection.execute(
                    """
                    UPDATE review_batches
                    SET revision = revision + 1, updated_at = ? WHERE id = ?
                    """,
                    (now, batch_id),
                )
                event_data = {
                    "batch_id": batch_id,
                    "review_ids": review_ids,
                    "action": action,
                    "updated_count": len(changes),
                    "reason": clean_note,
                }
                connection.execute(
                    """
                    INSERT INTO task_events(
                        task_id, event_type, stage, message, actor_id,
                        data_json, created_at
                    ) VALUES (?, 'review_batch_records_updated', '人工复核',
                              '复核批次已批量处理', ?, ?, ?)
                    """,
                    (
                        rows[0]["task_id"],
                        actor_id,
                        json_text(event_data),
                        now,
                    ),
                )
                self._insert_audit(
                    connection,
                    batch_id,
                    "bulk_update_records",
                    actor_id,
                    {"review_ids": review_ids},
                    {
                        "review_ids": review_ids,
                        "action": action,
                        "updated_count": len(changes),
                        "reason": clean_note,
                    },
                    now,
                )
        except (ReviewBatchConflict, RevisionConflict) as exc:
            self._record_batch_conflict(batch_id, actor_id, str(exc))
            raise
        return {"updated_count": len(review_ids), "batch": self.get_batch(batch_id)}
