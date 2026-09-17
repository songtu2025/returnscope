from __future__ import annotations

from builtins import list as builtin_list
from collections.abc import Callable
from copy import deepcopy
from typing import TYPE_CHECKING, Any

from return_semantics.schemas import ValidatedClassification
from web_backend.classification_standard_service import ClassificationStandardService
from web_backend.common import json_text, json_value, new_id
from web_backend.database import Database
from web_backend.review_contracts import ReviewBatchConflict, RevisionConflict
from web_backend.security import utc_now


class ReviewBatchEditingMixin:
    database: Database
    standard_service: ClassificationStandardService

    if TYPE_CHECKING:

        def get(self, review_id: str) -> dict[str, Any] | None: ...

        def get_batch(self, batch_id: str) -> dict[str, Any]: ...

        def _record_batch_conflict(
            self,
            batch_id: str,
            actor_id: str,
            message: str,
        ) -> None: ...

        def _validate_reviewed_classification(
            self,
            classification: dict[str, Any],
        ) -> tuple[ValidatedClassification, dict[str, Any] | None]: ...

        _insert_audit: Callable[
            [Any, str, str, str, dict[str, Any], dict[str, Any], str],
            None,
        ]

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
            units = connection.execute(
                """
                SELECT classification_key, comment, classification_json
                FROM classification_units
                WHERE result_version_id = ? AND quality_status != 'ready'
                ORDER BY classification_key
                """,
                (base_result_version_id,),
            ).fetchall()
            if not units:
                raise ValueError("该结果版本没有需要复核的分类单元")
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
    ) -> dict[str, Any]:
        clean_note = note.strip()
        if not clean_note:
            raise ValueError("请填写修改原因")
        resolved_action = action or ("modify" if label_code else "confirm")
        now = utc_now()
        try:
            with self.database.transaction(immediate=True) as connection:
                batch = connection.execute(
                    "SELECT * FROM review_batches WHERE id = ?",
                    (batch_id,),
                ).fetchone()
                if batch is None:
                    raise ValueError("复核批次不存在")
                if batch["status"] != "draft":
                    raise ReviewBatchConflict("已发布的复核批次不能修改")
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
                    expected_revision=expected_revision,
                    actor_id=actor_id,
                    action=resolved_action,
                    label_code=label_code,
                    note=clean_note,
                    now=now,
                    review_assessment=review_assessment,
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
                batch = connection.execute(
                    "SELECT * FROM review_batches WHERE id = ?",
                    (batch_id,),
                ).fetchone()
                if batch is None:
                    raise ValueError("复核批次不存在")
                if batch["status"] != "draft":
                    raise ReviewBatchConflict("已发布的复核批次不能修改")
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
                        expected_revision=expected_by_id[review_id],
                        actor_id=actor_id,
                        action=action,
                        label_code=label_code,
                        note=clean_note,
                        now=now,
                        review_assessment=review_assessment,
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

    def _update_batch_record_row(
        self,
        connection: Any,
        row: Any,
        *,
        result_version_id: str,
        expected_revision: int,
        actor_id: str,
        action: str,
        label_code: str | None,
        note: str,
        now: str,
        review_assessment: dict[str, str | None] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if action not in {"confirm", "modify", "exclude"}:
            raise ValueError("复核处理动作不合法")
        if action == "modify" and not str(label_code or "").strip():
            raise ValueError("修改分类时请选择目标标签")
        if int(row["revision"]) != expected_revision:
            raise RevisionConflict("记录已被其他用户修改，请刷新后重试")
        if row["workflow_status"] != "pending":
            raise ReviewBatchConflict("只能处理待处理的复核记录")
        before = json_value(str(row["classification_json"]), {})
        after = (
            before
            if action == "exclude"
            else self._apply_resolution(
                before,
                str(row["comment"]),
                label_code if action == "modify" else None,
                result_version_id,
            )
        )
        assessment = {
            key: value
            for key, value in (review_assessment or {}).items()
            if value is not None
        }
        if assessment:
            after = deepcopy(after)
            after["human_review_assessment"] = {
                **assessment,
                "assessed_by": actor_id,
                "assessed_at": now,
            }
        next_revision = expected_revision + 1
        workflow_status = "excluded" if action == "exclude" else "resolved"
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
                actor_id,
                now,
                row["id"],
                row["batch_id"],
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
                new_id("revision"),
                row["id"],
                next_revision,
                json_text(before),
                json_text(after),
                note,
                actor_id,
                now,
            ),
        )
        return before, after

    def _apply_resolution(
        self,
        classification: dict[str, Any],
        comment: str,
        label_code: str | None,
        result_version_id: str | None = None,
    ) -> dict[str, Any]:
        taxonomy = (
            self.standard_service.taxonomy_config_for_result_version(result_version_id)
            if result_version_id
            else self.standard_service.combined_taxonomy()
        )
        label_codes = {label.code for label in taxonomy.labels}
        selected = (label_code or "").strip()
        updated = dict(classification)
        if selected:
            if selected not in label_codes:
                raise ValueError("选择的语义标签不存在")
            units = [dict(item) for item in updated.get("semantic_units", [])]
            if units:
                previous_label = str(units[0].get("label_code", ""))
                units[0]["label_code"] = selected
            else:
                previous_label = ""
                units = [
                    {
                        "subject": "PRODUCT",
                        "label_code": selected,
                        "opinion": comment,
                        "sentiment": "NEGATIVE",
                        "assertion": "AFFIRMED",
                        "part": "UNSPECIFIED",
                        "evidence": comment,
                        "implicit": False,
                        "claim_relation": "NONE",
                        "claim_id": None,
                    }
                ]
            updated["semantic_units"] = units
            updated["unknown_semantics"] = []
            problem_codes, positive_codes, negative_codes = self._project_review_labels(
                units,
                list(updated.get("problem_label_codes", [])),
                previous_label,
                selected,
            )
            updated["problem_label_codes"] = problem_codes
            updated["positive_label_codes"] = positive_codes
            updated["primary_label_codes"] = [selected]
            summary = dict(updated.get("comment_summary", {}))
            summary["positive_label_codes"] = positive_codes
            summary["negative_label_codes"] = negative_codes
            updated["comment_summary"] = summary
        if not updated.get("semantic_units") and updated.get("unknown_semantics"):
            raise ValueError("未知语义必须选择一个标签后才能完成复核")
        updated["status"] = "MANUAL_RESOLVED"
        updated["review_reasons"] = []
        self._validate_reviewed_classification(updated)
        return updated

    @staticmethod
    def _project_review_labels(
        units: list[dict[str, Any]],
        previous_problem_codes: list[str],
        previous_label: str,
        selected: str,
    ) -> tuple[list[str], list[str], list[str]]:
        neutral_problem_codes = set(previous_problem_codes)
        if previous_label in neutral_problem_codes:
            neutral_problem_codes.remove(previous_label)
            neutral_problem_codes.add(selected)
        problem_codes: list[str] = []
        positive_codes: list[str] = []
        negative_codes: list[str] = []
        for unit in units:
            code = str(unit.get("label_code", ""))
            sentiment = str(unit.get("sentiment", ""))
            if sentiment == "POSITIVE":
                positive_codes.append(code)
            elif sentiment == "NEGATIVE":
                problem_codes.append(code)
                negative_codes.append(code)
            elif code in neutral_problem_codes:
                problem_codes.append(code)
        return (
            list(dict.fromkeys(problem_codes)),
            list(dict.fromkeys(positive_codes)),
            list(dict.fromkeys(negative_codes)),
        )
