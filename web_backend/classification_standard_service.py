from __future__ import annotations

import hashlib
import json
from typing import Any

from return_semantics.taxonomy import load_taxonomy_alignment
from web_backend.classification_standard_bootstrap import (
    ClassificationStandardBootstrapMixin,
)
from web_backend.classification_standard_catalog import (
    ClassificationStandardCatalogMixin,
)
from web_backend.classification_standard_content import (
    ClassificationStandardContentMixin,
)
from web_backend.classification_standard_contracts import (
    CLASSIFICATION_STANDARD_RULES_MIGRATION as CLASSIFICATION_STANDARD_RULES_MIGRATION,
)
from web_backend.classification_standard_contracts import (
    CLASSIFICATION_STANDARD_SEED_MIGRATION as CLASSIFICATION_STANDARD_SEED_MIGRATION,
)
from web_backend.classification_standard_contracts import (
    ClassificationStandardConflict as ClassificationStandardConflict,
)
from web_backend.classification_standard_contracts import (
    ClassificationStandardNotFound as ClassificationStandardNotFound,
)
from web_backend.classification_standard_contracts import (
    ClassificationStandardValidationError as ClassificationStandardValidationError,
)
from web_backend.classification_standard_drafts import (
    ClassificationStandardDraftsMixin,
)
from web_backend.classification_standard_publication import (
    ClassificationStandardPublicationMixin,
)
from web_backend.common import add_audit, json_text, new_id
from web_backend.database import Database
from web_backend.security import utc_now

ClassificationStandardConflict.__module__ = __name__
ClassificationStandardNotFound.__module__ = __name__
ClassificationStandardValidationError.__module__ = __name__


class ClassificationStandardService(
    ClassificationStandardBootstrapMixin,
    ClassificationStandardCatalogMixin,
    ClassificationStandardDraftsMixin,
    ClassificationStandardPublicationMixin,
    ClassificationStandardContentMixin,
):
    def __init__(self, database: Database) -> None:
        self.database = database
        if self._tables_exist():
            self.ensure_bootstrapped()

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
        snapshot: dict[str, Any] = {
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
