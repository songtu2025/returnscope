from __future__ import annotations

from concurrent.futures import Future
from threading import Lock
from typing import Any

from web_backend.common import new_id
from web_backend.dashboard_common import (
    TEXT_ENCODING_ANOMALY,
    DashboardConflict,
    DashboardNotFound,
)
from web_backend.dashboard_insights import (
    InsightOptions,
)
from web_backend.dashboard_plan import build_plan
from web_backend.dashboards.analysis import _DashboardAnalysis
from web_backend.dashboards.catalog import _DashboardCatalog
from web_backend.dashboards.version_storage import _DashboardVersionStorage
from web_backend.database import Database
from web_backend.security import utc_now

__all__ = [
    "DashboardConflict",
    "DashboardNotFound",
    "DashboardService",
    "TEXT_ENCODING_ANOMALY",
]


class DashboardService(_DashboardCatalog, _DashboardVersionStorage, _DashboardAnalysis):
    def __init__(self, database: Database) -> None:
        self.database = database
        self._insights_lock = Lock()
        self._inflight_insights: dict[
            tuple[str, str, InsightOptions, str], Future[dict[str, Any]]
        ] = {}

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
            if dashboard["deleted_at"]:
                raise DashboardConflict("请先恢复分析看板")
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

    def report_data_version(
        self,
        dashboard_id: str,
        version_id: str,
        *,
        filters: dict[str, Any],
        plan_hash: str,
        actor_id: str,
    ) -> str:
        """复用数据快照保存报告范围，不推进看板的当前数据。"""
        with self.database.transaction(immediate=True) as connection:
            current = connection.execute(
                "SELECT current_version_id FROM analysis_dashboards WHERE id = ?",
                (dashboard_id,),
            ).fetchone()
            if current is None:
                raise DashboardNotFound("分析看板不存在")
            if current["current_version_id"] != version_id:
                raise DashboardConflict("看板数据已更新，请重新打开报告生成窗口")
            sources = connection.execute(
                """SELECT source.result_version_id FROM dashboard_dataset_sources source
                JOIN dashboard_versions version ON version.dataset_version_id = source.dataset_version_id
                WHERE version.id = ?""",
                (version_id,),
            ).fetchall()
            plan = build_plan(
                self.database,
                connection,
                [str(source[0]) for source in sources],
                filters,
            )
            self._require_ready_plan(plan, plan_hash)
            existing = connection.execute(
                """SELECT v.id FROM dashboard_versions v JOIN dashboard_dataset_versions data
                ON data.id = v.dataset_version_id WHERE v.dashboard_id = ? AND data.plan_hash = ?
                ORDER BY v.version_no DESC LIMIT 1""",
                (dashboard_id, plan_hash),
            ).fetchone()
            if existing:
                return str(existing["id"])
            number = connection.execute(
                "SELECT COALESCE(MAX(version_no), 0) + 1 FROM dashboard_versions WHERE dashboard_id = ?",
                (dashboard_id,),
            ).fetchone()[0]
            return self._insert_version(
                connection,
                dashboard_id=dashboard_id,
                version_no=number,
                plan=plan,
                reason="AI 洞察统计范围",
                actor_id=actor_id,
                now=utc_now(),
            )["version_id"]
