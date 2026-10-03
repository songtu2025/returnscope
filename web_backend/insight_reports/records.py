from __future__ import annotations

import builtins
from typing import Any, Callable

from web_backend.common import json_text, json_value, new_id
from web_backend.dashboard_service import DashboardService
from web_backend.database import Database
from web_backend.insight_report_contracts import PROMPT_VERSION
from web_backend.insight_reports.lifecycle_contracts import (
    InsightReportConflict,
    InsightReportNotFound,
)
from web_backend.security import utc_now


class _InsightReportRecords:
    database: Database
    dashboard_service: DashboardService
    _serialize: Callable[..., dict[str, Any]]

    def list(
        self,
        dashboard_id: str,
        dashboard_version_id: str,
    ) -> list[dict[str, Any]]:
        self.dashboard_service.get(dashboard_id, dashboard_version_id)
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                {self._select_sql()}
                WHERE report.dashboard_id = ?
                  AND report.dashboard_version_id = ?
                ORDER BY report.version_no DESC
                """,
                (dashboard_id, dashboard_version_id),
            ).fetchall()
            decisions = self._decision_map(
                connection,
                [str(row["id"]) for row in rows],
            )
        text_quality = None
        if any(row["status"] == "completed" for row in rows):
            text_quality = self.dashboard_service.text_quality(
                dashboard_id,
                dashboard_version_id,
            )
        return [
            self._serialize(
                dict(row),
                text_quality=text_quality,
                decisions=decisions.get(str(row["id"]), []),
            )
            for row in rows
        ]

    def get(self, report_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                f"""
                {self._select_sql()}
                WHERE report.id = ?
                """,
                (report_id,),
            ).fetchone()
            decisions = self._decision_map(connection, [report_id]).get(
                report_id,
                [],
            )
        if row is None:
            raise InsightReportNotFound("AI 洞察报告不存在")
        report = dict(row)
        text_quality = None
        if report["status"] == "completed":
            text_quality = self.dashboard_service.text_quality(
                str(report["dashboard_id"]),
                str(report["dashboard_version_id"]),
            )
        return self._serialize(
            report,
            text_quality=text_quality,
            decisions=decisions,
        )

    def set_issue_decision(
        self,
        report_id: str,
        issue_id: str,
        status: str,
        actor_id: str,
    ) -> dict[str, Any]:
        if status not in {"pending", "ignored", "watching", "verify"}:
            raise ValueError("问题决策状态不合法")
        clean_issue_id = issue_id.strip()
        if not clean_issue_id:
            raise InsightReportNotFound("报告问题不存在")
        with self.database.transaction(immediate=True) as connection:
            report = connection.execute(
                """
                SELECT prompt_version, status, content_json
                FROM ai_insight_reports WHERE id = ?
                """,
                (report_id,),
            ).fetchone()
            if report is None:
                raise InsightReportNotFound("AI 洞察报告不存在")
            if (
                report["status"] != "completed"
                or report["prompt_version"] != PROMPT_VERSION
            ):
                raise InsightReportConflict("只有已完成的 V6 报告支持问题决策")
            content = json_value(report["content_json"], {})
            issue_ids = {
                str(issue.get("id") or "")
                for issue in content.get("issues", [])
                if isinstance(issue, dict)
            }
            if clean_issue_id not in issue_ids:
                raise InsightReportNotFound("报告问题不存在")
            existing = connection.execute(
                """
                SELECT report_id, issue_id, status, updated_by, updated_at
                FROM ai_insight_issue_decisions
                WHERE report_id = ? AND issue_id = ?
                """,
                (report_id, clean_issue_id),
            ).fetchone()
            if existing is not None and existing["status"] == status:
                return dict(existing)
            now = utc_now()
            before = dict(existing) if existing is not None else None
            connection.execute(
                """
                INSERT INTO ai_insight_issue_decisions(
                    report_id, issue_id, status, updated_by, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(report_id, issue_id) DO UPDATE SET
                    status = excluded.status,
                    updated_by = excluded.updated_by,
                    updated_at = excluded.updated_at
                """,
                (report_id, clean_issue_id, status, actor_id, now),
            )
            decision = {
                "report_id": report_id,
                "issue_id": clean_issue_id,
                "status": status,
                "updated_by": actor_id,
                "updated_at": now,
            }
            connection.execute(
                """
                INSERT INTO audit_logs(
                    id, entity_type, entity_id, action,
                    before_json, after_json, actor_id, created_at
                ) VALUES (?, 'ai_insight_issue_decision', ?,
                          'set_decision', ?, ?, ?, ?)
                """,
                (
                    new_id("audit"),
                    f"{report_id}:{clean_issue_id}",
                    json_text(before) if before else None,
                    json_text(decision),
                    actor_id,
                    now,
                ),
            )
        return decision

    @staticmethod
    def _select_sql() -> str:
        return """
            SELECT report.*, model.display_name AS model_name,
                   creator.display_name AS created_by_name,
                   dashboard_version.version_no AS dashboard_version_no,
                   published.id AS publication_id,
                   published.version_no AS published_version_no,
                   published.published_at
            FROM ai_insight_reports report
            JOIN api_models model ON model.id = report.model_id
            JOIN users creator ON creator.id = report.created_by
            JOIN dashboard_versions dashboard_version
              ON dashboard_version.id = report.dashboard_version_id
            LEFT JOIN ai_insight_report_versions published
              ON published.job_id = report.id
        """

    @staticmethod
    def _decision_map(
        connection: Any,
        report_ids: builtins.list[str],
    ) -> dict[str, builtins.list[dict[str, Any]]]:
        if not report_ids:
            return {}
        placeholders = ",".join("?" for _ in report_ids)
        rows = connection.execute(
            f"""
            SELECT decision.report_id, decision.issue_id, decision.status,
                   decision.updated_by, decision.updated_at,
                   user.display_name AS updated_by_name
            FROM ai_insight_issue_decisions decision
            LEFT JOIN users user ON user.id = decision.updated_by
            WHERE decision.report_id IN ({placeholders})
            ORDER BY decision.updated_at DESC, decision.issue_id
            """,
            tuple(report_ids),
        ).fetchall()
        decisions: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            value = dict(row)
            decisions.setdefault(str(value["report_id"]), []).append(value)
        return decisions
