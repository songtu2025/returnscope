from __future__ import annotations

from typing import Any

from return_semantics.schemas import TaxonomyConfig
from web_backend.classification_result_payload import prepare_semantic_record
from web_backend.common import json_value
from web_backend.database import Database
from web_backend.result_hierarchy import result_taxonomy
from web_backend.reviews.batch_queries import (
    _BATCH_SUMMARY_SELECT as _BATCH_SUMMARY_SELECT,
)
from web_backend.reviews.batch_queries import ReviewBatchQueriesMixin
from web_backend.reviews.batch_records import ReviewBatchRecordsMixin


class ReviewQueriesMixin(ReviewBatchQueriesMixin, ReviewBatchRecordsMixin):
    database: Database

    def list(
        self,
        workflow_status: str | None = None,
        task_id: str | None = None,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT r.*, t.title AS task_title, t.owner_id,
                   owner.display_name AS owner_name,
                   editor.display_name AS updated_by_name
            FROM review_records r
            JOIN tasks t ON t.id = r.task_id
            JOIN users owner ON owner.id = t.owner_id
            LEFT JOIN users editor ON editor.id = r.updated_by
            WHERE r.batch_id IS NULL
        """
        params: list[object] = []
        if workflow_status:
            query += " AND r.workflow_status = ?"
            params.append(workflow_status)
        if task_id:
            query += " AND r.task_id = ?"
            params.append(task_id)
        query += " ORDER BY r.updated_at DESC"
        with self.database.connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
            taxonomies = {
                version_id: result_taxonomy(connection, version_id)
                for version_id in {
                    str(row["base_result_version_id"])
                    for row in rows
                    if row["base_result_version_id"]
                }
            }
        return [
            self._serialize(
                dict(row), taxonomies.get(str(row["base_result_version_id"]))
            )
            for row in rows
        ]

    def get(self, review_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT r.*, t.title AS task_title,
                       owner.display_name AS owner_name,
                       editor.display_name AS updated_by_name
                FROM review_records r
                JOIN tasks t ON t.id = r.task_id
                JOIN users owner ON owner.id = t.owner_id
                LEFT JOIN users editor ON editor.id = r.updated_by
                WHERE r.id = ?
                """,
                (review_id,),
            ).fetchone()
            if row is None:
                return None
            revisions = connection.execute(
                """
                SELECT rr.*, u.display_name AS actor_name
                FROM review_revisions rr
                JOIN users u ON u.id = rr.actor_id
                WHERE rr.review_record_id = ?
                ORDER BY rr.revision DESC
                """,
                (review_id,),
            ).fetchall()
            taxonomy = (
                result_taxonomy(connection, str(row["base_result_version_id"]))
                if row["base_result_version_id"]
                else None
            )
        item = self._serialize(dict(row), taxonomy)
        item["revisions"] = [
            self._serialize_revision(dict(value)) for value in revisions
        ]
        return item

    @staticmethod
    def _serialize(
        item: dict[str, Any],
        taxonomy: TaxonomyConfig | None = None,
    ) -> dict[str, Any]:
        item["legacy"] = item.get("batch_id") is None
        classification = json_value(
            item.pop("classification_json", None),
            {},
        )
        item["classification"] = classification
        return prepare_semantic_record(item, taxonomy)

    @staticmethod
    def _serialize_revision(item: dict[str, Any]) -> dict[str, Any]:
        item["before"] = json_value(item.pop("before_json"), {})
        item["after"] = json_value(item.pop("after_json"), {})
        return item
