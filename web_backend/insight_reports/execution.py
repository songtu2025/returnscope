from __future__ import annotations

import hashlib
from dataclasses import replace
from typing import Any, Callable

from return_semantics.model_client import JsonModelCallResult, Sub2APIClient
from web_backend import (
    insight_report_consistency,
    insight_report_content,
    insight_report_diagnostics,
    insight_report_evidence,
)
from web_backend.common import json_text
from web_backend.config_service import ConfigService
from web_backend.insight_report_contracts import PROMPT_VERSION
from web_backend.insight_reports.execution_publication import _InsightReportPublication
from web_backend.security import utc_now


class _InsightReportExecution(_InsightReportPublication):
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
            analysis = self._report_analysis(report)
            prompt_version = str(report["prompt_version"])
            evidence = self._build_evidence(
                analysis,
                prompt_version=prompt_version,
            )
            evidence_hash = hashlib.sha256(
                json_text(evidence).encode("utf-8")
            ).hexdigest()
            self._persist_report_evidence(report_id, evidence, evidence_hash)
            result = self._generate_report(report, prompt_version, evidence)
            content_json = self._assemble_report(
                report_id, prompt_version, evidence, result
            )
            self._publish_report(report_id, report, result, content_json)
        except Exception as exc:
            self._fail_report(report_id, exc)

    def _report_analysis(self, report: dict[str, Any]) -> dict[str, Any]:
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
        return analysis

    def _persist_report_evidence(
        self, report_id: str, evidence: dict[str, Any], evidence_hash: str
    ) -> None:
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

    def _generate_report(
        self, report: dict[str, Any], prompt_version: str, evidence: dict[str, Any]
    ) -> JsonModelCallResult:
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
        return result

    def _assemble_report(
        self,
        report_id: str,
        prompt_version: str,
        evidence: dict[str, Any],
        result: JsonModelCallResult,
    ) -> str:
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
        return content_json
