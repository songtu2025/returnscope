from __future__ import annotations

import builtins
from typing import Any

from web_backend.dashboard_common import (
    PAGE_SIZE_DEFAULT,
    DashboardNotFound,
)
from web_backend.dashboard_support import (
    contains_pattern,
    serialize_dashboard_list,
    serialize_version,
    validate_page,
    version_row,
    version_select,
)
from web_backend.database import Database


class _DashboardCatalog:
    database: Database

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

    def versions(self, dashboard_id: str) -> builtins.list[dict[str, Any]]:
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
