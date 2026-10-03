from __future__ import annotations

import json
from collections.abc import Callable
from copy import deepcopy
from typing import Any

from web_backend.classification_standard_contracts import (
    ClassificationStandardConflict,
    ClassificationStandardNotFound,
)
from web_backend.common import add_audit, json_text, json_value, new_id
from web_backend.database import Database
from web_backend.security import utc_now


class StandardDraftRecordsMixin:
    _diff_snapshots: Callable[..., dict[str, Any]]
    _editable_content: Callable[..., dict[str, Any]]
    _validate_candidate: Callable[..., dict[str, Any]]
    database: Database
    get: Callable[..., dict[str, Any]]
    get_version: Callable[..., dict[str, Any]]

    def get_draft(self, draft_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT draft.*, standard.standard_key,
                       standard.name AS standard_name,
                       standard.status AS standard_status,
                       standard.current_version_id,
                       base.version_no AS base_version_no,
                       base.snapshot_json AS base_snapshot_json
                FROM classification_standard_drafts draft
                JOIN classification_standards standard
                  ON standard.id = draft.standard_id
                JOIN classification_standard_versions base
                  ON base.id = draft.base_version_id
                WHERE draft.id = ?
                """,
                (draft_id,),
            ).fetchone()
        if row is None:
            raise ClassificationStandardNotFound("分类标准草稿不存在")
        return self._serialize_draft(dict(row))

    def draft_for_standard(self, standard_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT id FROM classification_standard_drafts WHERE standard_id = ?",
                (standard_id,),
            ).fetchone()
        return self.get_draft(str(row["id"])) if row else None

    def create_draft(self, standard_id: str, actor_id: str) -> dict[str, Any]:
        existing = self.draft_for_standard(standard_id)
        if existing is not None:
            return existing
        now = utc_now()
        draft_id = new_id("classification_standard_draft")
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute(
                """
                SELECT s.current_version_id, s.name, v.snapshot_json
                FROM classification_standards s
                JOIN classification_standard_versions v
                  ON v.id = s.current_version_id
                WHERE s.id = ? AND s.status = 'active'
                """,
                (standard_id,),
            ).fetchone()
            if row is None:
                raise ClassificationStandardNotFound("分类标准不存在或已停用")
            snapshot = json.loads(row["snapshot_json"])
            snapshot["name"] = row["name"]
            connection.execute(
                """
                INSERT INTO classification_standard_drafts(
                    id, standard_id, base_version_id, snapshot_json,
                    revision, validation_json, change_reason,
                    created_by, created_at, updated_by, updated_at
                ) VALUES (?, ?, ?, ?, 1, ?, '', ?, ?, ?, ?)
                """,
                (
                    draft_id,
                    standard_id,
                    row["current_version_id"],
                    json_text(snapshot),
                    json_text(
                        {
                            "blocking": ["草稿与当前已发布版本没有差异"],
                            "warnings": [],
                        }
                    ),
                    actor_id,
                    now,
                    actor_id,
                    now,
                ),
            )
            base_version_id = str(row["current_version_id"])
        add_audit(
            self.database,
            "classification_standard",
            standard_id,
            "create_draft",
            actor_id,
            after={"draft_id": draft_id, "base_version_id": base_version_id},
        )
        return self.get_draft(draft_id)

    def restore_version_as_draft(
        self,
        version_id: str,
        actor_id: str,
    ) -> dict[str, Any]:
        version = self.get_version(version_id)
        standard_id = str(version["standard_id"])
        standard = self.get(standard_id)
        if standard["status"] != "active":
            raise ClassificationStandardNotFound("分类标准不存在或已停用")
        if standard["standard_version_id"] == version_id:
            raise ValueError("当前版本无需恢复")
        if standard["draft_id"] is not None:
            raise ClassificationStandardConflict(
                "该分类标准已有草稿，请先发布或放弃现有草稿"
            )

        snapshot = deepcopy(version["snapshot"])
        validation = self._validate_candidate(
            standard_id,
            snapshot,
            standard["snapshot"],
        )
        draft_id = new_id("classification_standard_draft")
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            current = connection.execute(
                """
                SELECT status, current_version_id
                FROM classification_standards WHERE id = ?
                """,
                (standard_id,),
            ).fetchone()
            existing = connection.execute(
                """
                SELECT 1 FROM classification_standard_drafts
                WHERE standard_id = ?
                """,
                (standard_id,),
            ).fetchone()
            if (
                current is None
                or current["status"] != "active"
                or current["current_version_id"] != standard["standard_version_id"]
            ):
                raise ClassificationStandardConflict(
                    "当前启用版本已发生变化，请刷新后重试"
                )
            if existing is not None:
                raise ClassificationStandardConflict(
                    "该分类标准已有草稿，请先发布或放弃现有草稿"
                )
            connection.execute(
                """
                INSERT INTO classification_standard_drafts(
                    id, standard_id, base_version_id, snapshot_json,
                    revision, validation_json, change_reason,
                    created_by, created_at, updated_by, updated_at
                ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?)
                """,
                (
                    draft_id,
                    standard_id,
                    standard["standard_version_id"],
                    json_text(snapshot),
                    json_text(validation),
                    f"恢复 V{version['version_no']} 的内容",
                    actor_id,
                    now,
                    actor_id,
                    now,
                ),
            )
        add_audit(
            self.database,
            "classification_standard",
            standard_id,
            "restore_version_to_draft",
            actor_id,
            before={"version_id": standard["standard_version_id"]},
            after={
                "draft_id": draft_id,
                "source_version_id": version_id,
                "source_version_no": version["version_no"],
            },
        )
        return self.get_draft(draft_id)

    def _serialize_draft(self, value: dict[str, Any]) -> dict[str, Any]:
        snapshot = json.loads(value.pop("snapshot_json"))
        base_snapshot = json.loads(value.pop("base_snapshot_json"))
        validation = json_value(value.pop("validation_json"), {})
        with self.database.connect() as connection:
            impact = connection.execute(
                """
                SELECT
                    COUNT(DISTINCT segment.id) AS task_segment_count,
                    COUNT(DISTINCT result.id) AS result_count
                FROM classification_standard_versions version
                LEFT JOIN task_segments segment
                  ON segment.standard_version_id = version.id
                LEFT JOIN classification_results result
                  ON result.standard_version_id = version.id
                WHERE version.standard_id = ?
                """,
                (value["standard_id"],),
            ).fetchone()
        return {
            **value,
            "is_new": int(value["base_version_no"]) == 0,
            "snapshot": snapshot,
            "base_snapshot": base_snapshot,
            "content": self._editable_content(snapshot),
            "validation": validation,
            "diff": self._diff_snapshots(base_snapshot, snapshot),
            "impact": {
                "task_segment_count": int(impact["task_segment_count"] or 0),
                "result_count": int(impact["result_count"] or 0),
            },
        }
