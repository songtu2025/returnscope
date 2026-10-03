from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any

from web_backend.dashboard_common import (
    PLAN_VERSION,
)
from web_backend.dashboard_summary import (
    comment_summary_metrics as comment_summary_metrics,
)
from web_backend.dashboard_summary import summarize_sources as summarize_sources
from web_backend.dashboard_support import (
    DASHBOARD_SOURCE_COLUMNS_SQL,
    DASHBOARD_SOURCE_JOINS_SQL,
    mixed_hierarchy,
    normalize_filters,
)
from web_backend.database import Database


def build_plan(
    database: Database,
    connection: sqlite3.Connection,
    result_version_ids: list[str],
    filters: dict[str, Any],
) -> dict[str, Any]:
    clean_ids = sorted(
        {str(value).strip() for value in result_version_ids if str(value).strip()}
    )
    if not clean_ids:
        raise ValueError("result_version_ids 至少需要一个有效值")
    normalized_filters = normalize_filters(filters)
    sources = _load_sources(connection, clean_ids)
    blockers, warnings, eligible_sources = _source_issues(
        connection, clean_ids, sources
    )
    conflicts = _scope_conflicts(sources)
    eligible_ids = [str(source["result_version_id"]) for source in eligible_sources]
    _apply_quality_scope(connection, eligible_ids, normalized_filters, warnings)
    summary = summarize_sources(
        database,
        connection,
        eligible_ids,
        normalized_filters,
        eligible_sources,
        feedback_groups=True,
    )
    plan = {
        "ready": not blockers and not conflicts,
        "blockers": blockers,
        "warnings": warnings,
        "conflicts": conflicts,
        "sources": sources,
        "filters": normalized_filters,
        "summary": summary,
    }
    return {"plan_hash": _plan_hash(clean_ids, plan), **plan}


def _load_sources(
    connection: sqlite3.Connection,
    version_ids: list[str],
) -> list[dict[str, Any]]:
    placeholders = ",".join("?" for _ in version_ids)
    rows = connection.execute(
        f"""
        SELECT {DASHBOARD_SOURCE_COLUMNS_SQL}
        FROM classification_result_versions v
        {DASHBOARD_SOURCE_JOINS_SQL}
        WHERE v.id IN ({placeholders})
        ORDER BY v.id
        """,
        tuple(version_ids),
    ).fetchall()
    return [dict(row) for row in rows]


def _source_issues(
    connection: sqlite3.Connection,
    requested_ids: list[str],
    sources: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    found_ids = {str(row["result_version_id"]) for row in sources}
    blockers: list[dict[str, Any]] = [
        {
            "type": "not_found",
            "result_version_id": version_id,
            "message": "分类结果版本不存在",
        }
        for version_id in requested_ids
        if version_id not in found_ids
    ]
    if mixed_hierarchy(connection, sources):
        blockers.append(
            {
                "type": "incompatible_hierarchy_versions",
                "message": "层级框架必须按标准版本分别建立看板，不能合并不同标准版本的标签。",
            }
        )
    warnings: list[dict[str, Any]] = []
    for source in sources:
        if source["publish_status"] != "published":
            blockers.append(
                {
                    "type": "not_published",
                    "result_version_id": source["result_version_id"],
                    "message": "分类结果版本尚未发布",
                }
            )
        if source["quality_status"] == "review_required":
            warnings.append(
                {
                    "type": "quality_review_pending",
                    "result_version_id": source["result_version_id"],
                    "quality_status": source["quality_status"],
                    "message": (
                        "该版本仍有待复核数据；看板仅统计质量状态为 ready 的记录"
                    ),
                }
            )
        elif source["quality_status"] != "ready":
            blockers.append(
                {
                    "type": "quality_not_ready",
                    "result_version_id": source["result_version_id"],
                    "quality_status": source["quality_status"],
                    "message": "分类结果质量状态不是 ready",
                }
            )
    eligible_sources = [
        source
        for source in sources
        if source["publish_status"] == "published"
        and source["quality_status"] in {"ready", "review_required"}
    ]
    return blockers, warnings, eligible_sources


def _scope_conflicts(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_scope: dict[tuple[Any, Any], list[str]] = {}
    for source in sources:
        scope = (source["store_site"], source["listing"])
        by_scope.setdefault(scope, []).append(str(source["result_version_id"]))
    return [
        {
            "type": "duplicate_store_listing",
            "store_site": scope[0],
            "listing": scope[1],
            "result_version_ids": sorted(version_ids),
        }
        for scope, version_ids in sorted(
            by_scope.items(),
            key=lambda item: (str(item[0][0] or ""), str(item[0][1] or "")),
        )
        if len(version_ids) > 1
    ]


def _apply_quality_scope(
    connection: sqlite3.Connection,
    eligible_ids: list[str],
    normalized_filters: dict[str, list[str]],
    warnings: list[dict[str, Any]],
) -> None:
    has_non_ready_records = False
    if eligible_ids:
        eligible_placeholders = ",".join("?" for _ in eligible_ids)
        has_non_ready_records = (
            connection.execute(
                f"""
            SELECT 1 FROM classification_result_records
            WHERE result_version_id IN ({eligible_placeholders})
              AND quality_status != 'ready'
            LIMIT 1
            """,
                tuple(eligible_ids),
            ).fetchone()
            is not None
        )
    if has_non_ready_records and not warnings:
        warnings.append(
            {
                "type": "quality_scope_limited",
                "message": "该版本含已排除数据；看板仅统计质量状态为 ready 的记录",
            }
        )
    if warnings or has_non_ready_records:
        normalized_filters["quality_status"] = ["ready"]


def _plan_hash(result_version_ids: list[str], plan: dict[str, Any]) -> str:
    sources = plan["sources"]
    hash_sources = [
        {
            key: source[key]
            for key in (
                "result_version_id",
                "result_id",
                "version_no",
                "content_hash",
                "publish_status",
                "quality_status",
                "dataset_version_id",
                "dataset_version",
                "dataset_name",
                "product_version_id",
                "product_version",
                "product_dataset_name",
                "store_site",
                "listing",
                "logic_version",
                "taxonomy_version",
                "model_policy_version",
                "claims_version",
                "analysis_context",
                "parent_version_id",
            )
        }
        for source in sources
    ]
    hash_payload = {
        "version": PLAN_VERSION,
        "result_version_ids": result_version_ids,
        "filters": plan["filters"],
        "sources": hash_sources,
        "blockers": plan["blockers"],
        "warnings": plan["warnings"],
        "conflicts": plan["conflicts"],
    }
    return hashlib.sha256(
        json.dumps(
            hash_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
