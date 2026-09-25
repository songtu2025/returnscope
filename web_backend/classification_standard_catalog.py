from __future__ import annotations

import hashlib
import json
from typing import Any, Callable

from return_semantics.capabilities import (
    CapabilityRegistry,
    CategoryCapability,
    CategoryVariant,
    ModelPolicy,
)
from return_semantics.schemas import TaxonomyConfig
from return_semantics.taxonomy_hierarchy import label_path
from web_backend.classification_standard_contracts import (
    ClassificationStandardNotFound,
)
from web_backend.common import add_audit
from web_backend.database import Database
from web_backend.security import utc_now

_STANDARD_CATALOG_SELECT_SQL = """
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
"""


class ClassificationStandardCatalogMixin:
    database: Database
    _tables_exist: Callable[[], bool]

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

    def get(self, standard_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                f"{_STANDARD_CATALOG_SELECT_SQL} WHERE s.id = ?",
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
            "labels": [
                {
                    **label.model_dump(mode="json"),
                    "label_path": label_path(taxonomy, label.code),
                }
                for label in taxonomy.labels
            ],
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
            raise ClassificationStandardNotFound(
                "历史结果缺少标准版本绑定，请恢复正确的历史标准绑定后再复核"
            )
        version = self.get_version(version_id)
        taxonomy = TaxonomyConfig.model_validate(version["snapshot"]["taxonomy"])
        return taxonomy, version

    def combined_taxonomy(self) -> TaxonomyConfig:
        return self.active_registry().combined_taxonomy()

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

    def list(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                f"{_STANDARD_CATALOG_SELECT_SQL} "
                "ORDER BY s.name COLLATE NOCASE, s.standard_key"
            ).fetchall()
        return [self._serialize_standard(dict(row)) for row in rows]
