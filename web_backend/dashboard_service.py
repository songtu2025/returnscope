from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import date
from typing import Any

from web_backend.common import json_text, json_value, new_id
from web_backend.database import Database
from web_backend.security import utc_now

PAGE_SIZE_DEFAULT = 50
PAGE_SIZE_MAX = 200
PLAN_VERSION = "dashboard-dataset-plan-v1"
QUALITY_STATUSES = {"ready", "review_required", "unusable", "excluded"}
FILTER_COLUMNS = {
    "listing": "listing",
    "product_name": "product_name",
    "product_sku": "product_sku",
    "order_id": "order_id",
    "quality_status": "quality_status",
}
ALLOWED_FILTERS = {"problem", *FILTER_COLUMNS}
GROUP_COLUMNS = {
    "listing": "r.listing",
    "product_name": "r.product_name",
    "product_sku": "r.product_sku",
    "order_id": "r.order_id",
}
SUBJECT_LABELS = {
    "PRODUCT": "商品相关",
    "CUSTOMER": "顾客相关",
    "ORDER": "订单相关",
    "DELIVERY": "配送相关",
}
TEXT_ENCODING_ANOMALY = re.compile(
    r"(?:[A-Za-z][\u4e00-\u9fff]|[\u4e00-\u9fff][A-Za-z])"
)


class DashboardConflict(ValueError):
    pass


class DashboardNotFound(ValueError):
    pass


class DashboardService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def preflight(
        self,
        result_version_ids: list[str],
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self.database.connect() as connection:
            return self._build_plan(connection, result_version_ids, filters or {})

    def create(
        self,
        *,
        name: str,
        description: str,
        result_version_ids: list[str],
        filters: dict[str, Any],
        plan_hash: str,
        reason: str,
        actor_id: str,
    ) -> dict[str, Any]:
        dashboard_id = new_id("dashboard")
        with self.database.transaction(immediate=True) as connection:
            plan = self._build_plan(connection, result_version_ids, filters)
            self._require_ready_plan(plan, plan_hash)
            now = utc_now()
            connection.execute(
                """
                INSERT INTO analysis_dashboards(
                    id, name, description, status, revision,
                    created_by, created_at, updated_at
                ) VALUES (?, ?, ?, 'active', 1, ?, ?, ?)
                """,
                (dashboard_id, name.strip(), description.strip(), actor_id, now, now),
            )
            version_ids = self._insert_version(
                connection,
                dashboard_id=dashboard_id,
                version_no=1,
                plan=plan,
                reason=reason.strip(),
                actor_id=actor_id,
                now=now,
            )
            connection.execute(
                """
                UPDATE analysis_dashboards SET current_version_id = ?
                WHERE id = ?
                """,
                (version_ids["version_id"], dashboard_id),
            )
            self._insert_audit(
                connection,
                entity_type="analysis_dashboard",
                entity_id=dashboard_id,
                action="create",
                actor_id=actor_id,
                after={
                    **version_ids,
                    "revision": 1,
                    "plan_hash": plan["plan_hash"],
                    "reason": reason.strip(),
                },
                now=now,
            )
        return self.get(dashboard_id)

    def create_version(
        self,
        dashboard_id: str,
        *,
        expected_revision: int,
        result_version_ids: list[str],
        filters: dict[str, Any],
        plan_hash: str,
        reason: str,
        actor_id: str,
    ) -> dict[str, Any]:
        with self.database.transaction(immediate=True) as connection:
            dashboard = connection.execute(
                "SELECT * FROM analysis_dashboards WHERE id = ?",
                (dashboard_id,),
            ).fetchone()
            if dashboard is None:
                raise DashboardNotFound("分析看板不存在")
            if int(dashboard["revision"]) != expected_revision:
                raise DashboardConflict("看板已被其他用户更新，请刷新后重试")
            plan = self._build_plan(connection, result_version_ids, filters)
            self._require_ready_plan(plan, plan_hash)
            version_no = int(
                connection.execute(
                    """
                    SELECT COALESCE(MAX(version_no), 0) + 1
                    FROM dashboard_versions WHERE dashboard_id = ?
                    """,
                    (dashboard_id,),
                ).fetchone()[0]
            )
            now = utc_now()
            version_ids = self._insert_version(
                connection,
                dashboard_id=dashboard_id,
                version_no=version_no,
                plan=plan,
                reason=reason.strip(),
                actor_id=actor_id,
                now=now,
            )
            updated = connection.execute(
                """
                UPDATE analysis_dashboards
                SET current_version_id = ?, revision = revision + 1,
                    updated_at = ?
                WHERE id = ? AND revision = ?
                """,
                (
                    version_ids["version_id"],
                    now,
                    dashboard_id,
                    expected_revision,
                ),
            )
            if updated.rowcount != 1:
                raise DashboardConflict("看板已被其他用户更新，请刷新后重试")
            self._insert_audit(
                connection,
                entity_type="analysis_dashboard",
                entity_id=dashboard_id,
                action="create_version",
                actor_id=actor_id,
                before={
                    "revision": expected_revision,
                    "current_version_id": dashboard["current_version_id"],
                },
                after={
                    **version_ids,
                    "revision": expected_revision + 1,
                    "plan_hash": plan["plan_hash"],
                    "reason": reason.strip(),
                },
                now=now,
            )
        return self.get(dashboard_id, version_ids["version_id"])

    def list(
        self,
        *,
        page: int = 1,
        page_size: int = PAGE_SIZE_DEFAULT,
        q: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        page, page_size = self._validate_page(page, page_size)
        where = ["1 = 1"]
        params: list[Any] = []
        if status:
            if status not in {"active", "archived"}:
                raise ValueError("status 不合法")
            where.append("d.status = ?")
            params.append(status)
        clean_query = (q or "").strip()
        if clean_query:
            pattern = self._contains_pattern(clean_query)
            where.append(
                "(d.name LIKE ? ESCAPE '\\' OR d.description LIKE ? ESCAPE '\\')"
            )
            params.extend([pattern, pattern])
        where_sql = " AND ".join(where)
        with self.database.connect() as connection:
            total = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM analysis_dashboards d WHERE {where_sql}",
                    tuple(params),
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"""
                SELECT d.*, creator.display_name AS created_by_name,
                       v.version_no AS current_version,
                       v.dataset_version_id AS current_dataset_version_id,
                       data.plan_hash AS current_plan_hash,
                       data.summary_json
                FROM analysis_dashboards d
                LEFT JOIN users creator ON creator.id = d.created_by
                LEFT JOIN dashboard_versions v ON v.id = d.current_version_id
                LEFT JOIN dashboard_dataset_versions data
                  ON data.id = v.dataset_version_id
                WHERE {where_sql}
                ORDER BY d.updated_at DESC, d.id ASC
                LIMIT ? OFFSET ?
                """,
                (*params, page_size, (page - 1) * page_size),
            ).fetchall()
        return {
            "items": [self._serialize_dashboard_list(dict(row)) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def get(
        self,
        dashboard_id: str,
        version_id: str | None = None,
    ) -> dict[str, Any]:
        with self.database.connect() as connection:
            dashboard = connection.execute(
                """
                SELECT d.*, creator.display_name AS created_by_name
                FROM analysis_dashboards d
                LEFT JOIN users creator ON creator.id = d.created_by
                WHERE d.id = ?
                """,
                (dashboard_id,),
            ).fetchone()
            if dashboard is None:
                raise DashboardNotFound("分析看板不存在")
            selected_version = version_id or dashboard["current_version_id"]
            version = self._version_row(connection, dashboard_id, selected_version)
        output = dict(dashboard)
        output["version"] = self._serialize_version(dict(version))
        return output

    def versions(self, dashboard_id: str) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM analysis_dashboards WHERE id = ?",
                (dashboard_id,),
            ).fetchone()
            if exists is None:
                raise DashboardNotFound("分析看板不存在")
            rows = connection.execute(
                f"""
                {self._version_select()}
                WHERE v.dashboard_id = ?
                ORDER BY v.version_no DESC, v.id ASC
                """,
                (dashboard_id,),
            ).fetchall()
        return [self._serialize_version(dict(row)) for row in rows]

    def summary(self, dashboard_id: str, version_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            context = self._version_context(connection, dashboard_id, version_id)
            summary = self._summarize_sources(
                connection,
                context["source_ids"],
                context["filters"],
                context["sources"],
            )
        return {
            "dashboard_id": dashboard_id,
            "version_id": version_id,
            "dataset_version_id": context["dataset_version_id"],
            **summary,
        }

    def review_bias(self, dashboard_id: str, version_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            context = self._version_context(connection, dashboard_id, version_id)
            scope_filters = {
                key: value
                for key, value in context["filters"].items()
                if key != "quality_status"
            }
            where_sql, params = self._record_where(
                context["source_ids"],
                scope_filters,
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
                    "pending_rate": self._percentage(pending, total),
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
        overall_rate = self._percentage(pending, total)
        concentrated = []
        for row in rows:
            product_total = int(row["total_record_count"] or 0)
            product_pending = int(row["pending_record_count"] or 0)
            product_rate = self._percentage(product_pending, product_total)
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

    def text_quality(self, dashboard_id: str, version_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            context = self._version_context(connection, dashboard_id, version_id)
            where_sql, params = self._record_where(
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
            "anomaly_rate": self._percentage(count, total),
            "checked_record_count": total,
            "examples": anomalies[:5],
            "note": (
                f"发现 {count} 条疑似编码异常评论，重新导入原始数据前，"
                "不应生成商品级行动建议。"
                if count
                else "未发现明显的评论编码异常。"
            ),
        }

    def sources(self, dashboard_id: str, version_id: str) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            context = self._version_context(connection, dashboard_id, version_id)
        return context["sources"]

    def insights(
        self,
        dashboard_id: str,
        version_id: str,
        *,
        problem: str | None = None,
        label_group: str | None = None,
        listing: str | None = None,
        product_name: str | None = None,
        product_sku: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        report_mode: bool = False,
    ) -> dict[str, Any]:
        clean_date_from = self._clean_date(date_from)
        clean_date_to = self._clean_date(date_to)
        if clean_date_from and clean_date_to and clean_date_from > clean_date_to:
            raise ValueError("开始日期不能晚于结束日期")
        runtime_filters = self._normalize_filters(
            {
                "listing": listing,
                "product_name": product_name,
                "product_sku": product_sku,
            }
        )
        clean_group = (label_group or "").strip()
        requested_problem = (problem or "").strip()

        with self.database.connect() as connection:
            context = self._version_context(connection, dashboard_id, version_id)
            summary = self._summarize_sources(
                connection,
                context["source_ids"],
                context["filters"],
                context["sources"],
            )
            option_where, option_params = self._record_where(
                context["source_ids"],
                context["filters"],
            )
            where_sql, params = self._record_where(
                context["source_ids"],
                context["filters"],
                runtime_filters,
            )
            if clean_date_from:
                where_sql += " AND date(r.return_date) >= date(?)"
                params.append(clean_date_from)
            if clean_date_to:
                where_sql += " AND date(r.return_date) <= date(?)"
                params.append(clean_date_to)
            unit_rollup = (
                report_mode
                and not runtime_filters
                and not clean_date_from
                and not clean_date_to
                and not {key for key in context["filters"] if key != "quality_status"}
            )

            date_range = dict(
                connection.execute(
                    f"""
                    SELECT MIN(date(r.return_date)) AS date_from,
                           MAX(date(r.return_date)) AS date_to
                    FROM classification_result_records r
                    WHERE {option_where}
                    """,
                    tuple(option_params),
                ).fetchone()
            )
            total_records = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM classification_result_records r "
                    f"WHERE {where_sql}",
                    tuple(params),
                ).fetchone()[0]
            )
            labeled_record_count = int(
                connection.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM classification_result_records r
                    WHERE {where_sql}
                      AND EXISTS (
                          SELECT 1 FROM classification_unit_labels label
                          WHERE label.result_version_id = r.result_version_id
                            AND label.classification_key = r.classification_key
                            AND label.label_kind = 'problem'
                      )
                    """,
                    tuple(params),
                ).fetchone()[0]
            )
            if unit_rollup:
                source_placeholders = ",".join("?" for _ in context["source_ids"])
                subject_rows = connection.execute(
                    f"""
                    WITH unit_subjects AS (
                        SELECT DISTINCT u.id,
                               json_extract(unit.value, '$.subject') AS value,
                               u.record_count
                        FROM classification_units u
                        JOIN json_each(
                            u.classification_json,
                            '$.semantic_units'
                        ) unit
                        WHERE u.result_version_id IN ({source_placeholders})
                          AND u.quality_status = 'ready'
                          AND json_extract(unit.value, '$.subject') IS NOT NULL
                    )
                    SELECT value, SUM(record_count) AS record_count,
                           COUNT(*) AS semantic_unit_count
                    FROM unit_subjects
                    GROUP BY value
                    ORDER BY record_count DESC, value ASC
                    """,
                    tuple(context["source_ids"]),
                ).fetchall()
            else:
                subject_rows = connection.execute(
                    f"""
                    SELECT json_extract(unit.value, '$.subject') AS value,
                           COUNT(DISTINCT r.id) AS record_count,
                           COUNT(*) AS semantic_unit_count
                    FROM classification_result_records r
                    JOIN classification_units u
                      ON u.result_version_id = r.result_version_id
                     AND u.classification_key = r.classification_key
                    JOIN json_each(u.classification_json, '$.semantic_units') unit
                    WHERE {where_sql}
                      AND json_extract(unit.value, '$.subject') IS NOT NULL
                    GROUP BY json_extract(unit.value, '$.subject')
                    ORDER BY record_count DESC, value ASC
                    """,
                    tuple(params),
                ).fetchall()
            subject_breakdown = [
                {
                    "value": str(row["value"]),
                    "label": SUBJECT_LABELS.get(str(row["value"]), str(row["value"])),
                    "record_count": int(row["record_count"]),
                    "semantic_unit_count": int(row["semantic_unit_count"]),
                    "percentage": self._percentage(
                        int(row["record_count"]), total_records
                    ),
                }
                for row in subject_rows
            ]
            group_rows = connection.execute(
                f"""
                SELECT COALESCE(NULLIF(TRIM(l.label_group), ''), '其他原因') AS value,
                       COUNT(DISTINCT r.id) AS record_count
                FROM classification_result_records r
                JOIN classification_unit_labels l
                  ON l.result_version_id = r.result_version_id
                 AND l.classification_key = r.classification_key
                 AND l.label_kind = 'problem'
                WHERE {where_sql}
                GROUP BY value
                ORDER BY record_count DESC, MIN(l.rowid)
                """,
                tuple(params),
            ).fetchall()
            label_name_rows = connection.execute(
                f"""
                SELECT l.label_code,
                       COALESCE(NULLIF(TRIM(l.label_name), ''), l.label_code) AS label,
                       COUNT(DISTINCT r.id) AS record_count
                FROM classification_result_records r
                JOIN classification_unit_labels l
                  ON l.result_version_id = r.result_version_id
                 AND l.classification_key = r.classification_key
                 AND l.label_kind = 'problem'
                WHERE {where_sql}
                GROUP BY l.label_code, l.label_name
                """,
                tuple(params),
            ).fetchall()
            label_names = {
                str(row["label_code"]): str(row["label"]) for row in label_name_rows
            }
            label_counts = {
                str(row["label_code"]): int(row["record_count"])
                for row in label_name_rows
            }
            if unit_rollup:
                reason_subject_rows = connection.execute(
                    f"""
                    WITH unit_subjects AS (
                        SELECT DISTINCT u.id,
                               json_extract(unit.value, '$.label_code') AS label_code,
                               json_extract(unit.value, '$.subject') AS subject,
                               u.record_count
                        FROM classification_units u
                        JOIN json_each(
                            u.classification_json,
                            '$.semantic_units'
                        ) unit
                        WHERE u.result_version_id IN ({source_placeholders})
                          AND u.quality_status = 'ready'
                          AND json_extract(unit.value, '$.label_code') IS NOT NULL
                    )
                    SELECT label_code, subject,
                           SUM(record_count) AS record_count
                    FROM unit_subjects
                    GROUP BY label_code, subject
                    ORDER BY record_count DESC
                    """,
                    tuple(context["source_ids"]),
                ).fetchall()
            else:
                reason_subject_rows = connection.execute(
                    f"""
                    SELECT l.label_code,
                           json_extract(unit.value, '$.subject') AS subject,
                           COUNT(DISTINCT r.id) AS record_count
                    FROM classification_result_records r
                    JOIN classification_unit_labels l
                      ON l.result_version_id = r.result_version_id
                     AND l.classification_key = r.classification_key
                     AND l.label_kind = 'problem'
                    JOIN classification_units u
                      ON u.result_version_id = r.result_version_id
                     AND u.classification_key = r.classification_key
                    JOIN json_each(u.classification_json, '$.semantic_units') unit
                      ON json_extract(unit.value, '$.label_code') = l.label_code
                    WHERE {where_sql}
                    GROUP BY l.label_code, subject
                    ORDER BY record_count DESC
                    """,
                    tuple(params),
                ).fetchall()
            reason_subjects: dict[str, list[str]] = {}
            for row in reason_subject_rows:
                reason_subjects.setdefault(str(row["label_code"]), []).append(
                    str(row["subject"])
                )
            reason_group_filter = ""
            reason_params = list(params)
            if clean_group:
                reason_group_filter = (
                    " AND COALESCE(NULLIF(TRIM(l.label_group), ''), '其他原因') = ?"
                )
                reason_params.append(clean_group)
            if report_mode:
                reason_sql = f"""
                    SELECT l.label_code AS value,
                           COALESCE(NULLIF(TRIM(l.label_name), ''), l.label_code)
                               AS label,
                           COALESCE(NULLIF(TRIM(l.label_group), ''), '其他原因')
                               AS label_group,
                           COUNT(r.id) AS record_count,
                           NULL AS primary_record_count
                    FROM classification_result_records r
                    JOIN classification_unit_labels l
                      ON l.result_version_id = r.result_version_id
                     AND l.classification_key = r.classification_key
                     AND l.label_kind = 'problem'
                    WHERE {where_sql}{reason_group_filter}
                    GROUP BY l.label_code, l.label_name, l.label_group
                    ORDER BY record_count DESC, label COLLATE NOCASE ASC
                """
            else:
                reason_sql = f"""
                SELECT l.label_code AS value,
                       COALESCE(NULLIF(TRIM(l.label_name), ''), l.label_code) AS label,
                       COALESCE(NULLIF(TRIM(l.label_group), ''), '其他原因') AS label_group,
                       COUNT(r.id) AS record_count,
                       SUM(CASE WHEN EXISTS (
                           SELECT 1
                           FROM json_each(
                               u.classification_json,
                               '$.primary_label_codes'
                           ) primary_label
                           WHERE primary_label.value = l.label_code
                       ) THEN 1 ELSE 0 END) AS primary_record_count
                FROM classification_result_records r
                JOIN classification_unit_labels l
                  ON l.result_version_id = r.result_version_id
                 AND l.classification_key = r.classification_key
                 AND l.label_kind = 'problem'
                JOIN classification_units u
                  ON u.result_version_id = r.result_version_id
                 AND u.classification_key = r.classification_key
                WHERE {where_sql}{reason_group_filter}
                GROUP BY l.label_code, l.label_name, l.label_group
                ORDER BY record_count DESC, label COLLATE NOCASE ASC
                """
            reason_rows = connection.execute(
                reason_sql,
                tuple(reason_params),
            ).fetchall()
            reasons = [
                {
                    **dict(row),
                    "record_count": int(row["record_count"]),
                    "primary_record_count": (
                        None if report_mode else int(row["primary_record_count"] or 0)
                    ),
                    "companion_only_count": (
                        None
                        if report_mode
                        else int(row["record_count"])
                        - int(row["primary_record_count"] or 0)
                    ),
                    "primary_rate": (
                        None
                        if report_mode
                        else self._percentage(
                            int(row["primary_record_count"] or 0),
                            int(row["record_count"]),
                        )
                    ),
                    "subjects": reason_subjects.get(str(row["value"]), []),
                    "percentage": self._percentage(
                        int(row["record_count"]), total_records
                    ),
                }
                for row in reason_rows
            ]
            product_matrix_rows = connection.execute(
                f"""
                WITH filtered_records AS (
                    SELECT r.id, r.result_version_id, r.classification_key,
                           r.product_name
                    FROM classification_result_records r
                    WHERE {where_sql}
                ),
                top_products AS (
                    SELECT product_name AS value,
                           COUNT(*) AS total_record_count
                    FROM filtered_records
                    WHERE product_name IS NOT NULL
                      AND TRIM(product_name) <> ''
                    GROUP BY product_name
                    ORDER BY total_record_count DESC, value COLLATE NOCASE ASC
                    LIMIT 8
                )
                SELECT top_products.value,
                       top_products.total_record_count,
                       l.label_code,
                       COUNT(DISTINCT filtered_records.id) AS record_count
                FROM top_products
                JOIN filtered_records
                  ON filtered_records.product_name = top_products.value
                LEFT JOIN classification_unit_labels l
                  ON l.result_version_id = filtered_records.result_version_id
                 AND l.classification_key = filtered_records.classification_key
                 AND l.label_kind = 'problem'
                GROUP BY top_products.value, top_products.total_record_count,
                         l.label_code
                ORDER BY top_products.total_record_count DESC,
                         top_products.value COLLATE NOCASE ASC,
                         record_count DESC
                """,
                tuple(params),
            ).fetchall()
            product_reason_matrix: list[dict[str, Any]] = []
            products_by_name: dict[str, dict[str, Any]] = {}
            for row in product_matrix_rows:
                product_name_value = str(row["value"])
                product = products_by_name.get(product_name_value)
                if product is None:
                    product = {
                        "value": product_name_value,
                        "total_record_count": int(row["total_record_count"]),
                        "reliable": int(row["total_record_count"]) >= 15,
                        "reason_rates": {},
                    }
                    products_by_name[product_name_value] = product
                    product_reason_matrix.append(product)
                if row["label_code"] is None:
                    continue
                label_code = str(row["label_code"])
                record_count = int(row["record_count"])
                product_rate = self._percentage(
                    record_count, int(row["total_record_count"])
                )
                overall_count = label_counts.get(label_code, 0)
                product["reason_rates"][label_code] = {
                    "label": label_names.get(label_code, label_code),
                    "record_count": record_count,
                    "percentage": product_rate,
                    "lift": round(
                        (record_count / int(row["total_record_count"]))
                        / (overall_count / total_records),
                        2,
                    )
                    if overall_count and total_records
                    else 0.0,
                }
            selected_reason = (
                None
                if report_mode
                else next(
                    (item for item in reasons if item["value"] == requested_problem),
                    reasons[0] if reasons else None,
                )
            )

            trend: list[dict[str, Any]] = []
            products: list[dict[str, Any]] = []
            co_reasons: list[dict[str, Any]] = []
            semantic_parts: list[dict[str, Any]] = []
            semantic_opinions: list[dict[str, Any]] = []
            semantic_record_count = 0
            evidence_items: list[dict[str, Any]] = []
            evidence_total = 0
            if selected_reason:
                selected_code = str(selected_reason["value"])
                trend_rows = connection.execute(
                    f"""
                    SELECT date(
                               r.return_date,
                               '-' || ((CAST(strftime('%w', r.return_date) AS INTEGER)
                               + 6) % 7) || ' days'
                           ) AS period_start,
                           date(
                               r.return_date,
                               '-' || ((CAST(strftime('%w', r.return_date) AS INTEGER)
                               + 6) % 7) || ' days',
                               '+6 days'
                           ) AS period_end,
                           COUNT(r.id) AS total_record_count,
                           SUM(CASE WHEN EXISTS (
                               SELECT 1 FROM classification_unit_labels selected
                               WHERE selected.result_version_id = r.result_version_id
                                 AND selected.classification_key = r.classification_key
                                 AND selected.label_kind = 'problem'
                                 AND selected.label_code = ?
                           ) THEN 1 ELSE 0 END) AS record_count
                    FROM classification_result_records r
                    WHERE {where_sql} AND r.return_date IS NOT NULL
                    GROUP BY period_start, period_end
                    ORDER BY period_start
                    """,
                    (selected_code, *params),
                ).fetchall()
                trend = [
                    {
                        **dict(row),
                        "record_count": int(row["record_count"] or 0),
                        "total_record_count": int(row["total_record_count"] or 0),
                        "percentage": self._percentage(
                            int(row["record_count"] or 0),
                            int(row["total_record_count"] or 0),
                        ),
                        "low_sample": int(row["total_record_count"] or 0) < 10,
                    }
                    for row in trend_rows
                ]
                product_rows = connection.execute(
                    f"""
                    SELECT COALESCE(NULLIF(TRIM(r.product_name), ''), '未提供产品')
                               AS value,
                           COUNT(r.id) AS total_record_count,
                           SUM(CASE WHEN EXISTS (
                               SELECT 1 FROM classification_unit_labels selected
                               WHERE selected.result_version_id = r.result_version_id
                                 AND selected.classification_key = r.classification_key
                                 AND selected.label_kind = 'problem'
                                 AND selected.label_code = ?
                           ) THEN 1 ELSE 0 END) AS record_count
                    FROM classification_result_records r
                    WHERE {where_sql}
                    GROUP BY value
                    HAVING record_count > 0
                    ORDER BY record_count DESC, value COLLATE NOCASE ASC
                    LIMIT 8
                    """,
                    (selected_code, *params),
                ).fetchall()
                selected_count = int(selected_reason["record_count"])
                products = [
                    {
                        "value": row["value"],
                        "record_count": int(row["record_count"]),
                        "total_record_count": int(row["total_record_count"]),
                        "reason_share": self._percentage(
                            int(row["record_count"]), selected_count
                        ),
                        "product_reason_rate": self._percentage(
                            int(row["record_count"]),
                            int(row["total_record_count"]),
                        ),
                        "overall_reason_rate": self._percentage(
                            selected_count, total_records
                        ),
                        "lift": round(
                            (int(row["record_count"]) / int(row["total_record_count"]))
                            / (selected_count / total_records),
                            2,
                        )
                        if total_records and selected_count
                        else 0.0,
                        "reliable": int(row["total_record_count"]) >= 15,
                    }
                    for row in product_rows
                ]
                co_reason_rows = connection.execute(
                    f"""
                    SELECT other.label_code AS value,
                           COALESCE(NULLIF(TRIM(other.label_name), ''),
                                    other.label_code) AS label,
                           COUNT(r.id) AS record_count
                    FROM classification_result_records r
                    JOIN classification_unit_labels selected
                      ON selected.result_version_id = r.result_version_id
                     AND selected.classification_key = r.classification_key
                     AND selected.label_kind = 'problem'
                     AND selected.label_code = ?
                    JOIN classification_unit_labels other
                      ON other.result_version_id = r.result_version_id
                     AND other.classification_key = r.classification_key
                     AND other.label_kind = 'problem'
                     AND other.label_code <> ?
                    WHERE {where_sql}
                    GROUP BY other.label_code, other.label_name
                    ORDER BY record_count DESC, label COLLATE NOCASE ASC
                    LIMIT 6
                    """,
                    (selected_code, selected_code, *params),
                ).fetchall()
                co_reasons = [
                    {
                        **dict(row),
                        "record_count": int(row["record_count"]),
                        "percentage": self._percentage(
                            int(row["record_count"]), selected_count
                        ),
                        "lift": round(
                            (int(row["record_count"]) / selected_count)
                            / (label_counts.get(str(row["value"]), 0) / total_records),
                            2,
                        )
                        if total_records and label_counts.get(str(row["value"]), 0)
                        else 0.0,
                    }
                    for row in co_reason_rows
                ]
                semantic_record_count = int(
                    connection.execute(
                        f"""
                        SELECT COUNT(DISTINCT r.id)
                        FROM classification_result_records r
                        JOIN classification_units u
                          ON u.result_version_id = r.result_version_id
                         AND u.classification_key = r.classification_key
                        JOIN json_each(
                            u.classification_json,
                            '$.semantic_units'
                        ) unit
                        WHERE {where_sql}
                          AND json_extract(unit.value, '$.label_code') = ?
                        """,
                        (*params, selected_code),
                    ).fetchone()[0]
                )
                part_rows = connection.execute(
                    f"""
                    SELECT COALESCE(
                               NULLIF(json_extract(unit.value, '$.part'), ''),
                               'UNSPECIFIED'
                           ) AS value,
                           COUNT(DISTINCT r.id) AS record_count
                    FROM classification_result_records r
                    JOIN classification_units u
                      ON u.result_version_id = r.result_version_id
                     AND u.classification_key = r.classification_key
                    JOIN json_each(
                        u.classification_json,
                        '$.semantic_units'
                    ) unit
                    WHERE {where_sql}
                      AND json_extract(unit.value, '$.label_code') = ?
                    GROUP BY COALESCE(
                        NULLIF(json_extract(unit.value, '$.part'), ''),
                        'UNSPECIFIED'
                    )
                    ORDER BY record_count DESC, value ASC
                    LIMIT 6
                    """,
                    (*params, selected_code),
                ).fetchall()
                semantic_parts = [
                    {
                        "value": str(row["value"]),
                        "record_count": int(row["record_count"]),
                        "percentage": self._percentage(
                            int(row["record_count"]), semantic_record_count
                        ),
                    }
                    for row in part_rows
                ]
                opinion_rows = connection.execute(
                    f"""
                    SELECT json_extract(unit.value, '$.opinion') AS opinion,
                           json_extract(unit.value, '$.subject') AS subject,
                           COALESCE(
                               NULLIF(json_extract(unit.value, '$.part'), ''),
                               'UNSPECIFIED'
                           ) AS part,
                           COUNT(DISTINCT r.id) AS record_count,
                           MAX(json_extract(unit.value, '$.evidence')) AS evidence
                    FROM classification_result_records r
                    JOIN classification_units u
                      ON u.result_version_id = r.result_version_id
                     AND u.classification_key = r.classification_key
                    JOIN json_each(
                        u.classification_json,
                        '$.semantic_units'
                    ) unit
                    WHERE {where_sql}
                      AND json_extract(unit.value, '$.label_code') = ?
                      AND NULLIF(json_extract(unit.value, '$.opinion'), '')
                          IS NOT NULL
                    GROUP BY opinion, subject, part
                    ORDER BY record_count DESC, opinion ASC
                    LIMIT 4
                    """,
                    (*params, selected_code),
                ).fetchall()
                semantic_opinions = [
                    {
                        **dict(row),
                        "record_count": int(row["record_count"]),
                    }
                    for row in opinion_rows
                ]
                evidence_total = selected_count
                evidence_rows = connection.execute(
                    f"""
                    SELECT r.*, u.processing_status, u.problem_labels_json,
                           u.classification_json
                    FROM classification_result_records r
                    JOIN classification_units u
                      ON u.result_version_id = r.result_version_id
                     AND u.classification_key = r.classification_key
                    WHERE {where_sql}
                      AND EXISTS (
                          SELECT 1 FROM classification_unit_labels selected
                          WHERE selected.result_version_id = r.result_version_id
                            AND selected.classification_key = r.classification_key
                            AND selected.label_kind = 'problem'
                            AND selected.label_code = ?
                      )
                    ORDER BY datetime(r.return_date) DESC,
                             r.source_row DESC, r.id ASC
                    LIMIT 4
                    """,
                    (*params, selected_code),
                ).fetchall()
                evidence_items = [
                    self._serialize_record(dict(row)) for row in evidence_rows
                ]
                for item in evidence_items:
                    item["problem_labels"] = [
                        label_names.get(str(label), str(label))
                        for label in item["problem_labels"]
                    ]

            filter_options = {}
            for key, column in (
                ("listings", "r.listing"),
                ("product_names", "r.product_name"),
                ("product_skus", "r.product_sku"),
            ):
                rows = connection.execute(
                    f"""
                    SELECT DISTINCT {column} AS value
                    FROM classification_result_records r
                    WHERE {option_where}
                      AND {column} IS NOT NULL
                      AND TRIM({column}) <> ''
                    ORDER BY value COLLATE NOCASE ASC
                    """,
                    tuple(option_params),
                ).fetchall()
                filter_options[key] = [str(row["value"]) for row in rows]

        return {
            "dashboard_id": dashboard_id,
            "version_id": version_id,
            "summary": summary,
            "date_range": date_range,
            "filter_options": filter_options,
            "category_groups": [str(row["value"]) for row in group_rows],
            "label_group_breakdown": [
                {
                    "value": str(row["value"]),
                    "record_count": int(row["record_count"]),
                    "percentage": self._percentage(
                        int(row["record_count"]), total_records
                    ),
                }
                for row in group_rows
            ],
            "total_record_count": total_records,
            "labeled_record_count": labeled_record_count,
            "label_coverage": self._percentage(labeled_record_count, total_records),
            "subject_breakdown": subject_breakdown,
            "reasons": reasons,
            "product_reason_matrix": product_reason_matrix,
            "selected_reason": selected_reason,
            "trend": trend,
            "products": products,
            "co_reasons": co_reasons,
            "semantic_profile": {
                "record_count": semantic_record_count,
                "coverage": self._percentage(
                    semantic_record_count,
                    int(selected_reason["record_count"]) if selected_reason else 0,
                ),
                "parts": semantic_parts,
                "opinions": semantic_opinions,
            },
            "evidence": {
                "items": evidence_items,
                "total": evidence_total,
            },
        }

    def records(
        self,
        dashboard_id: str,
        version_id: str,
        *,
        page: int = 1,
        page_size: int = PAGE_SIZE_DEFAULT,
        **filters: str | None,
    ) -> dict[str, Any]:
        page, page_size = self._validate_page(page, page_size)
        runtime_filters = self._normalize_filters(filters)
        with self.database.connect() as connection:
            context = self._version_context(connection, dashboard_id, version_id)
            where_sql, params = self._record_where(
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
                       u.classification_json
                FROM classification_result_records r
                JOIN classification_units u
                  ON u.result_version_id = r.result_version_id
                 AND u.classification_key = r.classification_key
                WHERE {where_sql}
                ORDER BY r.store_site ASC, r.listing ASC,
                         r.source_row ASC, r.id ASC
                LIMIT ? OFFSET ?
                """,
                (*params, page_size, (page - 1) * page_size),
            ).fetchall()
        return {
            "items": [self._serialize_record(dict(row)) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def drilldown(
        self,
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
        page, page_size = self._validate_page(page, page_size)
        runtime_filters = self._normalize_filters(filters)
        with self.database.connect() as connection:
            context = self._version_context(connection, dashboard_id, version_id)
            where_sql, params = self._record_where(
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

    def _build_plan(
        self,
        connection: sqlite3.Connection,
        result_version_ids: list[str],
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        clean_ids = sorted(
            {str(value).strip() for value in result_version_ids if str(value).strip()}
        )
        if not clean_ids:
            raise ValueError("result_version_ids 至少需要一个有效值")
        normalized_filters = self._normalize_filters(filters)
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
                   r.logic_version, r.taxonomy_version,
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
        summary = self._summarize_sources(
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

    def _summarize_sources(
        self,
        connection: sqlite3.Connection,
        source_ids: list[str],
        filters: dict[str, list[str]],
        sources: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if source_ids:
            where_sql, params = self._record_where(source_ids, filters)
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
            scope_where, scope_params = self._record_where(
                source_ids,
                scope_filters,
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
            pending_review_record_count = int(
                coverage["pending_review_record_count"] or 0
            )
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

    def _insert_version(
        self,
        connection: sqlite3.Connection,
        *,
        dashboard_id: str,
        version_no: int,
        plan: dict[str, Any],
        reason: str,
        actor_id: str,
        now: str,
    ) -> dict[str, str]:
        dataset_version_id = new_id("dashboard_dataset_version")
        version_id = new_id("dashboard_version")
        connection.execute(
            """
            INSERT INTO dashboard_dataset_versions(
                id, dashboard_id, version_no, filters_json,
                source_snapshot_json, summary_json, plan_hash,
                reason, created_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dataset_version_id,
                dashboard_id,
                version_no,
                json_text(plan["filters"]),
                json_text(plan["sources"]),
                json_text(plan["summary"]),
                plan["plan_hash"],
                reason,
                actor_id,
                now,
            ),
        )
        for source in plan["sources"]:
            connection.execute(
                """
                INSERT INTO dashboard_dataset_sources(
                    dataset_version_id, result_version_id, store_site,
                    listing, source_snapshot_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    dataset_version_id,
                    source["result_version_id"],
                    source["store_site"],
                    source["listing"],
                    json_text(source),
                ),
            )
        connection.execute(
            """
            INSERT INTO dashboard_versions(
                id, dashboard_id, version_no, dataset_version_id,
                reason, created_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                version_id,
                dashboard_id,
                version_no,
                dataset_version_id,
                reason,
                actor_id,
                now,
            ),
        )
        return {
            "version_id": version_id,
            "dataset_version_id": dataset_version_id,
        }

    @staticmethod
    def _require_ready_plan(plan: dict[str, Any], expected_hash: str) -> None:
        if plan["plan_hash"] != expected_hash.strip():
            raise DashboardConflict("看板数据计划已变化，请重新预检")
        if not plan["ready"]:
            raise DashboardConflict("看板数据计划存在阻断或 Listing 冲突")

    def _version_context(
        self,
        connection: sqlite3.Connection,
        dashboard_id: str,
        version_id: str,
    ) -> dict[str, Any]:
        version = self._version_row(connection, dashboard_id, version_id)
        source_rows = connection.execute(
            """
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
                   r.logic_version, r.taxonomy_version,
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
            FROM dashboard_dataset_sources source
            JOIN classification_result_versions v
              ON v.id = source.result_version_id
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
        }

    def _version_row(
        self,
        connection: sqlite3.Connection,
        dashboard_id: str,
        version_id: str | None,
    ) -> sqlite3.Row:
        if not version_id:
            raise DashboardNotFound("分析看板还没有可用版本")
        row = connection.execute(
            f"""
            {self._version_select()}
            WHERE v.id = ? AND v.dashboard_id = ?
            """,
            (version_id, dashboard_id),
        ).fetchone()
        if row is None:
            raise DashboardNotFound("分析看板版本不存在")
        return row

    @staticmethod
    def _version_select() -> str:
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

    @staticmethod
    def _serialize_version(value: dict[str, Any]) -> dict[str, Any]:
        value["filters"] = json_value(value.pop("filters_json", None), {})
        value["source_snapshot"] = json_value(
            value.pop("source_snapshot_json", None),
            [],
        )
        value["summary"] = json_value(value.pop("summary_json", None), {})
        return value

    @staticmethod
    def _serialize_dashboard_list(value: dict[str, Any]) -> dict[str, Any]:
        value["summary"] = json_value(value.pop("summary_json", None), {})
        return value

    @staticmethod
    def _normalize_filters(filters: dict[str, Any]) -> dict[str, list[str]]:
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

    @staticmethod
    def _record_where(
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
                    where.append(
                        """
                        EXISTS (
                            SELECT 1 FROM classification_unit_labels f
                            WHERE f.result_version_id = r.result_version_id
                              AND f.classification_key = r.classification_key
                              AND f.label_kind = 'problem'
                              AND f.label_code IN ("""
                        + placeholders
                        + ") )"
                    )
                else:
                    where.append(f"r.{FILTER_COLUMNS[key]} IN ({placeholders})")
                params.extend(values)
        return " AND ".join(where), params

    @staticmethod
    def _serialize_record(value: dict[str, Any]) -> dict[str, Any]:
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

    @staticmethod
    def _clean_date(value: str | None) -> str:
        clean_value = (value or "").strip()
        if not clean_value:
            return ""
        try:
            return date.fromisoformat(clean_value).isoformat()
        except ValueError as exc:
            raise ValueError("日期必须使用 YYYY-MM-DD 格式") from exc

    @staticmethod
    def _percentage(numerator: int, denominator: int) -> float:
        return round(numerator * 100 / denominator, 1) if denominator else 0.0

    @staticmethod
    def _insert_audit(
        connection: sqlite3.Connection,
        *,
        entity_type: str,
        entity_id: str,
        action: str,
        actor_id: str,
        after: dict[str, Any],
        now: str,
        before: dict[str, Any] | None = None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO audit_logs(
                id, entity_type, entity_id, action, before_json,
                after_json, actor_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id("audit"),
                entity_type,
                entity_id,
                action,
                json_text(before) if before is not None else None,
                json_text(after),
                actor_id,
                now,
            ),
        )

    @staticmethod
    def _validate_page(page: int, page_size: int) -> tuple[int, int]:
        if page < 1:
            raise ValueError("page 必须大于等于 1")
        if not 1 <= page_size <= PAGE_SIZE_MAX:
            raise ValueError(f"page_size 必须在 1 到 {PAGE_SIZE_MAX} 之间")
        return page, page_size

    @staticmethod
    def _contains_pattern(value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace("%", "\\%")
        escaped = escaped.replace("_", "\\_")
        return f"%{escaped}%"
