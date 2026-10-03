from __future__ import annotations

import hashlib
from dataclasses import replace
from typing import Any, Callable

from return_semantics.model_client import Sub2APIClient
from web_backend import (
    insight_report_consistency,
    insight_report_content,
    insight_report_diagnostics,
    insight_report_evidence,
)
from web_backend.common import json_text, new_id
from web_backend.config_service import ConfigService
from web_backend.insight_report_contracts import PROMPT_VERSION
from web_backend.insight_reports.lifecycle_contracts import (
    GENERATION_ERROR_MESSAGE,
)
from web_backend.insight_reports.records import _InsightReportRecords
from web_backend.security import utc_now


class _InsightReportExecution(_InsightReportRecords):
    config_service: ConfigService
    client_factory: Callable[[Any], Sub2APIClient]

    _diagnostic_reason_codes = staticmethod(
        insight_report_diagnostics._diagnostic_reason_codes
    )

    _compact_diagnostic = staticmethod(insight_report_diagnostics._compact_diagnostic)

    _build_evidence = staticmethod(insight_report_evidence._build_evidence)

    _messages_v6 = staticmethod(insight_report_content._messages_v6)

    _assemble_content_v6 = staticmethod(insight_report_content._assemble_content_v6)

    _messages = staticmethod(insight_report_content._messages)

    _assemble_content = staticmethod(insight_report_content._assemble_content)

    _validate_evidence_refs = staticmethod(
        insight_report_content._validate_evidence_refs
    )

    _validate_issue_evidence_refs = staticmethod(
        insight_report_content._validate_issue_evidence_refs
    )

    _decision_report_consistency = staticmethod(
        insight_report_consistency._decision_report_consistency
    )

    _report_consistency = staticmethod(insight_report_consistency._report_consistency)

    def recover(self) -> None:
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                UPDATE ai_insight_reports
                SET status = 'queued', stage = 'queued', error = NULL,
                    technical_error = NULL, started_at = NULL
                WHERE status = 'running'
                """
            )

    def claim_next(self) -> str | None:
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute(
                """
                SELECT id FROM ai_insight_reports
                WHERE status = 'queued'
                ORDER BY created_at, id
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None
            report_id = str(row["id"])
            updated = connection.execute(
                """
                UPDATE ai_insight_reports
                SET status = 'running', stage = 'preparing_evidence',
                    started_at = ?, error = NULL, technical_error = NULL
                WHERE id = ? AND status = 'queued'
                """,
                (utc_now(), report_id),
            )
            return report_id if updated.rowcount == 1 else None

    def run(self, report_id: str) -> None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM ai_insight_reports WHERE id = ?",
                (report_id,),
            ).fetchone()
        if row is None or row["status"] != "running":
            return
        report = dict(row)
        try:
            analysis = self.dashboard_service.insights(
                str(report["dashboard_id"]),
                str(report["dashboard_version_id"]),
                report_mode=True,
            )
            analysis["review_bias"] = self.dashboard_service.review_bias(
                str(report["dashboard_id"]),
                str(report["dashboard_version_id"]),
            )
            analysis["text_quality"] = self.dashboard_service.text_quality(
                str(report["dashboard_id"]),
                str(report["dashboard_version_id"]),
            )
            analysis["sources"] = self.dashboard_service.sources(
                str(report["dashboard_id"]),
                str(report["dashboard_version_id"]),
            )
            reason_codes = self._diagnostic_reason_codes(analysis)
            analysis["diagnostics"] = [
                self._compact_diagnostic(diagnostic)
                for diagnostic in self.dashboard_service.report_diagnostics(
                    str(report["dashboard_id"]),
                    str(report["dashboard_version_id"]),
                    reason_codes,
                )
            ]
            analysis["issue_cases"] = self.dashboard_service.issue_cases(
                str(report["dashboard_id"]),
                str(report["dashboard_version_id"]),
                reason_codes,
            )
            prompt_version = str(report["prompt_version"])
            evidence = self._build_evidence(
                analysis,
                prompt_version=prompt_version,
            )
            evidence_hash = hashlib.sha256(
                json_text(evidence).encode("utf-8")
            ).hexdigest()
            with self.database.transaction() as connection:
                connection.execute(
                    """
                    UPDATE ai_insight_reports
                    SET evidence_json = ?, evidence_hash = ?,
                        stage = 'calling_model'
                    WHERE id = ?
                    """,
                    (json_text(evidence), evidence_hash, report_id),
                )
            settings = self.config_service.build_model_settings(
                str(report["config_version_id"])
            )
            settings = replace(
                settings,
                model=str(report["model_key"]),
                reasoning_effort=str(report["reasoning_effort"]),
                cheap_model=None,
                secondary_model=None,
            )
            client = self.client_factory(settings)
            messages = (
                self._messages_v6(evidence)
                if prompt_version == PROMPT_VERSION
                else self._messages(evidence)
            )
            result = client.generate_json(
                messages,
                model=str(report["model_key"]),
                reasoning_effort=str(report["reasoning_effort"]),
            )
            with self.database.transaction() as connection:
                connection.execute(
                    """
                    UPDATE ai_insight_reports SET stage = 'assembling_report'
                    WHERE id = ? AND status = 'running'
                    """,
                    (report_id,),
                )
            if prompt_version == PROMPT_VERSION:
                decision_content = self._assemble_content_v6(evidence, result.payload)
                self._validate_issue_evidence_refs(
                    decision_content,
                    set(evidence["catalog"]),
                )
                consistency = self._decision_report_consistency(
                    decision_content.model_dump(),
                    evidence,
                )
                content_json = decision_content.model_dump_json()
            else:
                report_content = self._assemble_content(evidence, result.payload)
                self._validate_evidence_refs(report_content, set(evidence["catalog"]))
                consistency = self._report_consistency(
                    report_content.model_dump(),
                    evidence,
                    require_information_diagnostics=True,
                )
                content_json = report_content.model_dump_json()
            if consistency["status"] == "blocked":
                detail = "；".join(consistency["issues"][:3])
                raise ValueError(f"报告数据一致性校验未通过：{detail}")
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
                if updated.rowcount == 1:
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
        except Exception as exc:
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
