from __future__ import annotations

from typing import TYPE_CHECKING, Any

from return_semantics.schemas import TaxonomyConfig
from web_backend.classification_result_payload import PAGE_SIZE_DEFAULT
from web_backend.classification_result_publication import (
    ClassificationResultNotFound,
)
from web_backend.common import json_value
from web_backend.database import Database
from web_backend.result_hierarchy import result_taxonomy
from web_backend.result_state import result_delivery_state


class _ClassificationResultQueries:
    database: Database

    if TYPE_CHECKING:

        @staticmethod
        def _validate_page(page: int, page_size: int) -> tuple[int, int]: ...

        @staticmethod
        def _validate_quality_status(value: str) -> None: ...

    def get(self, version_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            return self._get_version_with_connection(connection, version_id)

    def taxonomy(self, version_id: str) -> TaxonomyConfig | None:
        with self.database.connect() as connection:
            return result_taxonomy(connection, version_id)

    def history(self, version_id: str) -> list[dict[str, Any]]:
        current = self.get(version_id)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                {self._version_select()}
                WHERE v.result_id = ? AND v.publish_status = 'published'
                ORDER BY v.version_no DESC
                """,
                (current["result_id"],),
            ).fetchall()
        return [self._serialize_version(dict(row)) for row in rows]

    @staticmethod
    def _version_select() -> str:
        return """
            SELECT v.id AS version_id, v.result_id, v.version_no AS version,
                   v.content_hash, v.quality_status, v.publish_status,
                   v.unit_count, v.record_count, v.created_at,
                   v.published_at, v.parent_version_id, v.version_reason,
                   v.created_by, creator.display_name AS created_by_name,
                   (
                       SELECT batch.id FROM review_batches batch
                       WHERE batch.published_version_id = v.id
                       ORDER BY batch.published_at DESC, batch.id DESC
                       LIMIT 1
                   ) AS source_review_batch_id,
                   (
                       SELECT parent.version_no
                       FROM classification_result_versions parent
                       WHERE parent.id = v.parent_version_id
                   ) AS parent_version_no,
                   COALESCE((
                       SELECT COUNT(DISTINCT revision.review_record_id)
                       FROM review_batches batch
                       JOIN review_records review
                         ON review.batch_id = batch.id
                       JOIN review_revisions revision
                         ON revision.review_record_id = review.id
                       WHERE batch.published_version_id = v.id
                         AND (
                             json_extract(
                                 revision.before_json, '$.semantic_units'
                             ) IS NOT json_extract(
                                 revision.after_json, '$.semantic_units'
                             )
                             OR json_extract(
                                 revision.before_json, '$.unknown_semantics'
                             ) IS NOT json_extract(
                                 revision.after_json, '$.unknown_semantics'
                             )
                             OR json_extract(
                                 revision.before_json, '$.problem_label_codes'
                             ) IS NOT json_extract(
                                 revision.after_json, '$.problem_label_codes'
                             )
                             OR json_extract(
                                 revision.before_json, '$.positive_label_codes'
                             ) IS NOT json_extract(
                                 revision.after_json, '$.positive_label_codes'
                             )
                             OR json_extract(
                                 revision.before_json, '$.primary_label_codes'
                             ) IS NOT json_extract(
                                 revision.after_json, '$.primary_label_codes'
                             )
                         )
                   ), 0) AS changed_unit_count,
                   r.source_task_id, r.source_segment_id,
                   r.dataset_version_id, r.product_version_id,
                   r.store_site, r.listing, r.agent_key, r.agent_family,
                   r.logic_version, r.taxonomy_version,
                   r.model_policy_version, r.standard_version_id,
                   standard.id AS standard_id,
                   standard.name AS standard_name,
                   standard_version.version_no AS standard_version,
                   r.claims_version,
                   rd.name AS dataset_name, dv.version AS dataset_version,
                   pd.name AS product_dataset_name,
                   pv.version AS product_version,
                   COALESCE((
                       SELECT json_group_array(product_name)
                       FROM (
                           SELECT DISTINCT records.product_name AS product_name
                           FROM classification_result_records records
                           WHERE records.result_version_id = v.id
                             AND records.product_name IS NOT NULL
                             AND TRIM(records.product_name) != ''
                           ORDER BY records.product_name COLLATE NOCASE,
                                    records.product_name
                       )
                   ), '[]') AS product_names_json
            FROM classification_result_versions v
            JOIN classification_results r ON r.id = v.result_id
            JOIN dataset_versions dv ON dv.id = r.dataset_version_id
            JOIN datasets rd ON rd.id = dv.dataset_id
            JOIN dataset_versions pv ON pv.id = r.product_version_id
            JOIN datasets pd ON pd.id = pv.dataset_id
            LEFT JOIN classification_standard_versions standard_version
              ON standard_version.id = r.standard_version_id
            LEFT JOIN classification_standards standard
              ON standard.id = standard_version.standard_id
            LEFT JOIN users creator ON creator.id = v.created_by
        """

    def _get_version_with_connection(
        self,
        connection: Any,
        version_id: str,
    ) -> dict[str, Any]:
        row = connection.execute(
            f"{self._version_select()} WHERE v.id = ?",
            (version_id,),
        ).fetchone()
        if row is None:
            raise ClassificationResultNotFound("分类结果版本不存在")
        return self._serialize_version(dict(row))

    @staticmethod
    def _serialize_version(value: dict[str, Any]) -> dict[str, Any]:
        value["product_names"] = json_value(
            value.pop("product_names_json", None),
            [],
        )
        value["changed_unit_count"] = int(value.get("changed_unit_count") or 0)
        value["inherited_unit_count"] = (
            max(int(value.get("unit_count") or 0) - value["changed_unit_count"], 0)
            if value.get("parent_version_id")
            else 0
        )
        value.update(
            result_delivery_state(
                quality_status=value.get("quality_status"),
                publish_status=value.get("publish_status"),
                parent_version_id=value.get("parent_version_id"),
                source_review_batch_id=value.get("source_review_batch_id"),
            )
        )
        return value

    @staticmethod
    def _contains_pattern(value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace("%", "\\%")
        escaped = escaped.replace("_", "\\_")
        return f"%{escaped}%"

    def list(
        self,
        *,
        page: int = 1,
        page_size: int = PAGE_SIZE_DEFAULT,
        q: str | None = None,
        store_site: str | None = None,
        listing: str | None = None,
        quality_status: str | None = None,
    ) -> dict[str, Any]:
        page, page_size = self._validate_page(page, page_size)
        where = [
            "v.publish_status = 'published'",
            """
            v.version_no = (
                SELECT MAX(latest.version_no)
                FROM classification_result_versions latest
                WHERE latest.result_id = v.result_id
                  AND latest.publish_status = 'published'
            )
            """,
        ]
        params: list[Any] = []
        clean_query = (q or "").strip()
        if clean_query:
            pattern = self._contains_pattern(clean_query)
            where.append(
                """
                EXISTS (
                    SELECT 1 FROM classification_result_records search_record
                    WHERE search_record.result_version_id = v.id
                      AND (
                          search_record.product_name LIKE ? ESCAPE '\\'
                          OR search_record.listing LIKE ? ESCAPE '\\'
                          OR search_record.source_sku LIKE ? ESCAPE '\\'
                          OR search_record.product_sku LIKE ? ESCAPE '\\'
                      )
                )
                """
            )
            params.extend([pattern, pattern, pattern, pattern])
        if store_site:
            where.append("r.store_site = ?")
            params.append(store_site)
        if listing:
            where.append("r.listing = ?")
            params.append(listing)
        if quality_status:
            self._validate_quality_status(quality_status)
            where.append("v.quality_status = ?")
            params.append(quality_status)
        where_sql = " AND ".join(where)
        with self.database.connect() as connection:
            total = int(
                connection.execute(
                    f"""
                    SELECT COUNT(*) FROM classification_result_versions v
                    JOIN classification_results r ON r.id = v.result_id
                    WHERE {where_sql}
                    """,
                    tuple(params),
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"""
                {self._version_select()}
                WHERE {where_sql}
                ORDER BY v.published_at DESC, v.id ASC
                LIMIT ? OFFSET ?
                """,
                (*params, page_size, (page - 1) * page_size),
            ).fetchall()
        return {
            "items": [self._serialize_version(dict(row)) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
