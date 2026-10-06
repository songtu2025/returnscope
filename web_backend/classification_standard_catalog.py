from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from web_backend.classification_standard_contracts import ClassificationStandardNotFound
from web_backend.classification_standards.registry import StandardRegistryMixin
from web_backend.classification_standards.result_taxonomy import (
    StandardResultTaxonomyMixin,
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


def _can_hard_delete(value: Mapping[str, Any]) -> bool:
    return (
        int(value.get("published_version_count") or 0) == 0
        and int(value.get("task_segment_count") or 0) == 0
        and int(value.get("result_count") or 0) == 0
    )


class ClassificationStandardCatalogMixin(
    StandardRegistryMixin, StandardResultTaxonomyMixin
):
    database: Database

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
            hard_delete = _can_hard_delete(
                {
                    "published_version_count": published_count,
                    "task_segment_count": task_count,
                    "result_count": result_count,
                }
            )
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
            "delete_mode": ("delete" if _can_hard_delete(value) else "deactivate"),
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
