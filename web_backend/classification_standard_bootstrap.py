from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from web_backend.classification_standard_contracts import (
    CLASSIFICATION_STANDARD_CATEGORY_NAMES_MIGRATION,
    CLASSIFICATION_STANDARD_NAME_MIGRATION,
    CLASSIFICATION_STANDARD_RULES_MIGRATION,
)
from web_backend.common import json_text
from web_backend.database import Database
from web_backend.security import utc_now
from web_backend.settings import PROJECT_ROOT


class ClassificationStandardBootstrapMixin:
    database: Database

    def _tables_exist(self) -> bool:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT 1 FROM sqlite_master
                WHERE type = 'table' AND name = 'classification_standards'
                """
            ).fetchone()
        return row is not None

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

    @staticmethod
    def _migrate_gloves_standard_name(connection: Any) -> None:
        ClassificationStandardBootstrapMixin._migrate_standard_names(
            connection,
            migration_id=CLASSIFICATION_STANDARD_NAME_MIGRATION,
            name_updates={
                "gloves": (
                    "手套退货问题标准",
                    "手套用户反馈语义标准",
                )
            },
        )

    @staticmethod
    def _migrate_category_standard_names(connection: Any) -> None:
        ClassificationStandardBootstrapMixin._migrate_standard_names(
            connection,
            migration_id=CLASSIFICATION_STANDARD_CATEGORY_NAMES_MIGRATION,
            name_updates={
                "eyewear": (
                    "眼镜退货问题标准",
                    "眼镜用户反馈语义标准",
                ),
                "footwear": (
                    "鞋履退货问题标准",
                    "鞋履用户反馈语义标准",
                ),
                "headwear": (
                    "帽类退货问题标准",
                    "帽类用户反馈语义标准",
                ),
            },
        )

    @staticmethod
    def _migrate_standard_names(
        connection: Any,
        *,
        migration_id: str,
        name_updates: dict[str, tuple[str, str]],
    ) -> None:
        migration = connection.execute(
            "SELECT 1 FROM app_migrations WHERE migration_id = ?",
            (migration_id,),
        ).fetchone()
        if migration is not None:
            return

        now = utc_now()
        updated_count = 0
        for standard_key, (legacy_name, current_name) in name_updates.items():
            standard = connection.execute(
                """
                SELECT id, name FROM classification_standards
                WHERE standard_key = ?
                """,
                (standard_key,),
            ).fetchone()
            if standard is not None and standard["name"] == legacy_name:
                connection.execute(
                    """
                    UPDATE classification_standards
                    SET name = ?, updated_at = ? WHERE id = ?
                    """,
                    (current_name, now, standard["id"]),
                )
                drafts = connection.execute(
                    """
                    SELECT id, snapshot_json FROM classification_standard_drafts
                    WHERE standard_id = ?
                    """,
                    (standard["id"],),
                ).fetchall()
                for draft in drafts:
                    snapshot = json.loads(draft["snapshot_json"])
                    if snapshot.get("name") != legacy_name:
                        continue
                    snapshot["name"] = current_name
                    connection.execute(
                        """
                        UPDATE classification_standard_drafts
                        SET snapshot_json = ?, updated_at = ? WHERE id = ?
                        """,
                        (json_text(snapshot), now, draft["id"]),
                    )
                updated_count += 1

        checksum = hashlib.sha256(json_text(name_updates).encode("utf-8")).hexdigest()
        connection.execute(
            """
            INSERT INTO app_migrations(
                migration_id, checksum, status, applied_at
            ) VALUES (?, ?, ?, ?)
            """,
            (
                migration_id,
                checksum,
                "applied" if updated_count else "baselined",
                now,
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
        return f"{family_name}用户反馈语义标准"
