from __future__ import annotations

import sqlite3
from typing import Any

from return_semantics.schemas import TaxonomyConfig
from return_semantics.taxonomy_hierarchy import descendant_label_codes
from web_backend.dashboard_common import (
    ALLOWED_FILTERS,
    FILTER_COLUMNS,
    QUALITY_STATUSES,
)
from web_backend.database import Database
from web_backend.result_hierarchy import feedback_group_key_sql, result_taxonomy


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
                where.append(_problem_where(database, source_ids, values, params))
            else:
                where.append(f"r.{FILTER_COLUMNS[key]} IN ({placeholders})")
                params.extend(values)
    return " AND ".join(where), params


def _problem_where(
    database: Database,
    source_ids: list[str],
    values: list[str],
    params: list[Any],
) -> str:
    """按来源标准展开问题标签，保持参数与查询顺序。"""
    scoped = []
    with database.connect() as connection:
        for source in source_ids:
            taxonomy = result_taxonomy(connection, source)
            codes = _problem_label_codes(taxonomy, values)
            code_placeholders = ",".join("?" for _ in codes)
            scoped.append(
                f"(f.result_version_id = ? AND f.label_code IN ({code_placeholders}))"
            )
            params.extend([source, *codes])
    return (
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


def _problem_label_codes(
    taxonomy: TaxonomyConfig | None, values: list[str]
) -> list[str]:
    """保留未知标签，并对后代标签去重排序。"""
    return sorted(
        {
            code
            for value in values
            for code in (
                descendant_label_codes(taxonomy, value) or [value]
                if taxonomy
                else [value]
            )
        }
    )
