from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any

from web_backend.common import json_value
from web_backend.dashboard_common import (
    COMMENT_SUMMARY_STATUSES,
    PLAN_VERSION,
    classification_comment_status,
)
from web_backend.dashboard_support import (
    mixed_hierarchy,
    normalize_filters,
    record_where,
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
    placeholders = ",".join("?" for _ in clean_ids)
    rows = connection.execute(
        f"""
        SELECT v.id AS result_version_id, v.result_id, v.version_no,
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
               COALESCE((
                   SELECT COUNT(DISTINCT revision.review_record_id)
                   FROM review_batches batch
                   JOIN review_records review ON review.batch_id = batch.id
                   JOIN review_revisions revision
                     ON revision.review_record_id = review.id
                   WHERE batch.published_version_id = v.id
                     AND (
                         json_extract(
                             revision.before_json, '$.semantic_units'
                         ) IS NOT json_extract(
                             revision.after_json, '$.semantic_units'
                         )
                         OR json_extract(
                             revision.before_json, '$.unknown_semantics'
                         ) IS NOT json_extract(
                             revision.after_json, '$.unknown_semantics'
                         )
                         OR json_extract(
                             revision.before_json, '$.problem_label_codes'
                         ) IS NOT json_extract(
                             revision.after_json, '$.problem_label_codes'
                         )
                         OR json_extract(
                             revision.before_json, '$.positive_label_codes'
                         ) IS NOT json_extract(
                             revision.after_json, '$.positive_label_codes'
                         )
                         OR json_extract(
                             revision.before_json, '$.primary_label_codes'
                         ) IS NOT json_extract(
                             revision.after_json, '$.primary_label_codes'
                         )
                     )
               ), 0) AS review_changed_unit_count
        FROM classification_result_versions v
        JOIN classification_results r ON r.id = v.result_id
        JOIN dataset_versions source_version
          ON source_version.id = r.dataset_version_id
        JOIN datasets source_dataset
          ON source_dataset.id = source_version.dataset_id
        JOIN dataset_versions product_version
          ON product_version.id = r.product_version_id
        JOIN datasets product_dataset
          ON product_dataset.id = product_version.dataset_id
        LEFT JOIN users creator ON creator.id = v.created_by
        WHERE v.id IN ({placeholders})
        ORDER BY v.id
        """,
        tuple(clean_ids),
    ).fetchall()
    sources = [dict(row) for row in rows]
    found_ids = {str(row["result_version_id"]) for row in sources}
    blockers: list[dict[str, Any]] = [
        {
            "type": "not_found",
            "result_version_id": version_id,
            "message": "分类结果版本不存在",
        }
        for version_id in clean_ids
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
    by_scope: dict[tuple[Any, Any], list[str]] = {}
    for source in sources:
        scope = (source["store_site"], source["listing"])
        by_scope.setdefault(scope, []).append(str(source["result_version_id"]))
    conflicts = [
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
    eligible_sources = [
        source
        for source in sources
        if source["publish_status"] == "published"
        and source["quality_status"] in {"ready", "review_required"}
    ]
    eligible_ids = [str(source["result_version_id"]) for source in eligible_sources]
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
    summary = summarize_sources(
        database,
        connection,
        eligible_ids,
        normalized_filters,
        eligible_sources,
    )
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
                "parent_version_id",
            )
        }
        for source in sources
    ]
    hash_payload = {
        "version": PLAN_VERSION,
        "result_version_ids": clean_ids,
        "filters": normalized_filters,
        "sources": hash_sources,
        "blockers": blockers,
        "warnings": warnings,
        "conflicts": conflicts,
    }
    plan_hash = hashlib.sha256(
        json.dumps(
            hash_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return {
        "plan_hash": plan_hash,
        "ready": not blockers and not conflicts,
        "blockers": blockers,
        "warnings": warnings,
        "conflicts": conflicts,
        "sources": sources,
        "filters": normalized_filters,
        "summary": summary,
    }


def summarize_sources(
    database: Database,
    connection: sqlite3.Connection,
    source_ids: list[str],
    filters: dict[str, list[str]],
    sources: list[dict[str, Any]],
    *,
    include_comment_metrics: bool = True,
) -> dict[str, Any]:
    if source_ids:
        where_sql, params = record_where(database, source_ids, filters)
        row = connection.execute(
            f"""
            SELECT COUNT(*) AS record_count,
                   COUNT(DISTINCT r.result_version_id || ':' ||
                         r.classification_key) AS unit_count,
                   SUM(CASE WHEN r.product_name IS NULL
                                 OR TRIM(r.product_name) = ''
                            THEN 1 ELSE 0 END) AS product_name_missing_count,
                   SUM(CASE WHEN r.product_match_status != 'matched'
                            THEN 1 ELSE 0 END) AS product_unmatched_count
            FROM classification_result_records r
            WHERE {where_sql}
            """,
            tuple(params),
        ).fetchone()
        record_count = int(row["record_count"] or 0)
        unit_count = int(row["unit_count"] or 0)
        missing_count = int(row["product_name_missing_count"] or 0)
        unmatched_count = int(row["product_unmatched_count"] or 0)
    else:
        record_count = unit_count = missing_count = unmatched_count = 0
    summary = {
        "source_count": len(source_ids),
        "store_count": len(
            {source["store_site"] for source in sources if source["store_site"]}
        ),
        "listing_count": len(
            {(source["store_site"], source["listing"]) for source in sources}
        ),
        "record_count": record_count,
        "unit_count": unit_count,
        "comment_count": 0,
        "total_comment_count": 0,
        "pending_review_comment_count": 0,
        "comment_statuses": [
            {"status": status, "comment_count": 0}
            for status in COMMENT_SUMMARY_STATUSES
        ],
        "product_name_missing_count": missing_count,
        "product_unmatched_count": unmatched_count,
        "review_changed_unit_count": sum(
            int(source.get("review_changed_unit_count") or 0) for source in sources
        ),
        "taxonomy_versions": sorted(
            {
                str(source["taxonomy_version"])
                for source in sources
                if source.get("taxonomy_version")
            }
        ),
    }
    if source_ids:
        scope_filters = {
            key: value for key, value in filters.items() if key != "quality_status"
        }
        scope_where, scope_params = record_where(
            database,
            source_ids,
            scope_filters,
        )
        if include_comment_metrics:
            summary.update(
                comment_summary_metrics(
                    connection,
                    where_sql,
                    params,
                    scope_where,
                    scope_params,
                )
            )
        coverage = connection.execute(
            f"""
            SELECT COUNT(*) AS total_record_count,
                   SUM(CASE WHEN r.quality_status = 'excluded'
                            THEN 1 ELSE 0 END) AS excluded_record_count,
                   SUM(CASE WHEN r.quality_status NOT IN ('ready', 'excluded')
                            THEN 1 ELSE 0 END) AS pending_review_record_count
            FROM classification_result_records r
            WHERE {scope_where}
            """,
            tuple(scope_params),
        ).fetchone()
        total_record_count = int(coverage["total_record_count"] or 0)
        excluded_record_count = int(coverage["excluded_record_count"] or 0)
        pending_review_record_count = int(coverage["pending_review_record_count"] or 0)
        if (
            total_record_count != record_count
            or excluded_record_count
            or pending_review_record_count
        ):
            summary.update(
                {
                    "total_record_count": total_record_count,
                    "pending_review_record_count": pending_review_record_count,
                    "excluded_record_count": excluded_record_count,
                    "coverage_rate": round(
                        record_count * 100 / total_record_count,
                        2,
                    )
                    if total_record_count
                    else 0,
                }
            )
    return summary


def comment_summary_metrics(
    connection: sqlite3.Connection,
    where_sql: str,
    params: list[Any],
    total_where_sql: str,
    total_params: list[Any],
) -> dict[str, Any]:
    rows = connection.execute(
        f"""
        SELECT u.classification_json, COUNT(r.id) AS comment_count
        FROM classification_result_records r
        JOIN classification_units u
          ON u.result_version_id = r.result_version_id
         AND u.classification_key = r.classification_key
        WHERE {where_sql}
        GROUP BY r.result_version_id, r.classification_key
        """,
        tuple(params),
    ).fetchall()
    status_counts = {status: 0 for status in COMMENT_SUMMARY_STATUSES}
    for row in rows:
        payload = json_value(row["classification_json"], {})
        status = classification_comment_status(payload)
        status_counts[status] += int(row["comment_count"] or 0)

    coverage = connection.execute(
        f"""
        SELECT COALESCE(SUM(comment_count), 0) AS total_comment_count,
               COALESCE(SUM(
                   CASE WHEN pending_review = 1 THEN comment_count ELSE 0 END
               ), 0) AS pending_review_comment_count
        FROM (
            SELECT COUNT(r.id) AS comment_count,
                   MAX(
                       CASE WHEN u.quality_status NOT IN ('ready', 'excluded')
                            THEN 1 ELSE 0 END
                   ) AS pending_review
            FROM classification_result_records r
            JOIN classification_units u
              ON u.result_version_id = r.result_version_id
             AND u.classification_key = r.classification_key
            WHERE {total_where_sql}
            GROUP BY r.result_version_id, r.classification_key
        ) scoped_comments
        """,
        tuple(total_params),
    ).fetchone()
    return {
        "comment_count": sum(int(row["comment_count"] or 0) for row in rows),
        "total_comment_count": int(coverage["total_comment_count"] or 0),
        "pending_review_comment_count": int(
            coverage["pending_review_comment_count"] or 0
        ),
        "comment_statuses": [
            {"status": status, "comment_count": status_counts[status]}
            for status in COMMENT_SUMMARY_STATUSES
        ],
    }
