from __future__ import annotations

import sqlite3
from typing import Any

from web_backend.common import insert_audit, json_text, new_id
from web_backend.dashboard_common import (
    PAGE_SIZE_DEFAULT,
    TEXT_ENCODING_ANOMALY,
    DashboardConflict,
    DashboardNotFound,
)
from web_backend.dashboard_insights import build_insights
from web_backend.dashboard_issue_cases import list_issue_cases
from web_backend.dashboard_plan import build_plan
from web_backend.dashboard_quality import (
    build_review_bias,
    build_summary,
    build_text_quality,
    list_sources,
)
from web_backend.dashboard_queries import build_drilldown, list_records
from web_backend.dashboard_support import (
    contains_pattern,
    mixed_hierarchy,
    serialize_dashboard_list,
    serialize_version,
    validate_page,
    version_row,
    version_select,
)
from web_backend.database import Database
from web_backend.security import utc_now

__all__ = [
    "DashboardConflict",
    "DashboardNotFound",
    "DashboardService",
    "TEXT_ENCODING_ANOMALY",
]


class DashboardService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def preflight(
        self,
        result_version_ids: list[str],
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self.database.connect() as connection:
            return build_plan(
                self.database, connection, result_version_ids, filters or {}
            )

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
            plan = build_plan(self.database, connection, result_version_ids, filters)
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
            plan = build_plan(self.database, connection, result_version_ids, filters)
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
        page, page_size = validate_page(page, page_size)
        where = ["1 = 1"]
        params: list[Any] = []
        if status:
            if status not in {"active", "archived"}:
                raise ValueError("status 不合法")
            where.append("d.status = ?")
            params.append(status)
        clean_query = (q or "").strip()
        if clean_query:
            pattern = contains_pattern(clean_query)
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
            "items": [serialize_dashboard_list(dict(row)) for row in rows],
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
            version = version_row(connection, dashboard_id, selected_version)
        output = dict(dashboard)
        output["version"] = serialize_version(dict(version))
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
                {version_select()}
                WHERE v.dashboard_id = ?
                ORDER BY v.version_no DESC, v.id ASC
                """,
                (dashboard_id,),
            ).fetchall()
        return [serialize_version(dict(row)) for row in rows]

    def summary(self, dashboard_id: str, version_id: str) -> dict[str, Any]:
        return build_summary(self.database, dashboard_id, version_id)

    def review_bias(self, dashboard_id: str, version_id: str) -> dict[str, Any]:
        return build_review_bias(self.database, dashboard_id, version_id)

    def text_quality(self, dashboard_id: str, version_id: str) -> dict[str, Any]:
        return build_text_quality(self.database, dashboard_id, version_id)

    def sources(self, dashboard_id: str, version_id: str) -> list[dict[str, Any]]:
        return list_sources(self.database, dashboard_id, version_id)

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
        return build_insights(
            self.database,
            dashboard_id,
            version_id,
            problem=problem,
            label_group=label_group,
            listing=listing,
            product_name=product_name,
            product_sku=product_sku,
            date_from=date_from,
            date_to=date_to,
            report_mode=report_mode,
        )

    def issue_cases(
        self,
        dashboard_id: str,
        version_id: str,
        reason_codes: list[str],
        *,
        max_cases_per_reason: int = 3,
    ) -> list[dict[str, Any]]:
        return list_issue_cases(
            self.database,
            dashboard_id,
            version_id,
            reason_codes,
            max_cases_per_reason=max_cases_per_reason,
        )

    def records(
        self,
        dashboard_id: str,
        version_id: str,
        *,
        page: int = 1,
        page_size: int = PAGE_SIZE_DEFAULT,
        **filters: str | None,
    ) -> dict[str, Any]:
        return list_records(
            self.database,
            dashboard_id,
            version_id,
            page=page,
            page_size=page_size,
            **filters,
        )

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
        return build_drilldown(
            self.database,
            dashboard_id,
            version_id,
            group_by,
            page=page,
            page_size=page_size,
            **filters,
        )

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
        insert_audit(
            connection,
            entity_type,
            entity_id,
            action,
            actor_id,
            before,
            after,
            now,
        )

    @staticmethod
    def _mixed_hierarchy(
        connection: sqlite3.Connection, sources: list[dict[str, Any]]
    ) -> bool:
        return mixed_hierarchy(connection, sources)
