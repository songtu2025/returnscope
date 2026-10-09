"""构建分类结果版本查询和列表分页，沿用服务入口的校验规则。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from web_backend.review_statistics_sql import REVIEW_CHANGED_UNIT_COUNT_SQL

VERSION_SELECT_SQL = f"""
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
                   {REVIEW_CHANGED_UNIT_COUNT_SQL} AS changed_unit_count,
                   r.source_task_id, r.source_segment_id,
                   COALESCE(
                       json_extract(task.snapshot_json, '$.analysis_context'),
                       'returns'
                   ) AS analysis_context,
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
            LEFT JOIN tasks task ON task.id = r.source_task_id
            LEFT JOIN classification_standard_versions standard_version
              ON standard_version.id = r.standard_version_id
            LEFT JOIN classification_standards standard
              ON standard.id = standard_version.standard_id
            LEFT JOIN users creator ON creator.id = v.created_by
        """


VERSION_SEARCH_SQL = """
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


def version_list_filters(
    filters: dict[str, str | None],
    contains_pattern: Callable[[str], str],
    validate_quality_status: Callable[[str], None],
) -> tuple[str, list[Any]]:
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
    clean_query = (filters.get("q") or "").strip()
    if clean_query:
        pattern = contains_pattern(clean_query)
        where.append(VERSION_SEARCH_SQL)
        params.extend([pattern, pattern, pattern, pattern])
    store_site = filters.get("store_site")
    if store_site:
        where.append("r.store_site = ?")
        params.append(store_site)
    listing = filters.get("listing")
    if listing:
        where.append("r.listing = ?")
        params.append(listing)
    quality_status = filters.get("quality_status")
    if quality_status:
        validate_quality_status(quality_status)
        where.append(
            "EXISTS (SELECT 1 FROM classification_result_records quality_record "
            "WHERE quality_record.result_version_id = v.id "
            "AND quality_record.quality_status = ?)"
        )
        params.append(quality_status)
    return " AND ".join(where), params


def fetch_version_page(
    connection: Any,
    select_sql: str,
    filters: tuple[str, list[Any]],
    page: int,
    page_size: int,
) -> tuple[int, list[Any]]:
    where_sql, params = filters
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
        {select_sql}
        WHERE {where_sql}
        ORDER BY v.published_at DESC, v.id ASC
        LIMIT ? OFFSET ?
        """,
        (*params, page_size, (page - 1) * page_size),
    ).fetchall()
    return total, rows
