from __future__ import annotations

from typing import TYPE_CHECKING, Any

from return_semantics.label_statistics import top_problem_labels
from return_semantics.schemas import ValidatedClassification
from web_backend.classification_standard_service import ClassificationStandardService
from web_backend.common import add_audit, json_text, json_value, new_id
from web_backend.database import Database
from web_backend.review_contracts import RevisionConflict
from web_backend.reviews.legacy_result_rebuild import ReviewLegacyResultRebuildMixin
from web_backend.security import utc_now


class ReviewResolutionMixin(ReviewLegacyResultRebuildMixin):
    database: Database
    standard_service: ClassificationStandardService

    if TYPE_CHECKING:

        def get(self, review_id: str) -> dict[str, Any] | None: ...

        def _apply_resolution(
            self,
            classification: dict[str, Any],
            comment: str,
            label_code: str | None,
            result_version_id: str | None = None,
        ) -> dict[str, Any]: ...

        def _validate_reviewed_classification(
            self,
            classification: dict[str, Any],
        ) -> tuple[ValidatedClassification, dict[str, Any]]: ...

    def resolve(
        self,
        review_id: str,
        expected_revision: int,
        actor_id: str,
        label_code: str | None,
        note: str,
    ) -> dict[str, Any]:
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute(
                "SELECT * FROM review_records WHERE id = ?",
                (review_id,),
            ).fetchone()
            if row is None:
                raise ValueError("复核记录不存在")
            if row["batch_id"] is not None:
                raise ValueError("新复核记录请使用批次草稿接口修改")
            if int(row["revision"]) != expected_revision:
                raise RevisionConflict("记录已被其他用户修改，请刷新后重试")
            before = json_value(str(row["classification_json"]), {})
            after = self._apply_resolution(
                before,
                str(row["comment"]),
                label_code,
                str(row["base_result_version_id"] or "") or None,
            )
            next_revision = expected_revision + 1
            revision_id = new_id("revision")
            now = utc_now()
            connection.execute(
                """
                UPDATE review_records
                SET workflow_status = 'resolved', classification_json = ?,
                    revision = ?, updated_by = ?, updated_at = ?
                WHERE id = ? AND revision = ?
                """,
                (
                    json_text(after),
                    next_revision,
                    actor_id,
                    now,
                    review_id,
                    expected_revision,
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
                    revision_id,
                    review_id,
                    next_revision,
                    json_text(before),
                    json_text(after),
                    note.strip(),
                    actor_id,
                    now,
                ),
            )
            task_id = str(row["task_id"])
            previous_state = {
                "workflow_status": str(row["workflow_status"]),
                "updated_by": row["updated_by"],
                "updated_at": str(row["updated_at"]),
            }
        try:
            self._rebuild_result(task_id, actor_id)
        except Exception:
            with self.database.transaction(immediate=True) as connection:
                connection.execute(
                    """
                    UPDATE review_records
                    SET workflow_status = ?, classification_json = ?,
                        revision = ?, updated_by = ?, updated_at = ?
                    WHERE id = ? AND revision = ?
                    """,
                    (
                        previous_state["workflow_status"],
                        json_text(before),
                        expected_revision,
                        previous_state["updated_by"],
                        previous_state["updated_at"],
                        review_id,
                        next_revision,
                    ),
                )
                connection.execute(
                    "DELETE FROM review_revisions WHERE id = ?",
                    (revision_id,),
                )
            raise
        add_audit(
            self.database,
            "review",
            review_id,
            "resolve",
            actor_id,
            before=before,
            after=after,
        )
        return self.get(review_id) or {}

    _top_problem_labels = staticmethod(top_problem_labels)
