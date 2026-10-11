"""把商品展示字段筛选绑定到商品关联，避免改名改变统计对象。"""

from __future__ import annotations

import sqlite3
from typing import Any

from web_backend.common import json_text, json_value

PRODUCT_SCOPE = "_product_scope"
PRODUCT_FILTERS = {"product_name", "product_sku"}


def bind_product_scope(
    connection: sqlite3.Connection,
    source_ids: list[str],
    filters: dict[str, list[str]],
) -> dict[str, list[str]]:
    if PRODUCT_SCOPE in filters or not PRODUCT_FILTERS.intersection(filters):
        return filters
    conditions = ["r.result_version_id IN (" + ",".join("?" for _ in source_ids) + ")"]
    params: list[Any] = list(source_ids)
    for name in sorted(PRODUCT_FILTERS.intersection(filters)):
        values = filters[name]
        conditions.append(f"r.{name} IN ({','.join('?' for _ in values)})")
        params.extend(values)
    rows = connection.execute(
        "SELECT DISTINCT p.dataset_id, r.store_site, r.matched_msku "
        "FROM classification_result_records r "
        "JOIN classification_result_versions v ON v.id = r.result_version_id "
        "JOIN classification_results c ON c.id = v.result_id "
        "JOIN dataset_versions p ON p.id = c.product_version_id "
        "WHERE " + " AND ".join(conditions),
        params,
    ).fetchall()
    return {**filters, PRODUCT_SCOPE: sorted(json_text(list(row)) for row in rows)}


def product_scope_where(values: list[str], params: list[Any]) -> str:
    if not values:
        return "0 = 1"
    params.append(json_text(values))
    return """
    EXISTS (
        SELECT 1 FROM classification_result_versions scope_version
        JOIN classification_results scope_result ON scope_result.id = scope_version.result_id
        JOIN dataset_versions scope_product ON scope_product.id = scope_result.product_version_id
        LEFT JOIN product_identity_aliases actual_alias
          ON actual_alias.dataset_id = scope_product.dataset_id
         AND actual_alias.store_site = r.store_site AND actual_alias.msku = r.matched_msku
        JOIN json_each(?) selected
        LEFT JOIN product_identity_aliases selected_alias
          ON selected_alias.dataset_id = json_extract(selected.value, '$[0]')
         AND selected_alias.store_site = json_extract(selected.value, '$[1]')
         AND selected_alias.msku = json_extract(selected.value, '$[2]')
        WHERE scope_version.id = r.result_version_id
          AND scope_product.dataset_id = json_extract(selected.value, '$[0]')
          AND COALESCE(actual_alias.current_store, r.store_site) =
              COALESCE(selected_alias.current_store, json_extract(selected.value, '$[1]'))
          AND COALESCE(actual_alias.current_msku, r.matched_msku) =
              COALESCE(selected_alias.current_msku, json_extract(selected.value, '$[2]'))
    )
    """


def capture_dashboard_product_scopes(
    connection: sqlite3.Connection, dataset_id: str
) -> dict[str, dict[str, list[str]]]:
    rows = connection.execute(
        """SELECT DISTINCT d.id, data.id AS dataset_version_id, data.filters_json
        FROM analysis_dashboards d
        JOIN dashboard_versions v ON v.id = d.current_version_id
        JOIN dashboard_dataset_versions data ON data.id = v.dataset_version_id
        JOIN dashboard_dataset_sources s ON s.dataset_version_id = data.id
        JOIN classification_result_versions r ON r.id = s.result_version_id
        JOIN classification_results c ON c.id = r.result_id
        JOIN dataset_versions p ON p.id = c.product_version_id
        WHERE d.status = 'active' AND p.dataset_id = ?""",
        (dataset_id,),
    ).fetchall()
    output = {}
    for row in rows:
        sources = connection.execute(
            "SELECT result_version_id FROM dashboard_dataset_sources WHERE dataset_version_id = ?",
            (row["dataset_version_id"],),
        ).fetchall()
        output[row["id"]] = bind_product_scope(
            connection,
            [item[0] for item in sources],
            json_value(row["filters_json"], {}),
        )
    return output
