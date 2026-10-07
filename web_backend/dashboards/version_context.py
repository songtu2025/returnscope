from __future__ import annotations

import sqlite3
from typing import Any

from return_semantics.analysis_context import aggregate_analysis_context
from web_backend.common import json_value
from web_backend.dashboard_common import FEEDBACK_GROUP_BASIS, DashboardNotFound
from web_backend.database import Database
from web_backend.result_hierarchy import result_taxonomy
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
    summary = json_value(version["summary_json"], {})
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
        "summary": summary,
        "sources": sources,
        "source_ids": [str(source["result_version_id"]) for source in sources],
        "counting_basis": (
            FEEDBACK_GROUP_BASIS
            if summary.get("counting_basis") == FEEDBACK_GROUP_BASIS
            else "source_record"
        ),
        "analysis_context": aggregate_analysis_context(
            source.get("analysis_context") for source in sources
        ),
    }


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
