from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from pydantic import ValidationError

from return_semantics.capabilities import (
    CapabilityRegistry,
    CategoryCapability,
    CategoryVariant,
    ModelPolicy,
)
from return_semantics.prompt import validation_contract_matches
from return_semantics.schemas import TaxonomyConfig
from return_semantics.taxonomy import load_taxonomy_alignment
from web_backend.common import add_audit, json_text, json_value, new_id
from web_backend.database import Database
from web_backend.security import utc_now
from web_backend.settings import PROJECT_ROOT

CLASSIFICATION_STANDARD_SEED_MIGRATION = "20260824_01_seed_classification_standards"
CLASSIFICATION_STANDARD_RULES_MIGRATION = "20260825_01_embed_taxonomy_validation_rules"


class ClassificationStandardNotFound(ValueError):
    pass


class ClassificationStandardConflict(ValueError):
    pass


class ClassificationStandardValidationError(ValueError):
    def __init__(self, validation: dict[str, list[str]]) -> None:
        self.validation = validation
        super().__init__("分类标准未通过发布检查")


class ClassificationStandardService:
    def __init__(self, database: Database) -> None:
        self.database = database
        if self._tables_exist():
            self.ensure_bootstrapped()

    def _tables_exist(self) -> bool:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT 1 FROM sqlite_master
                WHERE type = 'table' AND name = 'classification_standards'
                """
            ).fetchone()
        return row is not None

    def ensure_bootstrapped(self) -> None:
        with self.database.transaction(immediate=True) as connection:
            migration = connection.execute(
                "SELECT 1 FROM app_migrations WHERE migration_id = ?",
                (CLASSIFICATION_STANDARD_SEED_MIGRATION,),
            ).fetchone()
            if migration is None:
                count = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM classification_standards"
                    ).fetchone()[0]
                )
                status = "baselined"
                if count == 0:
                    self._import_seed_config(connection)
                    status = "applied"
                connection.execute(
                    """
                    INSERT INTO app_migrations(
                        migration_id, checksum, status, applied_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        CLASSIFICATION_STANDARD_SEED_MIGRATION,
                        self._classification_standard_checksum(connection),
                        status,
                        utc_now(),
                    ),
                )
            self._migrate_taxonomy_validation_rules(connection)
            self._backfill_bindings(connection)

    @staticmethod
    def _classification_standard_checksum(connection: Any) -> str:
        rows = connection.execute(
            """
            SELECT s.standard_key, v.content_hash
            FROM classification_standards s
            JOIN classification_standard_versions v
              ON v.id = s.current_version_id
            ORDER BY s.standard_key
            """
        ).fetchall()
        source = "\x1f".join(
            f"{row['standard_key']}:{row['content_hash']}" for row in rows
        )
        return hashlib.sha256(source.encode("utf-8")).hexdigest()

    def active_registry(self) -> CapabilityRegistry:
        if not self._tables_exist():
            raise RuntimeError("分类标准数据表尚未初始化")
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT v.id AS standard_version_id, v.snapshot_json
                FROM classification_standards s
                JOIN classification_standard_versions v
                  ON v.id = s.current_version_id
                WHERE s.status = 'active' AND v.status = 'published'
                ORDER BY s.standard_key
                """
            ).fetchall()
        capabilities = tuple(
            self._capability_from_snapshot(json.loads(row["snapshot_json"]))
            for row in rows
        )
        version_source = "\x1f".join(str(row["standard_version_id"]) for row in rows)
        registry_version = hashlib.sha256(version_source.encode("utf-8")).hexdigest()[
            :16
        ]
        return CapabilityRegistry(
            version=f"classification-standards-{registry_version}",
            capabilities=capabilities,
        )

    def capability_for_version(self, version_id: str) -> CategoryCapability:
        version = self.get_version(version_id)
        return self._capability_from_snapshot(version["snapshot"])

    def registry_for_versions(self, version_ids: list[str]) -> CapabilityRegistry:
        unique_ids = list(dict.fromkeys(value for value in version_ids if value))
        capabilities = tuple(
            self.capability_for_version(version_id) for version_id in unique_ids
        )
        version_source = "\x1f".join(unique_ids)
        registry_hash = hashlib.sha256(version_source.encode("utf-8")).hexdigest()[:16]
        return CapabilityRegistry(
            version=f"classification-standard-snapshot-{registry_hash}",
            capabilities=capabilities,
        )

    def taxonomy_for_version(self, version_id: str) -> TaxonomyConfig:
        taxonomy = self.capability_for_version(version_id).taxonomy
        if taxonomy is None:
            raise ClassificationStandardNotFound("分类标准版本缺少标签体系")
        return taxonomy

    def current_version_by_agent(self) -> dict[str, dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT s.id AS standard_id, s.standard_key, s.name,
                       v.id AS standard_version_id, v.version_no,
                       v.version_key, v.logic_version, v.taxonomy_version,
                       v.model_policy_version
                FROM classification_standards s
                JOIN classification_standard_versions v
                  ON v.id = s.current_version_id
                WHERE s.status = 'active' AND v.status = 'published'
                """
            ).fetchall()
        return {str(row["standard_key"]): dict(row) for row in rows}

    def list(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT s.*, v.version_no, v.version_key, v.logic_version,
                       v.taxonomy_version, v.model_policy_version,
                       v.snapshot_json, v.published_at,
                       draft.id AS draft_id, draft.revision AS draft_revision,
                       draft.updated_at AS draft_updated_at,
                       (SELECT COUNT(*) FROM task_segments segment
                        WHERE segment.standard_version_id IN (
                            SELECT version.id
                            FROM classification_standard_versions version
                            WHERE version.standard_id = s.id
                        )) AS task_segment_count,
                       (SELECT COUNT(*) FROM classification_results result
                        WHERE result.standard_version_id IN (
                            SELECT version.id
                            FROM classification_standard_versions version
                            WHERE version.standard_id = s.id
                        )) AS result_count,
                       (SELECT COUNT(*)
                        FROM classification_standard_versions version
                        WHERE version.standard_id = s.id
                          AND version.status = 'published') AS published_version_count
                FROM classification_standards s
                JOIN classification_standard_versions v
                  ON v.id = s.current_version_id
                LEFT JOIN classification_standard_drafts draft
                  ON draft.standard_id = s.id
                ORDER BY s.name COLLATE NOCASE, s.standard_key
                """
            ).fetchall()
        return [self._serialize_standard(dict(row)) for row in rows]

    def get(self, standard_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT s.*, v.version_no, v.version_key, v.logic_version,
                       v.taxonomy_version, v.model_policy_version,
                       v.snapshot_json, v.published_at,
                       draft.id AS draft_id, draft.revision AS draft_revision,
                       draft.updated_at AS draft_updated_at,
                       (SELECT COUNT(*) FROM task_segments segment
                        WHERE segment.standard_version_id IN (
                            SELECT version.id
                            FROM classification_standard_versions version
                            WHERE version.standard_id = s.id
                        )) AS task_segment_count,
                       (SELECT COUNT(*) FROM classification_results result
                        WHERE result.standard_version_id IN (
                            SELECT version.id
                            FROM classification_standard_versions version
                            WHERE version.standard_id = s.id
                        )) AS result_count,
                       (SELECT COUNT(*)
                        FROM classification_standard_versions version
                        WHERE version.standard_id = s.id
                          AND version.status = 'published') AS published_version_count
                FROM classification_standards s
                JOIN classification_standard_versions v
                  ON v.id = s.current_version_id
                LEFT JOIN classification_standard_drafts draft
                  ON draft.standard_id = s.id
                WHERE s.id = ?
                """,
                (standard_id,),
            ).fetchone()
        if row is None:
            raise ClassificationStandardNotFound("分类标准不存在")
        return self._serialize_standard(dict(row), include_snapshot=True)

    def versions(self, standard_id: str) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT v.*,
                       (SELECT COUNT(*) FROM task_segments segment
                        WHERE segment.standard_version_id = v.id) AS task_segment_count
                FROM classification_standard_versions v
                WHERE v.standard_id = ? AND v.status = 'published'
                ORDER BY v.version_no DESC
                """,
                (standard_id,),
            ).fetchall()
        if not rows:
            with self.database.connect() as connection:
                exists = connection.execute(
                    "SELECT 1 FROM classification_standards WHERE id = ?",
                    (standard_id,),
                ).fetchone()
            if exists is None:
                raise ClassificationStandardNotFound("分类标准不存在")
        return [self._serialize_version(dict(row)) for row in rows]

    def get_version(self, version_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT v.*, s.standard_key, s.name AS standard_name
                FROM classification_standard_versions v
                JOIN classification_standards s ON s.id = v.standard_id
                WHERE v.id = ?
                """,
                (version_id,),
            ).fetchone()
        if row is None:
            raise ClassificationStandardNotFound("分类标准版本不存在")
        return self._serialize_version(dict(row), include_snapshot=True)

    def current_version_for_standard(self, standard_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT v.id
                FROM classification_standards s
                JOIN classification_standard_versions v
                  ON v.id = s.current_version_id
                WHERE s.id = ?
                  AND s.status = 'active'
                  AND v.status = 'published'
                """,
                (standard_id,),
            ).fetchone()
        if row is None:
            raise ClassificationStandardNotFound("分类标准不存在、未启用或尚未发布")
        return self.get_version(str(row["id"]))

    def export_version_document(self, version_id: str) -> dict[str, Any]:
        version = self.get_version(version_id)
        if version["status"] != "published":
            raise ValueError("只能导出已发布的分类标准版本")
        return {
            "format": "classification-standard",
            "format_version": 1,
            "content_hash": version["content_hash"],
            "source": {
                "standard_id": version["standard_id"],
                "standard_key": version["standard_key"],
                "standard_name": version["standard_name"],
                "version_id": version["id"],
                "version_no": version["version_no"],
            },
            "snapshot": version["snapshot"],
        }

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
        encoded = json.dumps(
            snapshot,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        content_hash = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
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

    def create_standard(
        self,
        *,
        name: str,
        product_context: str,
        category_a: str,
        category_b: str,
        actor_id: str,
    ) -> dict[str, Any]:
        if not all(
            value.strip() for value in (name, product_context, category_a, category_b)
        ):
            raise ValueError("标准名称、适用说明和品类不能为空")
        standard_id = new_id("classification_standard")
        standard_key = f"custom_{standard_id.rsplit('_', 1)[-1]}"
        version_id = new_id("classification_standard_version")
        draft_id = new_id("classification_standard_draft")
        now = utc_now()
        agent_family = f"{name.strip().removesuffix('分类标准')}智能体"
        snapshot = {
            "standard_key": standard_key,
            "name": name.strip(),
            "agent_family": agent_family,
            "logic_version": f"{standard_key}-semantic-v1",
            "model_policy": {
                "version": f"{standard_key}-model-policy-v1",
                "first_pass_role": "primary",
                "review_role": "primary",
            },
            "variants": [
                {
                    "category_a": category_a.strip(),
                    "category_b": category_b.strip(),
                    "attributes": {},
                }
            ],
            "taxonomy": {
                "version": f"{standard_key}-taxonomy-draft",
                "agent_family": agent_family,
                "product_context": product_context.strip(),
                "instructions": [],
                "allowed_parts": ["UNSPECIFIED"],
                "validation_rules": {
                    "allowed_groups": load_taxonomy_alignment()["groups"],
                    "neutral_reason_labels": [],
                    "conflict_scope": "evidence",
                },
                "labels": [],
            },
        }
        encoded = json.dumps(
            snapshot,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        content_hash = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        validation = self._validate_candidate(standard_id, snapshot, snapshot)
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                INSERT INTO classification_standards(
                    id, standard_key, name, status, current_version_id,
                    created_at, updated_at
                ) VALUES (?, ?, ?, 'inactive', NULL, ?, ?)
                """,
                (standard_id, standard_key, name.strip(), now, now),
            )
            connection.execute(
                """
                INSERT INTO classification_standard_versions(
                    id, standard_id, version_no, version_key,
                    logic_version, taxonomy_version, model_policy_version,
                    snapshot_json, content_hash, version_reason, status,
                    created_at, published_at
                ) VALUES (?, ?, 0, ?, ?, ?, ?, ?, ?,
                          '未发布草稿基线', 'inactive', ?, ?)
                """,
                (
                    version_id,
                    standard_id,
                    f"{standard_key}-draft-base",
                    snapshot["logic_version"],
                    snapshot["taxonomy"]["version"],
                    snapshot["model_policy"]["version"],
                    encoded,
                    content_hash,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                UPDATE classification_standards
                SET current_version_id = ? WHERE id = ?
                """,
                (version_id, standard_id),
            )
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
                    version_id,
                    encoded,
                    json_text(validation),
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
            "create",
            actor_id,
            after={
                "draft_id": draft_id,
                "name": name.strip(),
                "category_a": category_a.strip(),
                "category_b": category_b.strip(),
            },
        )
        return self.get_draft(draft_id)

    def create_draft(self, standard_id: str, actor_id: str) -> dict[str, Any]:
        existing = self.draft_for_standard(standard_id)
        if existing is not None:
            return existing
        now = utc_now()
        draft_id = new_id("classification_standard_draft")
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute(
                """
                SELECT s.current_version_id, v.snapshot_json
                FROM classification_standards s
                JOIN classification_standard_versions v
                  ON v.id = s.current_version_id
                WHERE s.id = ? AND s.status = 'active'
                """,
                (standard_id,),
            ).fetchone()
            if row is None:
                raise ClassificationStandardNotFound("分类标准不存在或已停用")
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
                    row["snapshot_json"],
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

    def update_draft(
        self,
        draft_id: str,
        expected_revision: int,
        content: dict[str, Any],
        change_reason: str,
        actor_id: str,
    ) -> dict[str, Any]:
        draft = self.get_draft(draft_id)
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

    def publish_draft(
        self,
        draft_id: str,
        expected_revision: int,
        reason: str,
        actor_id: str,
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
        with self.database.connect() as connection:
            sample_validation = connection.execute(
                """
                SELECT id, source_json FROM classification_standard_validation_runs
                WHERE draft_id = ? AND draft_revision = ?
                  AND status = 'completed' AND error_count = 0
                  AND approved_at IS NOT NULL
                ORDER BY completed_at DESC, id DESC
                LIMIT 1
                """,
                (draft_id, expected_revision),
            ).fetchone()
        sample_validation_id = (
            str(sample_validation["id"])
            if sample_validation is not None
            and validation_contract_matches(
                draft["snapshot"], json.loads(sample_validation["source_json"])
            )
            else None
        )
        if sample_validation_id is None:
            raise ClassificationStandardValidationError(
                {
                    "blocking": ["请先完成并人工确认当前草稿修订的样本验证"],
                    "warnings": validation["warnings"],
                }
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
            if sample_validation_id is not None:
                connection.execute(
                    """
                    UPDATE classification_standard_validation_runs
                    SET published_version_id = ? WHERE id = ?
                    """,
                    (version_id, sample_validation_id),
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
                "sample_validation_id": sample_validation_id,
            },
        )
        return self.get(standard_id)

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

    def delete_standard(self, standard_id: str, actor_id: str) -> dict[str, Any]:
        with self.database.transaction(immediate=True) as connection:
            standard = connection.execute(
                """
                SELECT s.id, s.name, s.status,
                       (SELECT COUNT(*)
                        FROM classification_standard_versions version
                        WHERE version.standard_id = s.id
                          AND version.status = 'published') AS published_version_count,
                       (SELECT COUNT(*) FROM task_segments segment
                        WHERE segment.standard_version_id IN (
                            SELECT version.id
                            FROM classification_standard_versions version
                            WHERE version.standard_id = s.id
                        )) AS task_segment_count,
                       (SELECT COUNT(*) FROM classification_results result
                        WHERE result.standard_version_id IN (
                            SELECT version.id
                            FROM classification_standard_versions version
                            WHERE version.standard_id = s.id
                        )) AS result_count
                FROM classification_standards s
                WHERE s.id = ?
                """,
                (standard_id,),
            ).fetchone()
            if standard is None:
                raise ClassificationStandardNotFound("分类标准不存在")

            published_count = int(standard["published_version_count"] or 0)
            task_count = int(standard["task_segment_count"] or 0)
            result_count = int(standard["result_count"] or 0)
            hard_delete = published_count == 0 and task_count == 0 and result_count == 0
            if hard_delete:
                connection.execute(
                    "DELETE FROM classification_standard_validation_runs WHERE standard_id = ?",
                    (standard_id,),
                )
                connection.execute(
                    "DELETE FROM classification_standards WHERE id = ?",
                    (standard_id,),
                )
                mode = "deleted"
            else:
                draft = connection.execute(
                    "SELECT id FROM classification_standard_drafts WHERE standard_id = ?",
                    (standard_id,),
                ).fetchone()
                if draft is not None:
                    connection.execute(
                        "DELETE FROM classification_standard_validation_runs WHERE draft_id = ?",
                        (draft["id"],),
                    )
                    connection.execute(
                        "DELETE FROM classification_standard_drafts WHERE id = ?",
                        (draft["id"],),
                    )
                connection.execute(
                    """
                    UPDATE classification_standards
                    SET status = 'inactive', updated_at = ?
                    WHERE id = ?
                    """,
                    (utc_now(), standard_id),
                )
                mode = "deactivated"

        add_audit(
            self.database,
            "classification_standard",
            standard_id,
            mode,
            actor_id,
            before={
                "name": standard["name"],
                "status": standard["status"],
                "task_segment_count": task_count,
                "result_count": result_count,
            },
            after={"status": "deleted" if hard_delete else "inactive"},
        )
        return {
            "id": standard_id,
            "mode": mode,
            "status": "deleted" if hard_delete else "inactive",
        }

    def taxonomy_for_result_version(self, result_version_id: str) -> dict[str, Any]:
        taxonomy, version = self._taxonomy_context_for_result(result_version_id)
        return {
            **taxonomy.model_dump(mode="json"),
            "standard_id": version["standard_id"],
            "standard_version_id": version["id"],
            "standard_name": version["standard_name"],
            "standard_version": version["version_no"],
        }

    def taxonomy_config_for_result_version(
        self,
        result_version_id: str,
    ) -> TaxonomyConfig:
        taxonomy, _version = self._taxonomy_context_for_result(result_version_id)
        return taxonomy

    def _taxonomy_context_for_result(
        self,
        result_version_id: str,
    ) -> tuple[TaxonomyConfig, dict[str, Any]]:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT r.standard_version_id
                FROM classification_result_versions v
                JOIN classification_results r ON r.id = v.result_id
                WHERE v.id = ?
                """,
                (result_version_id,),
            ).fetchone()
        if row is None:
            raise ClassificationStandardNotFound("分类结果版本不存在")
        version_id = str(row["standard_version_id"] or "")
        if not version_id:
            return self.combined_taxonomy(), {
                "standard_id": None,
                "id": None,
                "standard_name": "历史合并标签体系",
                "version_no": None,
            }
        version = self.get_version(version_id)
        taxonomy = TaxonomyConfig.model_validate(version["snapshot"]["taxonomy"])
        return taxonomy, version

    def combined_taxonomy(self) -> TaxonomyConfig:
        return self.active_registry().combined_taxonomy()

    def _snapshot_from_content(
        self,
        source: dict[str, Any],
        content: dict[str, Any],
    ) -> dict[str, Any]:
        snapshot = deepcopy(source)
        existing_labels = {
            str(label["code"]): label for label in source["taxonomy"]["labels"]
        }
        snapshot["name"] = str(content["name"]).strip()
        snapshot["variants"] = [
            {
                "category_a": str(item["category_a"]).strip(),
                "category_b": str(item["category_b"]).strip(),
                "attributes": {
                    str(key).strip(): str(value).strip()
                    for key, value in item.get("attributes", {}).items()
                    if str(key).strip()
                },
            }
            for item in content["variants"]
        ]
        taxonomy = snapshot["taxonomy"]
        taxonomy["recognition_profile"] = content.get(
            "recognition_profile", taxonomy.get("recognition_profile", "legacy_v3")
        )
        taxonomy["product_context"] = str(content["product_context"]).strip()
        taxonomy["instructions"] = [
            str(value).strip()
            for value in content["instructions"]
            if str(value).strip()
        ]
        taxonomy["allowed_parts"] = [
            str(value).strip().upper()
            for value in content["allowed_parts"]
            if str(value).strip()
        ]
        taxonomy["validation_rules"] = deepcopy(
            content.get(
                "validation_rules",
                taxonomy.get("validation_rules", {}),
            )
        )
        taxonomy["labels"] = []
        for item in content["labels"]:
            code = str(item["code"]).strip().upper()
            previous = existing_labels.get(code, {})
            taxonomy["labels"].append(
                {
                    "code": code,
                    "name": str(item["name"]).strip(),
                    "group": str(item["group"]).strip(),
                    "description": str(item["description"]).strip(),
                    "exclusions": list(
                        item.get("exclusions", previous.get("exclusions", []))
                    ),
                    "examples": deepcopy(
                        item.get("examples", previous.get("examples", []))
                    ),
                    "keywords": [
                        str(value).strip()
                        for value in item.get("keywords", previous.get("keywords", []))
                        if str(value).strip()
                    ],
                    "allowed_sentiments": [
                        str(value).strip().upper()
                        for value in item["allowed_sentiments"]
                    ],
                    "allowed_claim_ids": list(
                        item["allowed_claim_ids"]
                        if item.get("allowed_claim_ids") is not None
                        else previous.get("allowed_claim_ids", [])
                    ),
                }
            )
        return snapshot

    def _validate_candidate(
        self,
        standard_id: str,
        candidate: dict[str, Any],
        base: dict[str, Any],
    ) -> dict[str, list[str]]:
        blocking: list[str] = []
        warnings: list[str] = []
        taxonomy = candidate.get("taxonomy", {})
        groups = taxonomy.get("validation_rules", {}).get("allowed_groups", [])
        if groups and groups != load_taxonomy_alignment()["groups"]:
            blocking.append("统一标准必须使用规定的七个业务分组")
        if not str(candidate.get("name", "")).strip():
            blocking.append("标准名称不能为空")
        if not str(taxonomy.get("product_context", "")).strip():
            blocking.append("适用商品说明不能为空")
        if not taxonomy.get("instructions"):
            blocking.append("至少需要一条分类规则")
        if not candidate.get("variants"):
            blocking.append("至少需要一个适用品类")
        if not taxonomy.get("labels"):
            blocking.append("至少需要一个问题标签")
        categories = [
            (str(item.get("category_a", "")), str(item.get("category_b", "")))
            for item in candidate.get("variants", [])
        ]
        label_codes = [str(item.get("code", "")) for item in taxonomy.get("labels", [])]
        for index, (category_a, category_b) in enumerate(categories, start=1):
            if not category_a.strip() or not category_b.strip():
                blocking.append(f"第 {index} 个品类的品类 A 和品类 B 不能为空")
        for index, label in enumerate(taxonomy.get("labels", []), start=1):
            if not all(
                str(label.get(field, "")).strip()
                for field in ("code", "name", "group", "description")
            ):
                blocking.append(f"第 {index} 个标签的编码、名称、分组和定义不能为空")
            if not label.get("allowed_sentiments"):
                blocking.append(f"第 {index} 个标签至少需要一种适用情感")
        if len(categories) != len(set(categories)):
            blocking.append("同一标准内存在重复品类映射")
        if len(label_codes) != len(set(label_codes)):
            blocking.append("同一标准内存在重复标签编码")
        if "UNSPECIFIED" not in taxonomy.get("allowed_parts", []):
            blocking.append("证据部位必须保留“未指定部位”")
        try:
            candidate_capability = self._capability_from_snapshot(candidate)
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            blocking.append(f"标准结构无效：{self._validation_message(exc)}")
            candidate_capability = None
        if candidate_capability is not None:
            try:
                capabilities = [candidate_capability]
                with self.database.connect() as connection:
                    rows = connection.execute(
                        """
                        SELECT v.snapshot_json
                        FROM classification_standards s
                        JOIN classification_standard_versions v
                          ON v.id = s.current_version_id
                        WHERE s.status = 'active' AND s.id != ?
                        """,
                        (standard_id,),
                    ).fetchall()
                capabilities.extend(
                    self._capability_from_snapshot(json.loads(row["snapshot_json"]))
                    for row in rows
                )
                registry = CapabilityRegistry(
                    version="classification-standard-draft-validation",
                    capabilities=tuple(capabilities),
                )
                registry.combined_taxonomy()
            except (KeyError, TypeError, ValueError, ValidationError) as exc:
                blocking.append(f"与已发布标准冲突：{self._validation_message(exc)}")
        diff = self._diff_snapshots(base, candidate)
        if not diff["has_changes"]:
            blocking.append("草稿与当前已发布版本没有差异")
        if diff["semantic_label_changes"]:
            codes = "、".join(diff["semantic_label_changes"])
            blocking.append(
                f"已发布标签不能同码改义：{codes}；请停用旧标签并创建新编码"
            )
        if diff["removed_categories"]:
            warnings.append(
                f"将移除 {len(diff['removed_categories'])} 个适用品类，新任务不再匹配这些品类"
            )
        if diff["removed_labels"]:
            warnings.append(
                f"将停用 {len(diff['removed_labels'])} 个标签，历史结果仍保留原标签"
            )
        nonsemantic_changes = sorted(
            set(diff["modified_labels"]) - set(diff["semantic_label_changes"])
        )
        if nonsemantic_changes:
            warnings.append(
                f"补充了 {len(nonsemantic_changes)} 个已发布标签的搜索别名或判定说明"
            )
        return {
            "blocking": list(dict.fromkeys(blocking)),
            "warnings": warnings,
        }

    @staticmethod
    def _validation_message(exc: Exception) -> str:
        if isinstance(exc, ValidationError) and exc.errors():
            error = exc.errors()[0]
            path = ".".join(str(value) for value in error["loc"])
            return f"{path} {error['msg']}".strip()
        return str(exc)

    @staticmethod
    def _editable_content(snapshot: dict[str, Any]) -> dict[str, Any]:
        taxonomy = snapshot["taxonomy"]
        return {
            "name": snapshot["name"],
            "recognition_profile": taxonomy.get("recognition_profile", "legacy_v3"),
            "product_context": taxonomy["product_context"],
            "instructions": list(taxonomy["instructions"]),
            "allowed_parts": list(taxonomy["allowed_parts"]),
            "validation_rules": deepcopy(taxonomy.get("validation_rules", {})),
            "variants": deepcopy(snapshot["variants"]),
            "labels": [
                {
                    "code": label["code"],
                    "name": label["name"],
                    "group": label["group"],
                    "description": label["description"],
                    "keywords": list(label.get("keywords", [])),
                    "exclusions": list(label.get("exclusions", [])),
                    "examples": deepcopy(label.get("examples", [])),
                    "allowed_sentiments": list(label["allowed_sentiments"]),
                    "allowed_claim_ids": list(label.get("allowed_claim_ids", [])),
                }
                for label in taxonomy["labels"]
            ],
        }

    @classmethod
    def _diff_snapshots(
        cls,
        base: dict[str, Any],
        candidate: dict[str, Any],
    ) -> dict[str, Any]:
        base_content = cls._editable_content(base)
        candidate_content = cls._editable_content(candidate)
        base_categories = {
            (item["category_a"], item["category_b"])
            for item in base_content["variants"]
        }
        candidate_categories = {
            (item["category_a"], item["category_b"])
            for item in candidate_content["variants"]
        }
        base_labels = {item["code"]: item for item in base_content["labels"]}
        candidate_labels = {item["code"]: item for item in candidate_content["labels"]}
        shared_codes = base_labels.keys() & candidate_labels.keys()
        return {
            "has_changes": base_content != candidate_content,
            "added_categories": sorted(candidate_categories - base_categories),
            "removed_categories": sorted(base_categories - candidate_categories),
            "added_labels": sorted(candidate_labels.keys() - base_labels.keys()),
            "removed_labels": sorted(base_labels.keys() - candidate_labels.keys()),
            "modified_labels": sorted(
                code
                for code in shared_codes
                if base_labels[code] != candidate_labels[code]
            ),
            "semantic_label_changes": sorted(
                code
                for code in shared_codes
                if any(
                    base_labels[code][field] != candidate_labels[code][field]
                    for field in (
                        "name",
                        "group",
                        "description",
                        "allowed_sentiments",
                    )
                )
            ),
            "rules_changed": (
                base_content["recognition_profile"]
                != candidate_content["recognition_profile"]
                or base_content["instructions"] != candidate_content["instructions"]
                or base_content["allowed_parts"] != candidate_content["allowed_parts"]
                or base_content["validation_rules"]
                != candidate_content["validation_rules"]
            ),
            "description_changed": (
                base_content["name"] != candidate_content["name"]
                or base_content["product_context"]
                != candidate_content["product_context"]
            ),
        }

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

    def _import_seed_config(self, connection: Any) -> None:
        registry_path = PROJECT_ROOT / "config" / "category_capabilities.json"
        registry_data = json.loads(registry_path.read_text(encoding="utf-8"))
        now = utc_now()
        for family in registry_data["families"]:
            standard_key = str(family["key"])
            standard_id = f"classification_standard_{standard_key}"
            taxonomy_path = registry_path.parent / str(family["taxonomy"])
            taxonomy = json.loads(taxonomy_path.read_text(encoding="utf-8"))
            snapshot = {
                "standard_key": standard_key,
                "name": self._standard_name(str(family["agent_family"])),
                "agent_family": str(family["agent_family"]),
                "logic_version": str(family["logic_version"]),
                "model_policy": family["model_policy"],
                "variants": family["variants"],
                "taxonomy": taxonomy,
            }
            encoded = json.dumps(
                snapshot,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            content_hash = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
            version_id = (
                f"classification_standard_version_{standard_key}_{content_hash[:16]}"
            )
            connection.execute(
                """
                INSERT INTO classification_standards(
                    id, standard_key, name, status, current_version_id,
                    created_at, updated_at
                ) VALUES (?, ?, ?, 'active', NULL, ?, ?)
                """,
                (standard_id, standard_key, snapshot["name"], now, now),
            )
            connection.execute(
                """
                INSERT INTO classification_standard_versions(
                    id, standard_id, version_no, version_key,
                    logic_version, taxonomy_version, model_policy_version,
                    snapshot_json, content_hash, version_reason, status,
                    created_at, published_at
                ) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, '导入现有分类配置',
                          'published', ?, ?)
                """,
                (
                    version_id,
                    standard_id,
                    str(taxonomy["version"]),
                    str(family["logic_version"]),
                    str(taxonomy["version"]),
                    str(family["model_policy"]["version"]),
                    encoded,
                    content_hash,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                UPDATE classification_standards
                SET current_version_id = ? WHERE id = ?
                """,
                (version_id, standard_id),
            )

    def _migrate_taxonomy_validation_rules(self, connection: Any) -> None:
        migration = connection.execute(
            "SELECT 1 FROM app_migrations WHERE migration_id = ?",
            (CLASSIFICATION_STANDARD_RULES_MIGRATION,),
        ).fetchone()
        if migration is not None:
            return

        registry_path = PROJECT_ROOT / "config" / "category_capabilities.json"
        registry_data = json.loads(registry_path.read_text(encoding="utf-8"))
        rules_by_standard = {}
        for family in registry_data["families"]:
            taxonomy_path = registry_path.parent / str(family["taxonomy"])
            taxonomy = json.loads(taxonomy_path.read_text(encoding="utf-8"))
            rules = taxonomy.get("validation_rules", {})
            if rules:
                rules_by_standard[str(family["key"])] = rules

        updated_count = 0
        version_rows = connection.execute(
            """
            SELECT version.id, version.snapshot_json, standard.standard_key
            FROM classification_standard_versions version
            JOIN classification_standards standard
              ON standard.id = version.standard_id
            """
        ).fetchall()
        for row in version_rows:
            rules = rules_by_standard.get(str(row["standard_key"]))
            snapshot = json.loads(row["snapshot_json"])
            if not rules or "validation_rules" in snapshot["taxonomy"]:
                continue
            snapshot["taxonomy"]["validation_rules"] = deepcopy(rules)
            encoded = json.dumps(
                snapshot,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            content_hash = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
            connection.execute(
                """
                UPDATE classification_standard_versions
                SET snapshot_json = ?, content_hash = ? WHERE id = ?
                """,
                (encoded, content_hash, row["id"]),
            )
            updated_count += 1

        draft_rows = connection.execute(
            """
            SELECT draft.id, draft.snapshot_json, standard.standard_key
            FROM classification_standard_drafts draft
            JOIN classification_standards standard
              ON standard.id = draft.standard_id
            """
        ).fetchall()
        for row in draft_rows:
            rules = rules_by_standard.get(str(row["standard_key"]))
            snapshot = json.loads(row["snapshot_json"])
            if not rules or "validation_rules" in snapshot["taxonomy"]:
                continue
            snapshot["taxonomy"]["validation_rules"] = deepcopy(rules)
            connection.execute(
                """
                UPDATE classification_standard_drafts
                SET snapshot_json = ? WHERE id = ?
                """,
                (json_text(snapshot), row["id"]),
            )
            updated_count += 1

        rules_checksum = hashlib.sha256(
            json_text(rules_by_standard).encode("utf-8")
        ).hexdigest()
        connection.execute(
            """
            INSERT INTO app_migrations(
                migration_id, checksum, status, applied_at
            ) VALUES (?, ?, ?, ?)
            """,
            (
                CLASSIFICATION_STANDARD_RULES_MIGRATION,
                rules_checksum,
                "applied" if updated_count else "baselined",
                utc_now(),
            ),
        )

    def _backfill_bindings(self, connection: Any) -> None:
        versions = connection.execute(
            """
            SELECT s.standard_key, v.id, v.logic_version,
                   v.taxonomy_version, v.model_policy_version
            FROM classification_standards s
            JOIN classification_standard_versions v
              ON v.id = s.current_version_id
            """
        ).fetchall()
        for version in versions:
            values = (
                version["id"],
                version["standard_key"],
                version["logic_version"],
                version["taxonomy_version"],
                version["model_policy_version"],
            )
            connection.execute(
                """
                UPDATE task_segments
                SET standard_version_id = ?
                WHERE standard_version_id IS NULL
                  AND agent_key = ?
                  AND COALESCE(logic_version, '') = COALESCE(?, '')
                  AND taxonomy_version = ?
                  AND COALESCE(model_policy_version, '') = COALESCE(?, '')
                """,
                values,
            )
            connection.execute(
                """
                UPDATE classification_results
                SET standard_version_id = ?
                WHERE standard_version_id IS NULL
                  AND agent_key = ?
                  AND COALESCE(logic_version, '') = COALESCE(?, '')
                  AND taxonomy_version = ?
                  AND COALESCE(model_policy_version, '') = COALESCE(?, '')
                """,
                values,
            )

    @staticmethod
    def _standard_name(agent_family: str) -> str:
        family_name = agent_family.removesuffix("智能体")
        return f"{family_name}退货问题标准"

    @staticmethod
    def _capability_from_snapshot(snapshot: dict[str, Any]) -> CategoryCapability:
        policy = snapshot["model_policy"]
        return CategoryCapability(
            key=str(snapshot["standard_key"]),
            agent_family=str(snapshot["agent_family"]),
            logic_version=str(snapshot["logic_version"]),
            model_policy=ModelPolicy(
                version=str(policy["version"]),
                first_pass_role=str(policy["first_pass_role"]),
                review_role=(
                    str(policy["review_role"]) if policy.get("review_role") else None
                ),
            ),
            variants=tuple(
                CategoryVariant(
                    category_a=str(item["category_a"]),
                    category_b=str(item["category_b"]),
                    attributes={
                        str(key): str(value)
                        for key, value in item.get("attributes", {}).items()
                    },
                )
                for item in snapshot["variants"]
            ),
            taxonomy=TaxonomyConfig.model_validate(snapshot["taxonomy"]),
        )

    @staticmethod
    def _serialize_standard(
        value: dict[str, Any],
        include_snapshot: bool = False,
    ) -> dict[str, Any]:
        snapshot = json.loads(value.pop("snapshot_json"))
        taxonomy = snapshot["taxonomy"]
        output = {
            **value,
            "standard_version_id": value["current_version_id"],
            "agent_family": snapshot["agent_family"],
            "product_context": taxonomy["product_context"],
            "category_count": len(snapshot["variants"]),
            "label_count": len(taxonomy["labels"]),
            "label_group_count": len(
                {str(label["group"]) for label in taxonomy["labels"]}
            ),
            "delete_mode": (
                "delete"
                if int(value.get("published_version_count") or 0) == 0
                and int(value.get("task_segment_count") or 0) == 0
                and int(value.get("result_count") or 0) == 0
                else "deactivate"
            ),
        }
        if include_snapshot:
            output["snapshot"] = snapshot
        return output

    @staticmethod
    def _serialize_version(
        value: dict[str, Any],
        include_snapshot: bool = False,
    ) -> dict[str, Any]:
        snapshot = json.loads(value.pop("snapshot_json"))
        output = value
        if include_snapshot:
            output["snapshot"] = snapshot
        return output
