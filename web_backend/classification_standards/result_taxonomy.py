from __future__ import annotations

from collections.abc import Callable
from typing import Any

from return_semantics.schemas import TaxonomyConfig
from return_semantics.taxonomy_hierarchy import label_path
from web_backend.classification_standard_contracts import ClassificationStandardNotFound
from web_backend.database import Database


class StandardResultTaxonomyMixin:
    database: Database
    get_version: Callable[..., dict[str, Any]]

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
