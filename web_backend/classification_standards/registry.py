from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any

from return_semantics.capabilities import (
    CapabilityRegistry,
    CategoryCapability,
    CategoryVariant,
    ModelPolicy,
)
from return_semantics.schemas import TaxonomyConfig
from web_backend.classification_standard_contracts import ClassificationStandardNotFound
from web_backend.database import Database


class StandardRegistryMixin:
    _tables_exist: Callable[[], bool]
    database: Database
    get_version: Callable[..., dict[str, Any]]

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
