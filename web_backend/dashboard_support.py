from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any

from return_semantics.analysis_context import aggregate_analysis_context
from return_semantics.taxonomy_hierarchy import descendant_label_codes
from web_backend.common import json_value
from web_backend.dashboard_common import (
    ALLOWED_FILTERS,
    FEEDBACK_GROUP_BASIS,
    FILTER_COLUMNS,
    PAGE_SIZE_MAX,
    QUALITY_STATUSES,
    DashboardNotFound,
)
from web_backend.database import Database
from web_backend.result_hierarchy import feedback_group_key_sql, result_taxonomy
from web_backend.review_statistics_sql import REVIEW_CHANGED_UNIT_COUNT_SQL

DASHBOARD_SOURCE_COLUMNS_SQL = f"""
    v.id AS result_version_id, v.result_id, v.version_no,
    v.content_hash, v.publish_status, v.quality_status,
    v.unit_count, v.record_count, v.parent_version_id,
    v.created_by, creator.display_name AS created_by_name,
    v.created_at, v.published_at,
    r.dataset_version_id, r.product_version_id,
    source_dataset.name AS dataset_name,
    source_version.version AS dataset_version,
    product_dataset.name AS product_dataset_name,
    product_version.version AS product_version,
    r.store_site, r.listing, r.agent_key, r.agent_family,
    r.logic_version, r.taxonomy_version, r.standard_version_id,
    r.model_policy_version, r.claims_version,
    COALESCE(
        json_extract(task.snapshot_json, '$.analysis_context'),
        'returns'
    ) AS analysis_context,
    {REVIEW_CHANGED_UNIT_COUNT_SQL} AS review_changed_unit_count
"""

DASHBOARD_SOURCE_JOINS_SQL = """
JOIN classification_results r ON r.id = v.result_id
JOIN dataset_versions source_version
  ON source_version.id = r.dataset_version_id
JOIN datasets source_dataset
  ON source_dataset.id = source_version.dataset_id
JOIN dataset_versions product_version
  ON product_version.id = r.product_version_id
JOIN datasets product_dataset
  ON product_dataset.id = product_version.dataset_id
LEFT JOIN tasks task ON task.id = r.source_task_id
LEFT JOIN users creator ON creator.id = v.created_by
"""


def version_context(
    database: Database,
    connection: sqlite3.Connection,
    dashboard_id: str,
    version_id: str,
) -> dict[str, Any]:
    version = version_row(connection, dashboard_id, version_id)
    source_rows = connection.execute(
        f"""
        SELECT {DASHBOARD_SOURCE_COLUMNS_SQL}
        FROM dashboard_dataset_sources source
        JOIN classification_result_versions v
          ON v.id = source.result_version_id
        {DASHBOARD_SOURCE_JOINS_SQL}
        WHERE source.dataset_version_id = ?
        ORDER BY r.store_site ASC, r.listing ASC, v.id ASC
        """,
        (version["dataset_version_id"],),
    ).fetchall()
    sources = [dict(row) for row in source_rows]
    return {
        "dataset_version_id": str(version["dataset_version_id"]),
        "filters": json_value(version["filters_json"], {}),
        "sources": sources,
        "source_ids": [str(source["result_version_id"]) for source in sources],
        "counting_basis": (
            FEEDBACK_GROUP_BASIS
            if json_value(version["summary_json"], {}).get("counting_basis")
            == FEEDBACK_GROUP_BASIS
            else "source_record"
        ),
        "analysis_context": aggregate_analysis_context(
            source.get("analysis_context") for source in sources
        ),
    }


def feedback_group_scope(
    connection: sqlite3.Connection,
    where_sql: str,
    params: list[Any],
    *,
    name: str,
) -> tuple[str, list[Any]]:
    """在当前查询筛选之后，每个反馈组只取一条代表明细。"""
    if name not in {"main", "options", "cases"}:
        raise ValueError("反馈组查询范围不合法")
    table = f"dashboard_feedback_{name}"
    connection.execute(f"CREATE TEMP TABLE IF NOT EXISTS {table}(id TEXT PRIMARY KEY)")
    connection.execute(f"DELETE FROM {table}")
    connection.execute(
        f"""
        INSERT INTO {table}(id)
        SELECT id FROM (
            SELECT r.id,
                   ROW_NUMBER() OVER (
                       PARTITION BY {feedback_group_key_sql("r")}
                       ORDER BY r.source_row ASC, r.id ASC
                   ) AS group_rank
            FROM classification_result_records r
            WHERE {where_sql}
        ) WHERE group_rank = 1
        """,
        tuple(params),
    )
    return f"r.id IN (SELECT id FROM {table})", []


def version_row(
    connection: sqlite3.Connection,
    dashboard_id: str,
    version_id: str | None,
) -> sqlite3.Row:
    if not version_id:
        raise DashboardNotFound("分析看板还没有可用版本")
    row = connection.execute(
        f"""
        {version_select()}
        WHERE v.id = ? AND v.dashboard_id = ?
        """,
        (version_id, dashboard_id),
    ).fetchone()
    if row is None:
        raise DashboardNotFound("分析看板版本不存在")
    return row


def version_select() -> str:
    return """
        SELECT v.id AS version_id, v.dashboard_id,
               v.version_no AS version, v.dataset_version_id,
               v.reason, v.created_by, creator.display_name AS created_by_name,
               v.created_at, data.plan_hash, data.filters_json,
               data.source_snapshot_json, data.summary_json
        FROM dashboard_versions v
        JOIN dashboard_dataset_versions data
          ON data.id = v.dataset_version_id
        LEFT JOIN users creator ON creator.id = v.created_by
    """


def serialize_version(value: dict[str, Any]) -> dict[str, Any]:
    value["filters"] = json_value(value.pop("filters_json", None), {})
    value["source_snapshot"] = json_value(
        value.pop("source_snapshot_json", None),
        [],
    )
    value["summary"] = json_value(value.pop("summary_json", None), {})
    return value


def serialize_dashboard_list(value: dict[str, Any]) -> dict[str, Any]:
    value["summary"] = json_value(value.pop("summary_json", None), {})
    return value


def mixed_hierarchy(
    connection: sqlite3.Connection, sources: list[dict[str, Any]]
) -> bool:
    versions = {source.get("standard_version_id") for source in sources}
    if len(versions) < 2:
        return False
    return any(
        taxonomy is not None and taxonomy.structure_version == 2
        for taxonomy in (
            result_taxonomy(connection, source["result_version_id"])
            for source in sources
        )
    )


def normalize_filters(filters: dict[str, Any]) -> dict[str, list[str]]:
    unknown = sorted(set(filters) - ALLOWED_FILTERS)
    if unknown:
        raise ValueError(f"不支持的筛选字段：{', '.join(unknown)}")
    output: dict[str, list[str]] = {}
    for key in sorted(filters):
        raw_value = filters[key]
        values = raw_value if isinstance(raw_value, list) else [raw_value]
        clean_values = sorted(
            {
                str(value).strip()
                for value in values
                if value is not None and str(value).strip()
            }
        )
        if clean_values:
            output[key] = clean_values
    invalid_quality = set(output.get("quality_status", [])) - QUALITY_STATUSES
    if invalid_quality:
        raise ValueError("quality_status 不合法")
    return output


def record_where(
    database: Database,
    source_ids: list[str],
    *filter_sets: dict[str, list[str]],
) -> tuple[str, list[Any]]:
    if not source_ids:
        return "0 = 1", []
    where = ["r.result_version_id IN (" + ",".join("?" for _ in source_ids) + ")"]
    params: list[Any] = list(source_ids)
    for filters in filter_sets:
        for key, values in filters.items():
            placeholders = ",".join("?" for _ in values)
            if key == "problem":
                scoped = []
                with database.connect() as connection:
                    for source in source_ids:
                        taxonomy = result_taxonomy(connection, source)
                        codes = sorted(
                            {
                                code
                                for value in values
                                for code in (
                                    (descendant_label_codes(taxonomy, value) or [value])
                                    if taxonomy
                                    else [value]
                                )
                            }
                        )
                        code_placeholders = ",".join("?" for _ in codes)
                        scoped.append(
                            f"(f.result_version_id = ? AND f.label_code IN ({code_placeholders}))"
                        )
                        params.extend([source, *codes])
                where.append(
                    """
                    EXISTS (
                        SELECT 1 FROM classification_unit_labels f
                        WHERE f.result_version_id = r.result_version_id
                          AND f.classification_key = r.classification_key
                          AND f.label_kind = 'problem'
                          AND ("""
                    + " OR ".join(scoped)
                    + ") )"
                )
            else:
                where.append(f"r.{FILTER_COLUMNS[key]} IN ({placeholders})")
                params.extend(values)
    return " AND ".join(where), params


def serialize_record(value: dict[str, Any]) -> dict[str, Any]:
    value["problem_labels"] = json_value(
        value.pop("problem_labels_json", None),
        [],
    )
    classification = json_value(value.pop("classification_json", None), {})
    value["classification"] = classification
    value["evidence"] = [
        unit.get("evidence")
        for unit in classification.get("semantic_units", [])
        if unit.get("evidence")
    ]
    return value


def clean_date(value: str | None) -> str:
    clean_value = (value or "").strip()
    if not clean_value:
        return ""
    try:
        return date.fromisoformat(clean_value).isoformat()
    except ValueError as exc:
        raise ValueError("日期必须使用 YYYY-MM-DD 格式") from exc


def percentage(numerator: int, denominator: int) -> float:
    return round(numerator * 100 / denominator, 1) if denominator else 0.0


def validate_page(page: int, page_size: int) -> tuple[int, int]:
    if page < 1:
        raise ValueError("page 必须大于等于 1")
    if not 1 <= page_size <= PAGE_SIZE_MAX:
        raise ValueError(f"page_size 必须在 1 到 {PAGE_SIZE_MAX} 之间")
    return page, page_size


def contains_pattern(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%")
    escaped = escaped.replace("_", "\\_")
    return f"%{escaped}%"
