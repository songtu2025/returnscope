from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from web_backend.classification_standard_contracts import (
    ClassificationStandardConflict,
)
from web_backend.classification_standard_excel import preview_excel
from web_backend.classification_standards.draft_records import StandardDraftRecordsMixin
from web_backend.classification_standards.snapshot_encoding import snapshot_content_hash
from web_backend.common import add_audit, json_text
from web_backend.database import Database
from web_backend.security import utc_now


class ClassificationStandardDraftsMixin(StandardDraftRecordsMixin):
    _capability_from_snapshot: Callable[..., Any]
    _editable_content: Callable[..., dict[str, Any]]
    _snapshot_from_content: Callable[..., dict[str, Any]]
    _validate_candidate: Callable[..., dict[str, Any]]
    database: Database

    def import_draft_document(
        self,
        draft_id: str,
        expected_revision: int,
        document: dict[str, Any],
        change_reason: str,
        actor_id: str,
    ) -> dict[str, Any]:
        if (
            document.get("format") != "classification-standard"
            or document.get("format_version") != 1
        ):
            raise ValueError("不支持的分类标准导入格式")
        snapshot = document.get("snapshot")
        if not isinstance(snapshot, dict):
            raise ValueError("导入文件缺少分类标准快照")
        content_hash = snapshot_content_hash(snapshot)
        if content_hash != document.get("content_hash"):
            raise ValueError("导入文件内容哈希校验失败")
        try:
            self._capability_from_snapshot(snapshot)
            content = self._editable_content(snapshot)
        except (KeyError, TypeError, ValidationError, ValueError) as exc:
            raise ValueError("导入文件中的分类标准结构无效") from exc
        return self.update_draft(
            draft_id,
            expected_revision,
            content,
            change_reason,
            actor_id,
        )

    def update_draft(
        self,
        draft_id: str,
        expected_revision: int,
        content: dict[str, Any],
        change_reason: str,
        actor_id: str,
    ) -> dict[str, Any]:
        draft = self.get_draft(draft_id)
        if (
            content.get("import_sources")
            and content["import_sources"] != draft["snapshot"].get("import_sources", [])
            and not change_reason.strip()
        ):
            raise ValueError("导入标签框架必须填写修改原因")
        candidate = self._snapshot_from_content(draft["snapshot"], content)
        validation = self._validate_candidate(
            str(draft["standard_id"]),
            candidate,
            draft["base_snapshot"],
        )
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            updated = connection.execute(
                """
                UPDATE classification_standard_drafts
                SET snapshot_json = ?, validation_json = ?, change_reason = ?,
                    revision = revision + 1, updated_by = ?, updated_at = ?
                WHERE id = ? AND revision = ?
                """,
                (
                    json_text(candidate),
                    json_text(validation),
                    change_reason.strip(),
                    actor_id,
                    now,
                    draft_id,
                    expected_revision,
                ),
            )
            if updated.rowcount != 1:
                raise ClassificationStandardConflict("草稿已被修改，请刷新后重试")
        add_audit(
            self.database,
            "classification_standard",
            str(draft["standard_id"]),
            "update_draft",
            actor_id,
            before={"draft_id": draft_id, "revision": expected_revision},
            after={
                "draft_id": draft_id,
                "revision": expected_revision + 1,
                "change_reason": change_reason.strip(),
            },
        )
        return self.get_draft(draft_id)

    def preview_draft_excel(
        self,
        draft_id: str,
        data: bytes,
        sheet_name: str,
        columns: dict[str, Any],
    ) -> dict[str, Any]:
        draft = self.get_draft(draft_id)
        result = preview_excel(
            data,
            sheet_name,
            columns,
            self._editable_content(draft["snapshot"]),
            str(draft["standard_id"]),
        )
        if result["content"] is not None:
            candidate = self._snapshot_from_content(
                draft["snapshot"], result["content"]
            )
            validation = self._validate_candidate(
                str(draft["standard_id"]),
                candidate,
                draft["base_snapshot"],
            )
            result["validation"] = validation
        return result

    def validate_draft(
        self,
        draft_id: str,
        expected_revision: int,
        actor_id: str,
    ) -> dict[str, Any]:
        draft = self.get_draft(draft_id)
        if int(draft["revision"]) != expected_revision:
            raise ClassificationStandardConflict("草稿已被修改，请刷新后重试")
        validation = self._validate_candidate(
            str(draft["standard_id"]),
            draft["snapshot"],
            draft["base_snapshot"],
        )
        with self.database.transaction(immediate=True) as connection:
            updated = connection.execute(
                """
                UPDATE classification_standard_drafts
                SET validation_json = ?, updated_by = ?, updated_at = ?
                WHERE id = ? AND revision = ?
                """,
                (
                    json_text(validation),
                    actor_id,
                    utc_now(),
                    draft_id,
                    expected_revision,
                ),
            )
            if updated.rowcount != 1:
                raise ClassificationStandardConflict("草稿已被修改，请刷新后重试")
        add_audit(
            self.database,
            "classification_standard",
            str(draft["standard_id"]),
            "validate_draft",
            actor_id,
            after={"draft_id": draft_id, **validation},
        )
        return self.get_draft(draft_id)

    def discard_draft(
        self,
        draft_id: str,
        expected_revision: int,
        reason: str,
        actor_id: str,
    ) -> dict[str, Any]:
        if not reason.strip():
            raise ValueError("变更说明不能为空")
        draft = self.get_draft(draft_id)
        with self.database.transaction(immediate=True) as connection:
            current = connection.execute(
                "SELECT revision FROM classification_standard_drafts WHERE id = ?",
                (draft_id,),
            ).fetchone()
            if current is None or int(current["revision"]) != expected_revision:
                raise ClassificationStandardConflict("草稿已被修改，请刷新后重试")
            if draft["is_new"]:
                connection.execute(
                    "DELETE FROM classification_standard_validation_runs WHERE draft_id = ?",
                    (draft_id,),
                )
                connection.execute(
                    "DELETE FROM classification_standards WHERE id = ?",
                    (draft["standard_id"],),
                )
            else:
                connection.execute(
                    "DELETE FROM classification_standard_drafts WHERE id = ?",
                    (draft_id,),
                )
        add_audit(
            self.database,
            "classification_standard",
            str(draft["standard_id"]),
            "discard_draft",
            actor_id,
            before={"draft_id": draft_id, "revision": expected_revision},
            after={"reason": reason.strip()},
        )
        return {"id": draft_id, "standard_id": draft["standard_id"]}
