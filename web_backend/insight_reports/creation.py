from __future__ import annotations

import json
from typing import Any

from web_backend.common import json_text, new_id
from web_backend.insight_report_contracts import PROMPT_VERSION
from web_backend.insight_reports.lifecycle_contracts import (
    InsightReportConflict,
    InsightReportNotFound,
    _ReportCreationTarget,
)
from web_backend.insight_reports.records import _InsightReportRecords
from web_backend.model_catalog import validate_effort
from web_backend.security import utc_now


class _InsightReportCreation(_InsightReportRecords):
    def retry(self, report_id: str, actor_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM ai_insight_reports WHERE id = ?",
                (report_id,),
            ).fetchone()
        if row is None:
            raise InsightReportNotFound("AI 洞察报告不存在")
        source = dict(row)
        if source["status"] != "failed":
            raise InsightReportConflict("只有生成失败的尝试可以重试")
        retried = self._create_report(
            target=_ReportCreationTarget(
                dashboard_id=str(source["dashboard_id"]),
                dashboard_version_id=str(source["dashboard_version_id"]),
                parent_job_id=report_id,
            ),
            model={
                "id": source["model_id"],
                "model_key": source["model_key"],
                "config_version_id": source["config_version_id"],
            },
            reasoning_effort=str(source["reasoning_effort"]),
            actor_id=actor_id,
        )
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                INSERT INTO audit_logs(
                    id, entity_type, entity_id, action,
                    after_json, actor_id, created_at
                ) VALUES (?, 'ai_insight_report', ?, 'retry', ?, ?, ?)
                """,
                (
                    new_id("audit"),
                    report_id,
                    json_text({"new_job_id": retried["id"]}),
                    actor_id,
                    utc_now(),
                ),
            )
        return retried

    def _create_report(
        self,
        *,
        target: _ReportCreationTarget,
        model: dict[str, Any],
        reasoning_effort: str,
        actor_id: str,
    ) -> dict[str, Any]:
        dashboard_id = target.dashboard_id
        dashboard_version_id = target.dashboard_version_id
        parent_job_id = target.parent_job_id
        report_id = new_id("insight_report")
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            active = connection.execute(
                """
                SELECT id FROM ai_insight_reports
                WHERE dashboard_id = ? AND dashboard_version_id = ?
                  AND status IN ('queued', 'running')
                LIMIT 1
                """,
                (dashboard_id, dashboard_version_id),
            ).fetchone()
            if active:
                raise InsightReportConflict("当前数据版本已有报告正在生成")
            version_no = int(
                connection.execute(
                    """
                    SELECT COALESCE(MAX(version_no), 0) + 1
                    FROM ai_insight_reports WHERE dashboard_id = ?
                    """,
                    (dashboard_id,),
                ).fetchone()[0]
            )
            connection.execute(
                """
                INSERT INTO ai_insight_reports(
                    id, dashboard_id, dashboard_version_id, version_no,
                    status, model_id, model_key, config_version_id,
                    reasoning_effort, prompt_version, stage, parent_job_id,
                    created_by, created_at
                ) VALUES (?, ?, ?, ?, 'queued', ?, ?, ?, ?, ?, 'queued', ?, ?, ?)
                """,
                (
                    report_id,
                    dashboard_id,
                    dashboard_version_id,
                    version_no,
                    model["id"],
                    model["model_key"],
                    model["config_version_id"],
                    reasoning_effort,
                    PROMPT_VERSION,
                    parent_job_id,
                    actor_id,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO audit_logs(
                    id, entity_type, entity_id, action,
                    after_json, actor_id, created_at
                ) VALUES (?, 'ai_insight_report', ?, 'create', ?, ?, ?)
                """,
                (
                    new_id("audit"),
                    report_id,
                    json_text(
                        {
                            "dashboard_id": dashboard_id,
                            "dashboard_version_id": dashboard_version_id,
                            "attempt_no": version_no,
                            "model_id": model["id"],
                            "reasoning_effort": reasoning_effort,
                            "parent_job_id": parent_job_id,
                        }
                    ),
                    actor_id,
                    now,
                ),
            )
        return self.get(report_id)

    def _resolve_model(
        self,
        model_id: str,
        reasoning_effort: str,
    ) -> dict[str, Any]:
        effort = validate_effort(reasoning_effort, "报告推理强度")
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT model.*, connection.active_version_id AS config_version_id
                FROM api_models model
                JOIN api_connections connection
                  ON connection.id = model.connection_id
                WHERE model.id = ?
                """,
                (model_id,),
            ).fetchone()
        if row is None:
            raise ValueError("所选模型不存在")
        model = dict(row)
        if not model["active"] or model["validation_status"] != "validated":
            raise ValueError("所选模型必须已启用并验证通过")
        if not model.get("config_version_id"):
            raise ValueError("所选模型所在接入尚未发布配置")
        supported = json.loads(str(model["supported_efforts_json"]))
        if effort not in supported:
            raise ValueError("所选模型不支持该推理强度")
        return model
