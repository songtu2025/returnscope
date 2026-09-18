from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Callable

from return_semantics.prompt import validation_contract_matches
from web_backend.classification_standard_contracts import (
    ClassificationStandardConflict,
    ClassificationStandardValidationError,
)
from web_backend.classification_validation_quality import publication_quality_gate
from web_backend.common import add_audit, new_id
from web_backend.database import Database
from web_backend.security import utc_now


class ClassificationStandardPublicationMixin:
    database: Database
    _validate_candidate: Callable[..., dict[str, Any]]
    get: Callable[..., dict[str, Any]]
    get_draft: Callable[..., dict[str, Any]]

    def publish_draft(
        self,
        draft_id: str,
        expected_revision: int,
        reason: str,
        actor_id: str,
        validation_run_id: str | None = None,
    ) -> dict[str, Any]:
        if not reason.strip():
            raise ValueError("变更说明不能为空")
        draft = self.get_draft(draft_id)
        validation = self._validate_candidate(
            str(draft["standard_id"]),
            draft["snapshot"],
            draft["base_snapshot"],
        )
        if validation["blocking"]:
            raise ClassificationStandardValidationError(validation)
        validation_evidence = self._validation_evidence(
            draft,
            expected_revision,
            validation_run_id,
        )
        now = utc_now()
        standard_id = str(draft["standard_id"])
        with self.database.transaction(immediate=True) as connection:
            current = connection.execute(
                "SELECT current_version_id FROM classification_standards WHERE id = ?",
                (standard_id,),
            ).fetchone()
            current_draft = connection.execute(
                """
                SELECT revision, base_version_id
                FROM classification_standard_drafts WHERE id = ?
                """,
                (draft_id,),
            ).fetchone()
            if current is None or current_draft is None:
                raise ClassificationStandardConflict("分类标准或草稿已发生变化")
            if int(current_draft["revision"]) != expected_revision:
                raise ClassificationStandardConflict("草稿已被修改，请刷新后重试")
            if current["current_version_id"] != current_draft["base_version_id"]:
                raise ClassificationStandardConflict(
                    "已发布版本发生变化，请重新创建草稿"
                )
            version_no = int(
                connection.execute(
                    """
                    SELECT COALESCE(MAX(version_no), 0) + 1
                    FROM classification_standard_versions WHERE standard_id = ?
                    """,
                    (standard_id,),
                ).fetchone()[0]
            )
            snapshot = deepcopy(draft["snapshot"])
            taxonomy_version = f"{draft['standard_key']}-taxonomy-v{version_no}"
            snapshot["taxonomy"]["version"] = taxonomy_version
            encoded = json.dumps(
                snapshot,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            content_hash = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
            version_id = new_id("classification_standard_version")
            connection.execute(
                """
                INSERT INTO classification_standard_versions(
                    id, standard_id, version_no, version_key,
                    logic_version, taxonomy_version, model_policy_version,
                    snapshot_json, content_hash, version_reason, status,
                    created_at, published_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'published', ?, ?)
                """,
                (
                    version_id,
                    standard_id,
                    version_no,
                    taxonomy_version,
                    snapshot["logic_version"],
                    taxonomy_version,
                    snapshot["model_policy"]["version"],
                    encoded,
                    content_hash,
                    reason.strip(),
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                UPDATE classification_standards
                SET name = ?, status = 'active', current_version_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (snapshot["name"], version_id, now, standard_id),
            )
            connection.execute(
                "DELETE FROM classification_standard_drafts WHERE id = ?",
                (draft_id,),
            )
            if validation_evidence is not None:
                connection.execute(
                    """
                    UPDATE classification_standard_validation_runs
                    SET published_version_id = ? WHERE id = ?
                    """,
                    (version_id, validation_evidence["id"]),
                )
        add_audit(
            self.database,
            "classification_standard",
            standard_id,
            "publish",
            actor_id,
            before={"version_id": draft["base_version_id"]},
            after={
                "version_id": version_id,
                "version": version_no,
                "reason": reason,
                "publication_mode": (
                    "validated" if validation_evidence is not None else "direct"
                ),
                "validation_run_id": (
                    validation_evidence["id"]
                    if validation_evidence is not None
                    else None
                ),
                "validation_quality_passed": (
                    validation_evidence["quality_gate_passed"]
                    if validation_evidence is not None
                    else None
                ),
            },
        )
        return self.get(standard_id)

    def _validation_evidence(
        self,
        draft: dict[str, Any],
        expected_revision: int,
        validation_run_id: str | None,
    ) -> dict[str, Any] | None:
        if validation_run_id is None:
            return None
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT id, draft_id, draft_revision, status, error_count,
                       source_json, result_json, summary_json
                FROM classification_standard_validation_runs
                WHERE id = ?
                """,
                (validation_run_id,),
            ).fetchone()
        if row is None:
            raise ClassificationStandardValidationError(
                {
                    "blocking": ["所选测试记录不存在，请刷新后重试"],
                    "warnings": [],
                }
            )
        source = json.loads(row["source_json"] or "{}")
        if (
            str(row["draft_id"]) != str(draft["id"])
            or int(row["draft_revision"]) != expected_revision
            or source.get("comparison_type", "standard_version") != "standard_version"
            or not validation_contract_matches(draft["snapshot"], source)
        ):
            raise ClassificationStandardValidationError(
                {
                    "blocking": [
                        "所选测试记录不属于当前草稿修订，请重新测试或直接发布"
                    ],
                    "warnings": [],
                }
            )
        if row["status"] != "completed" or int(row["error_count"]) > 0:
            raise ClassificationStandardValidationError(
                {
                    "blocking": ["所选测试尚未成功完成，请重新测试或直接发布"],
                    "warnings": [],
                }
            )
        gate = publication_quality_gate(
            draft["snapshot"],
            source,
            json.loads(row["result_json"] or "[]"),
            json.loads(row["summary_json"] or "{}"),
        )
        return {
            "id": str(row["id"]),
            "quality_gate_passed": bool(gate["passed"]),
        }
