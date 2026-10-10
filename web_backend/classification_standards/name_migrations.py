from __future__ import annotations

import hashlib
import json
from typing import Any

from web_backend.classification_standard_contracts import (
    CLASSIFICATION_STANDARD_CATEGORY_NAMES_MIGRATION,
    CLASSIFICATION_STANDARD_NAME_MIGRATION,
)
from web_backend.common import json_text
from web_backend.security import utc_now


class StandardNameMigrationMixin:
    @staticmethod
    def _migrate_gloves_standard_name(connection: Any) -> None:
        StandardNameMigrationMixin._migrate_standard_names(
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
        StandardNameMigrationMixin._migrate_standard_names(
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
