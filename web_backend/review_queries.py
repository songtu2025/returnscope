from __future__ import annotations

from typing import Any

from web_backend.classification_result_service import ClassificationResultService
from web_backend.common import json_value
from web_backend.database import Database
from web_backend.result_hierarchy import enrich_record, result_taxonomy

_BATCH_SUMMARY_SELECT = """
    SELECT b.*, base.version_no AS version_no,
           base.version_no AS base_version_no,
           base.quality_status AS quality_status,
           base.quality_status AS base_quality_status,
           base.unit_count AS unit_count,
           base.unit_count AS base_unit_count,
           base.record_count AS base_record_count,
           result.store_site, result.listing,
           creator.display_name AS creator_name,
           COUNT(rr.id) AS record_count,
           COALESCE(SUM(
               CASE WHEN rr.workflow_status = 'resolved' THEN 1 ELSE 0 END
           ), 0) AS resolved_count,
           COALESCE(SUM(
               CASE WHEN rr.workflow_status = 'excluded' THEN 1 ELSE 0 END
           ), 0) AS excluded_count,
           b.published_version_id AS derived_result_version_id,
           derived.version_no AS derived_version_no,
           derived.quality_status AS derived_quality_status,
           derived.published_at AS derived_published_at
    FROM review_batches b
    JOIN classification_result_versions base
      ON base.id = b.base_result_version_id
    JOIN classification_results result ON result.id = b.result_id
    JOIN users creator ON creator.id = b.created_by
    LEFT JOIN review_records rr ON rr.batch_id = b.id
    LEFT JOIN classification_result_versions derived
      ON derived.id = b.published_version_id
"""


class ReviewQueriesMixin:
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
        return [self._serialize(dict(row)) for row in rows]

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
        item = self._serialize(dict(row))
        item["revisions"] = [
            self._serialize_revision(dict(value)) for value in revisions
        ]
        return item

    def list_batches(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        status: str | None = None,
        base_result_version_id: str | None = None,
        q: str | None = None,
    ) -> dict[str, Any]:
        page, page_size = ClassificationResultService._validate_page(
            page,
            page_size,
        )
        where: list[str] = []
        params: list[Any] = []
        if status:
            if status not in {"draft", "published"}:
                raise ValueError("status 仅支持 draft 或 published")
            where.append("b.status = ?")
            params.append(status)
        if base_result_version_id:
            where.append("b.base_result_version_id = ?")
            params.append(base_result_version_id)
        clean_query = (q or "").strip()
        if clean_query:
            pattern = ClassificationResultService._contains_pattern(clean_query)
            where.append(
                """
                (
                    result.listing LIKE ? ESCAPE '\\'
                    OR b.id LIKE ? ESCAPE '\\'
                    OR creator.display_name LIKE ? ESCAPE '\\'
                    OR b.created_by LIKE ? ESCAPE '\\'
                )
                """
            )
            params.extend([pattern, pattern, pattern, pattern])
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        joins = """
            FROM review_batches b
            JOIN classification_result_versions base
              ON base.id = b.base_result_version_id
            JOIN classification_results result ON result.id = b.result_id
            JOIN users creator ON creator.id = b.created_by
        """
        with self.database.connect() as connection:
            total = int(
                connection.execute(
                    f"SELECT COUNT(*) {joins} {where_sql}",
                    tuple(params),
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"""
                {_BATCH_SUMMARY_SELECT}
                {where_sql}
                GROUP BY b.id
                ORDER BY b.updated_at DESC, b.id DESC
                LIMIT ? OFFSET ?
                """,
                (*params, page_size, (page - 1) * page_size),
            ).fetchall()
        return {
            "items": [self._serialize_batch(dict(row)) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def get_batch(self, batch_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                f"""
                {_BATCH_SUMMARY_SELECT}
                WHERE b.id = ?
                GROUP BY b.id
                """,
                (batch_id,),
            ).fetchone()
        if row is None:
            raise ValueError("复核批次不存在")
        return self._serialize_batch(dict(row))

    def batch_records(
        self,
        batch_id: str,
        *,
        page: int = 1,
        page_size: int = 50,
        workflow_status: str | None = None,
        q: str | None = None,
        listing: str | None = None,
        product_name: str | None = None,
        product_sku: str | None = None,
        order_id: str | None = None,
    ) -> dict[str, Any]:
        self.get_batch(batch_id)
        page, page_size = ClassificationResultService._validate_page(
            page,
            page_size,
        )
        where = ["r.batch_id = ?"]
        params: list[Any] = [batch_id]
        if workflow_status:
            where.append("r.workflow_status = ?")
            params.append(workflow_status)
        record_filters = {
            "listing": listing,
            "product_name": product_name,
            "product_sku": product_sku,
            "order_id": order_id,
        }
        business_where: list[str] = []
        for column, value in record_filters.items():
            if value:
                business_where.append(f"filtered.{column} = ?")
                params.append(value)
        if business_where:
            where.append(
                f"""
                EXISTS (
                    SELECT 1 FROM classification_result_records filtered
                    WHERE filtered.result_version_id = b.base_result_version_id
                      AND filtered.classification_key = r.classification_key
                      AND {" AND ".join(business_where)}
                )
                """
            )
        clean_query = (q or "").strip()
        if clean_query:
            pattern = ClassificationResultService._contains_pattern(clean_query)
            where.append(
                """
                (
                    r.comment LIKE ? ESCAPE '\\'
                    OR r.classification_key LIKE ? ESCAPE '\\'
                    OR EXISTS (
                        SELECT 1 FROM classification_result_records searched
                        WHERE searched.result_version_id = b.base_result_version_id
                          AND searched.classification_key = r.classification_key
                          AND (
                              searched.order_id LIKE ? ESCAPE '\\'
                              OR searched.product_name LIKE ? ESCAPE '\\'
                              OR searched.listing LIKE ? ESCAPE '\\'
                              OR searched.source_sku LIKE ? ESCAPE '\\'
                              OR searched.matched_msku LIKE ? ESCAPE '\\'
                              OR searched.product_sku LIKE ? ESCAPE '\\'
                          )
                    )
                )
                """
            )
            params.extend([pattern] * 8)
        where_sql = " AND ".join(where)
        with self.database.connect() as connection:
            total = int(
                connection.execute(
                    f"""
                    SELECT COUNT(*) FROM review_records r
                    JOIN review_batches b ON b.id = r.batch_id
                    WHERE {where_sql}
                    """,
                    tuple(params),
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"""
                SELECT r.*, editor.display_name AS updated_by_name,
                       COUNT(business.id) AS record_count,
                       COALESCE(json_group_array(DISTINCT business.order_id)
                           FILTER (WHERE NULLIF(TRIM(business.order_id), '')
                           IS NOT NULL), '[]') AS order_ids_json,
                       COALESCE(json_group_array(DISTINCT business.product_name)
                           FILTER (WHERE NULLIF(TRIM(business.product_name), '')
                           IS NOT NULL), '[]') AS product_names_json,
                       COALESCE(json_group_array(DISTINCT business.listing)
                           FILTER (WHERE NULLIF(TRIM(business.listing), '')
                           IS NOT NULL), '[]') AS listings_json,
                       COALESCE(json_group_array(DISTINCT business.source_sku)
                           FILTER (WHERE NULLIF(TRIM(business.source_sku), '')
                           IS NOT NULL), '[]') AS source_skus_json,
                       COALESCE(json_group_array(DISTINCT business.matched_msku)
                           FILTER (WHERE NULLIF(TRIM(business.matched_msku), '')
                           IS NOT NULL), '[]') AS matched_mskus_json,
                       COALESCE(json_group_array(DISTINCT business.product_sku)
                           FILTER (WHERE NULLIF(TRIM(business.product_sku), '')
                           IS NOT NULL), '[]') AS product_skus_json
                FROM review_records r
                JOIN review_batches b ON b.id = r.batch_id
                LEFT JOIN users editor ON editor.id = r.updated_by
                LEFT JOIN classification_result_records business
                  ON business.result_version_id = b.base_result_version_id
                 AND business.classification_key = r.classification_key
                WHERE {where_sql}
                GROUP BY r.id
                ORDER BY r.classification_key, r.id
                LIMIT ? OFFSET ?
                """,
                (*params, page_size, (page - 1) * page_size),
            ).fetchall()
        batch = self.get_batch(batch_id)
        with self.database.connect() as connection:
            taxonomy = result_taxonomy(connection, batch["base_result_version_id"])
        return {
            "taxonomy": taxonomy.model_dump(mode="json") if taxonomy else None,
            "items": [
                enrich_record(self._serialize_batch_record(dict(row)), taxonomy)
                for row in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    @staticmethod
    def _serialize_batch(item: dict[str, Any]) -> dict[str, Any]:
        item["record_count"] = int(item.get("record_count") or 0)
        item["resolved_count"] = int(item.get("resolved_count") or 0)
        item["excluded_count"] = int(item.get("excluded_count") or 0)
        item["remaining_count"] = (
            item["record_count"] - item["resolved_count"] - item["excluded_count"]
        )
        item["creator"] = {
            "id": item.get("created_by"),
            "display_name": item.get("creator_name"),
        }
        return item

    @classmethod
    def _serialize_batch_record(cls, item: dict[str, Any]) -> dict[str, Any]:
        item = cls._serialize(item)
        for field in (
            "order_ids",
            "product_names",
            "listings",
            "source_skus",
            "matched_mskus",
            "product_skus",
        ):
            values = json_value(item.pop(f"{field}_json", None), [])
            item[field] = sorted(
                {
                    str(value).strip()
                    for value in values
                    if value is not None and str(value).strip()
                }
            )
        item["record_count"] = int(item.get("record_count") or 0)
        return item

    @staticmethod
    def _serialize(item: dict[str, Any]) -> dict[str, Any]:
        item["legacy"] = item.get("batch_id") is None
        item["classification"] = json_value(
            item.pop("classification_json", None),
            {},
        )
        return item

    @staticmethod
    def _serialize_revision(item: dict[str, Any]) -> dict[str, Any]:
        item["before"] = json_value(item.pop("before_json"), {})
        item["after"] = json_value(item.pop("after_json"), {})
        return item
