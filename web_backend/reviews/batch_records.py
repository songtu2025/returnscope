"""查询批次复核记录并聚合关联来源字段。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from return_semantics.schemas import TaxonomyConfig
from web_backend.classification_result_service import ClassificationResultService
from web_backend.common import json_value
from web_backend.database import Database
from web_backend.result_hierarchy import enrich_record, result_taxonomy


class ReviewBatchRecordsMixin:
    database: Database

    if TYPE_CHECKING:

        def get_batch(self, batch_id: str) -> dict[str, Any]: ...

        @staticmethod
        def _serialize(
            item: dict[str, Any],
            taxonomy: TaxonomyConfig | None = None,
        ) -> dict[str, Any]: ...

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
                enrich_record(
                    self._serialize_batch_record(dict(row), taxonomy),
                    taxonomy,
                )
                for row in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    @classmethod
    def _serialize_batch_record(
        cls,
        item: dict[str, Any],
        taxonomy: TaxonomyConfig | None,
    ) -> dict[str, Any]:
        item = cls._serialize(item, taxonomy)
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
