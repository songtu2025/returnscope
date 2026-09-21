from __future__ import annotations

from typing import Any

from web_backend.dashboard_common import TEXT_ENCODING_ANOMALY
from web_backend.dashboard_plan import summarize_sources
from web_backend.dashboard_support import (
    feedback_group_scope,
    percentage,
    record_where,
    version_context,
)
from web_backend.database import Database


def build_summary(
    database: Database, dashboard_id: str, version_id: str
) -> dict[str, Any]:
    with database.connect() as connection:
        context = version_context(database, connection, dashboard_id, version_id)
        summary = summarize_sources(
            database,
            connection,
            context["source_ids"],
            context["filters"],
            context["sources"],
            include_comment_metrics=False,
            feedback_groups=context["counting_basis"] == "feedback_group",
        )
    return {
        "dashboard_id": dashboard_id,
        "version_id": version_id,
        "dataset_version_id": context["dataset_version_id"],
        **summary,
    }


def build_review_bias(
    database: Database, dashboard_id: str, version_id: str
) -> dict[str, Any]:
    with database.connect() as connection:
        context = version_context(database, connection, dashboard_id, version_id)
        scope_filters = {
            key: value
            for key, value in context["filters"].items()
            if key != "quality_status"
        }
        where_sql, params = record_where(
            database,
            context["source_ids"],
            scope_filters,
        )
        if context["counting_basis"] == "feedback_group":
            where_sql, params = feedback_group_scope(
                connection, where_sql, params, name="main"
            )
        overall = connection.execute(
            f"""
            SELECT COUNT(*) AS total_record_count,
                   SUM(CASE WHEN r.quality_status NOT IN ('ready', 'excluded')
                            THEN 1 ELSE 0 END) AS pending_record_count
            FROM classification_result_records r
            WHERE {where_sql}
            """,
            tuple(params),
        ).fetchone()
        total = int(overall["total_record_count"] or 0)
        pending = int(overall["pending_record_count"] or 0)
        if not total or not pending:
            return {
                "status": "not_applicable",
                "total_record_count": total,
                "pending_record_count": pending,
                "pending_rate": percentage(pending, total),
                "concentrated_products": [],
                "note": "当前范围没有待审核记录，无需评估选择偏差。",
            }
        rows = connection.execute(
            f"""
            SELECT COALESCE(NULLIF(TRIM(r.product_name), ''), '未匹配商品')
                       AS value,
                   COUNT(*) AS total_record_count,
                   SUM(CASE WHEN r.quality_status NOT IN ('ready', 'excluded')
                            THEN 1 ELSE 0 END) AS pending_record_count
            FROM classification_result_records r
            WHERE {where_sql}
            GROUP BY value
            HAVING COUNT(*) >= 10 AND pending_record_count >= 5
            ORDER BY pending_record_count DESC, value COLLATE NOCASE ASC
            LIMIT 10
            """,
            tuple(params),
        ).fetchall()
    overall_rate = percentage(pending, total)
    concentrated = []
    for row in rows:
        product_total = int(row["total_record_count"] or 0)
        product_pending = int(row["pending_record_count"] or 0)
        product_rate = percentage(product_pending, product_total)
        if product_rate >= overall_rate + 10:
            concentrated.append(
                {
                    "value": str(row["value"]),
                    "total_record_count": product_total,
                    "pending_record_count": product_pending,
                    "pending_rate": product_rate,
                    "difference_percentage_points": round(
                        product_rate - overall_rate,
                        2,
                    ),
                }
            )
    return {
        "status": "concentrated" if concentrated else "not_detected",
        "total_record_count": total,
        "pending_record_count": pending,
        "pending_rate": overall_rate,
        "concentrated_products": concentrated,
        "note": (
            "待审核记录在部分商品中明显集中，已审核样本可能存在选择偏差。"
            if concentrated
            else "暂未发现待审核记录在商品维度明显集中。"
        ),
    }


def build_text_quality(
    database: Database, dashboard_id: str, version_id: str
) -> dict[str, Any]:
    with database.connect() as connection:
        context = version_context(database, connection, dashboard_id, version_id)
        where_sql, params = record_where(
            database,
            context["source_ids"],
            context["filters"],
        )
        rows = connection.execute(
            f"""
            SELECT r.comment
            FROM classification_result_records r
            WHERE {where_sql}
              AND r.comment IS NOT NULL
              AND TRIM(r.comment) <> ''
            """,
            tuple(params),
        ).fetchall()
    comments = [str(row["comment"]) for row in rows]
    anomalies = [
        comment for comment in comments if TEXT_ENCODING_ANOMALY.search(comment)
    ]
    count = len(anomalies)
    total = len(comments)
    return {
        "status": "needs_review" if count else "passed",
        "anomaly_record_count": count,
        "anomaly_rate": percentage(count, total),
        "checked_record_count": total,
        "examples": anomalies[:5],
        "note": (
            f"发现 {count} 条疑似编码异常评论，重新导入原始数据前，"
            "不应生成商品级行动建议。"
            if count
            else "未发现明显的评论编码异常。"
        ),
    }


def list_sources(
    database: Database, dashboard_id: str, version_id: str
) -> list[dict[str, Any]]:
    with database.connect() as connection:
        context = version_context(database, connection, dashboard_id, version_id)
    return context["sources"]
