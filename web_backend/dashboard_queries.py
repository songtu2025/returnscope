from __future__ import annotations

from typing import Any

from return_semantics.schemas import TaxonomyConfig
from web_backend.common import json_value
from web_backend.dashboard_common import GROUP_COLUMNS, PAGE_SIZE_DEFAULT
from web_backend.dashboard_support import (
    normalize_filters,
    record_where,
    serialize_record,
    validate_page,
    version_context,
)
from web_backend.database import Database
from web_backend.result_hierarchy import enrich_record


def list_records(
    database: Database,
    dashboard_id: str,
    version_id: str,
    *,
    page: int = 1,
    page_size: int = PAGE_SIZE_DEFAULT,
    **filters: str | None,
) -> dict[str, Any]:
    page, page_size = validate_page(page, page_size)
    runtime_filters = normalize_filters(filters)
    with database.connect() as connection:
        context = version_context(database, connection, dashboard_id, version_id)
        where_sql, params = record_where(
            database,
            context["source_ids"],
            context["filters"],
            runtime_filters,
        )
        total = int(
            connection.execute(
                f"SELECT COUNT(*) FROM classification_result_records r "
                f"WHERE {where_sql}",
                tuple(params),
            ).fetchone()[0]
        )
        rows = connection.execute(
            f"""
            SELECT r.*, u.processing_status, u.problem_labels_json,
                   u.classification_json, standard.snapshot_json AS hierarchy_snapshot_json
            FROM classification_result_records r
            JOIN classification_units u
              ON u.result_version_id = r.result_version_id
             AND u.classification_key = r.classification_key
            JOIN classification_result_versions result_version ON result_version.id = r.result_version_id
            JOIN classification_results result ON result.id = result_version.result_id
            LEFT JOIN classification_standard_versions standard ON standard.id = result.standard_version_id
            WHERE {where_sql}
            ORDER BY r.store_site ASC, r.listing ASC,
                     r.source_row ASC, r.id ASC
            LIMIT ? OFFSET ?
            """,
            (*params, page_size, (page - 1) * page_size),
        ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        snapshot = json_value(item.pop("hierarchy_snapshot_json", None), {})
        taxonomy = (
            TaxonomyConfig.model_validate(snapshot["taxonomy"]) if snapshot else None
        )
        items.append(enrich_record(serialize_record(item), taxonomy))
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def build_drilldown(
    database: Database,
    dashboard_id: str,
    version_id: str,
    group_by: str,
    *,
    page: int = 1,
    page_size: int = PAGE_SIZE_DEFAULT,
    **filters: str | None,
) -> dict[str, Any]:
    if group_by not in {"problem", *GROUP_COLUMNS}:
        raise ValueError(
            "group_by 仅支持 problem、listing、product_name、product_sku、order_id"
        )
    page, page_size = validate_page(page, page_size)
    runtime_filters = normalize_filters(filters)
    with database.connect() as connection:
        context = version_context(database, connection, dashboard_id, version_id)
        where_sql, params = record_where(
            database,
            context["source_ids"],
            context["filters"],
            runtime_filters,
        )
        if group_by == "problem":
            join_sql = """
                JOIN classification_unit_labels l
                  ON l.result_version_id = r.result_version_id
                 AND l.classification_key = r.classification_key
                 AND l.label_kind = 'problem'
            """
            group_columns = "l.label_code, l.label_name, l.label_group"
            value_columns = (
                "l.label_code AS value, l.label_name AS label_name, "
                "l.label_group AS label_group"
            )
        else:
            join_sql = ""
            column = GROUP_COLUMNS[group_by]
            group_columns = column
            value_columns = f"{column} AS value"
        base_sql = f"""
            FROM classification_result_records r
            {join_sql}
            WHERE {where_sql}
            GROUP BY {group_columns}
        """
        total = int(
            connection.execute(
                f"SELECT COUNT(*) FROM (SELECT 1 {base_sql})",
                tuple(params),
            ).fetchone()[0]
        )
        rows = connection.execute(
            f"""
            SELECT {value_columns}, COUNT(r.id) AS record_count,
                   COUNT(DISTINCT r.result_version_id || ':' ||
                         r.classification_key) AS unit_count
            {base_sql}
            ORDER BY record_count DESC, value COLLATE NOCASE ASC, value ASC
            LIMIT ? OFFSET ?
            """,
            (*params, page_size, (page - 1) * page_size),
        ).fetchall()
    return {
        "group_by": group_by,
        "items": [dict(row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
