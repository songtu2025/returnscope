from __future__ import annotations

from typing import Any

from return_semantics.model_client import JsonModelCallResult
from web_backend.common import json_text, new_id
from web_backend.insight_reports.lifecycle_contracts import GENERATION_ERROR_MESSAGE
from web_backend.insight_reports.records import _InsightReportRecords
from web_backend.security import utc_now


class _InsightReportPublication(_InsightReportRecords):
    def _publish_report(
        self,
        report_id: str,
        report: dict[str, Any],
        result: JsonModelCallResult,
        content_json: str,
    ) -> None:
        with self.database.transaction(immediate=True) as connection:
            version_no = int(
                connection.execute(
                    """
                        SELECT COALESCE(MAX(version_no), 0) + 1
                        FROM ai_insight_report_versions
                        WHERE dashboard_id = ?
                        """,
                    (report["dashboard_id"],),
                ).fetchone()[0]
            )
            completed_at = utc_now()
            completed = self._complete_report(
                connection, report_id, content_json, result, completed_at
            )
            if completed:
                connection.execute(
                    """
                        INSERT INTO ai_insight_report_versions(
                            id, job_id, dashboard_id, dashboard_version_id,
                            version_no, published_at
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                    (
                        new_id("insight_report_version"),
                        report_id,
                        report["dashboard_id"],
                        report["dashboard_version_id"],
                        version_no,
                        completed_at,
                    ),
                )

    @staticmethod
    def _complete_report(
        connection: Any,
        report_id: str,
        content_json: str,
        result: JsonModelCallResult,
        completed_at: str,
    ) -> bool:
        updated = connection.execute(
            """
                    UPDATE ai_insight_reports
                    SET status = 'completed', stage = 'completed',
                        resolved_model = ?,
                        content_json = ?, usage_json = ?, metrics_json = ?,
                        error = NULL, technical_error = NULL, completed_at = ?
                    WHERE id = ? AND status = 'running'
                    """,
            (
                result.model_name,
                content_json,
                json_text(result.usage),
                json_text(result.metrics),
                completed_at,
                report_id,
            ),
        )
        return updated.rowcount == 1

    def _fail_report(self, report_id: str, exc: Exception) -> None:
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                    UPDATE ai_insight_reports
                    SET status = 'failed', stage = 'failed', error = ?,
                        technical_error = ?, completed_at = ?
                    WHERE id = ? AND status = 'running'
                    """,
                (
                    GENERATION_ERROR_MESSAGE,
                    str(exc)[:4000],
                    utc_now(),
                    report_id,
                ),
            )
