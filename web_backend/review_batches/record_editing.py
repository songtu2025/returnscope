from __future__ import annotations

from typing import Any

from web_backend.common import json_text, json_value, new_id
from web_backend.review_batches.classification import _ReviewClassification
from web_backend.review_batches.semantic_validation import _ReviewSemanticValidation
from web_backend.review_contracts import (
    ReviewBatchConflict,
    ReviewRecordChange,
    RevisionConflict,
)


class _ReviewRecordEditing(_ReviewClassification, _ReviewSemanticValidation):
    def _update_batch_record_row(
        self,
        connection: Any,
        row: Any,
        *,
        result_version_id: str,
        change: ReviewRecordChange,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if change.action not in {"confirm", "modify", "exclude"}:
            raise ValueError("复核处理动作不合法")
        if change.action == "modify" and not str(change.label_code or "").strip():
            raise ValueError("修改分类时请选择目标标签")
        if int(row["revision"]) != change.expected_revision:
            raise RevisionConflict("记录已被其他用户修改，请刷新后重试")
        if row["workflow_status"] != "pending":
            raise ReviewBatchConflict("只能处理待处理的复核记录")
        before = json_value(str(row["classification_json"]), {})
        if change.coverage_status not in {None, "complete", "has_omission"}:
            raise ValueError("语义覆盖状态不合法")
        # 空列表仍表示显式核验，只有三个字段全为 None 才跳过详情校验。
        if any(
            value is not None
            for value in (
                change.semantic_item_reviews,
                change.added_semantic_items,
                change.coverage_status,
            )
        ):
            self._validate_semantic_review_details(
                result_version_id=result_version_id,
                classification=before,
                comment=str(row["comment"]),
                semantic_item_reviews=change.semantic_item_reviews,
                added_semantic_items=change.added_semantic_items,
            )
        after = self._apply_human_review_details(
            before,
            actor_id=change.actor_id,
            assessed_at=change.now,
            review_assessment=change.review_assessment,
            semantic_item_reviews=change.semantic_item_reviews,
            added_semantic_items=change.added_semantic_items,
            coverage_status=change.coverage_status,
        )
        if change.action != "exclude":
            after = self._resolve_batch_classification(
                after,
                str(row["comment"]),
                result_version_id,
                change.label_code if change.action == "modify" else None,
            )
        next_revision = change.expected_revision + 1
        workflow_status = "excluded" if change.action == "exclude" else "resolved"
        connection.execute(
            """
            UPDATE review_records
            SET workflow_status = ?, classification_json = ?,
                revision = ?, updated_by = ?, updated_at = ?
            WHERE id = ? AND batch_id = ? AND revision = ?
            """,
            (
                workflow_status,
                json_text(after),
                next_revision,
                change.actor_id,
                change.now,
                row["id"],
                row["batch_id"],
                change.expected_revision,
            ),
        )
        connection.execute(
            """
            INSERT INTO review_revisions(
                id, review_record_id, revision, before_json, after_json,
                note, actor_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id("revision"),
                row["id"],
                next_revision,
                json_text(before),
                json_text(after),
                change.note,
                change.actor_id,
                change.now,
            ),
        )
        return before, after
