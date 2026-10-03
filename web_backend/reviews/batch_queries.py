"""查询复核批次列表、详情和处理进度。"""

from __future__ import annotations

from typing import Any

from web_backend.classification_result_service import ClassificationResultService
from web_backend.database import Database

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


class ReviewBatchQueriesMixin:
    database: Database

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
