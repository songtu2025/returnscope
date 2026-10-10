from __future__ import annotations

import sqlite3
from typing import Any

from web_backend.common import insert_audit, json_text, new_id
from web_backend.dashboard_common import (
    DashboardConflict,
)
from web_backend.database import Database


class _DashboardVersionStorage:
    database: Database

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
