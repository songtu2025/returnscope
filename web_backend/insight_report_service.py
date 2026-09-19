from __future__ import annotations

import builtins
import hashlib
import json
from dataclasses import replace
from typing import Any, Callable

from return_semantics.model_client import Sub2APIClient
from web_backend import (
    insight_report_consistency,
    insight_report_content,
    insight_report_contracts,
    insight_report_decision_blueprint,
    insight_report_diagnostics,
    insight_report_evidence,
    insight_report_legacy_blueprint,
    insight_report_quality,
    insight_report_quality_v6,
)
from web_backend.common import json_text, json_value, new_id
from web_backend.config_service import ConfigService
from web_backend.dashboard_service import DashboardService
from web_backend.database import Database
from web_backend.model_catalog import validate_effort
from web_backend.security import utc_now

V5_PROMPT_VERSION = insight_report_contracts.V5_PROMPT_VERSION
PROMPT_VERSION = insight_report_contracts.PROMPT_VERSION
ReportSummaryItem = insight_report_contracts.ReportSummaryItem
ReportFinding = insight_report_contracts.ReportFinding
ReportAction = insight_report_contracts.ReportAction
InsightReportContent = insight_report_contracts.InsightReportContent
ReportIssueScope = insight_report_contracts.ReportIssueScope
ReportIssueMetrics = insight_report_contracts.ReportIssueMetrics
ReportIssueReadiness = insight_report_contracts.ReportIssueReadiness
ReportIssueRecommendation = insight_report_contracts.ReportIssueRecommendation
ReportIssue = insight_report_contracts.ReportIssue
InsightDecisionReportContent = insight_report_contracts.InsightDecisionReportContent
ReportQualityIssue = insight_report_contracts.ReportQualityIssue
ReportDecisionReadiness = insight_report_contracts.ReportDecisionReadiness
ReportQualityGate = insight_report_contracts.ReportQualityGate
DecisionReportQualityGate = insight_report_contracts.DecisionReportQualityGate

GENERATION_ERROR_MESSAGE = (
    "报告生成未完成，请稍后重试。失败尝试已保留，且不会占用报告版本号。"
)


class InsightReportNotFound(ValueError):
    pass


class InsightReportConflict(ValueError):
    pass


class InsightReportService:
    def __init__(
        self,
        database: Database,
        dashboard_service: DashboardService,
        config_service: ConfigService,
        client_factory: Callable[[Any], Sub2APIClient] = Sub2APIClient,
    ) -> None:
        self.database = database
        self.dashboard_service = dashboard_service
        self.config_service = config_service
        self.client_factory = client_factory

    def create_from_results(
        self,
        *,
        result_version_ids: list[str],
        filters: dict[str, Any],
        plan_hash: str,
        model_id: str,
        reasoning_effort: str,
        actor_id: str,
    ) -> dict[str, Any]:
        model = self._resolve_model(model_id, reasoning_effort)
        plan = self.dashboard_service.preflight(result_version_ids, filters)
        if int(plan.get("summary", {}).get("record_count") or 0) <= 0:
            raise ValueError("当前范围没有可用于生成报告的已审核记录")
        listings = sorted(
            {
                str(source.get("listing"))
                for source in plan.get("sources", [])
                if source.get("listing")
            }
        )
        scope_name = (
            listings[0] if len(listings) == 1 else f"{len(listings)} 个 Listing"
        )
        is_returns = all(
            source.get("analysis_context", "returns") == "returns"
            for source in plan.get("sources", [])
        )
        report_name = "AI 退货洞察报告" if is_returns else "AI 用户反馈语义洞察报告"
        dashboard = self.dashboard_service.create(
            name=f"AI 洞察 · {scope_name}",
            description=f"由分类结果自动创建，用于承载 {report_name}。",
            result_version_ids=result_version_ids,
            filters=filters,
            plan_hash=plan_hash,
            reason=f"生成 {report_name}",
            actor_id=actor_id,
        )
        report = self._create_report(
            dashboard_id=str(dashboard["id"]),
            dashboard_version_id=str(dashboard["version"]["version_id"]),
            model=model,
            reasoning_effort=reasoning_effort,
            actor_id=actor_id,
        )
        return {"dashboard": dashboard, "report": report}

    def create_for_dashboard(
        self,
        dashboard_id: str,
        dashboard_version_id: str,
        *,
        model_id: str,
        reasoning_effort: str,
        actor_id: str,
    ) -> dict[str, Any]:
        self.dashboard_service.get(dashboard_id, dashboard_version_id)
        model = self._resolve_model(model_id, reasoning_effort)
        return self._create_report(
            dashboard_id=dashboard_id,
            dashboard_version_id=dashboard_version_id,
            model=model,
            reasoning_effort=reasoning_effort,
            actor_id=actor_id,
        )

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
            dashboard_id=str(source["dashboard_id"]),
            dashboard_version_id=str(source["dashboard_version_id"]),
            model={
                "id": source["model_id"],
                "model_key": source["model_key"],
                "config_version_id": source["config_version_id"],
            },
            reasoning_effort=str(source["reasoning_effort"]),
            actor_id=actor_id,
            parent_job_id=report_id,
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
                self._compact_diagnostic(
                    self.dashboard_service.insights(
                        str(report["dashboard_id"]),
                        str(report["dashboard_version_id"]),
                        problem=reason_code,
                    )
                )
                for reason_code in reason_codes
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

    def _create_report(
        self,
        *,
        dashboard_id: str,
        dashboard_version_id: str,
        model: dict[str, Any],
        reasoning_effort: str,
        actor_id: str,
        parent_job_id: str | None = None,
    ) -> dict[str, Any]:
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

    _diagnostic_reason_codes = staticmethod(
        insight_report_diagnostics._diagnostic_reason_codes
    )
    _trend_summary = staticmethod(insight_report_diagnostics._trend_summary)
    _rank_hotspots = staticmethod(insight_report_diagnostics._rank_hotspots)
    _compact_diagnostic = staticmethod(insight_report_diagnostics._compact_diagnostic)
    _has_text_anomaly = staticmethod(insight_report_diagnostics._has_text_anomaly)
    _filter_diagnostic_text = staticmethod(
        insight_report_diagnostics._filter_diagnostic_text
    )
    _filter_issue_case_text = staticmethod(
        insight_report_diagnostics._filter_issue_case_text
    )
    _filter_business_issue_text = staticmethod(
        insight_report_diagnostics._filter_business_issue_text
    )
    _build_business_issues = staticmethod(
        insight_report_diagnostics._build_business_issues
    )
    _product_mapping_check = staticmethod(
        insight_report_diagnostics._product_mapping_check
    )
    _build_evidence = staticmethod(insight_report_evidence._build_evidence)
    _build_decision_blueprint = staticmethod(
        insight_report_decision_blueprint._build_decision_blueprint
    )
    _build_blueprint = staticmethod(insight_report_legacy_blueprint._build_blueprint)
    _messages_v6 = staticmethod(insight_report_content._messages_v6)
    _assemble_content_v6 = staticmethod(insight_report_content._assemble_content_v6)
    _messages = staticmethod(insight_report_content._messages)
    _assemble_content = staticmethod(insight_report_content._assemble_content)
    _items_by_id = staticmethod(insight_report_content._items_by_id)
    _text = staticmethod(insight_report_content._text)
    _narrative_text = staticmethod(insight_report_content._narrative_text)
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
    _evaluate_live_quality_v6 = staticmethod(
        insight_report_quality_v6._evaluate_live_quality_v6
    )
    _evaluate_live_quality = staticmethod(insight_report_quality._evaluate_live_quality)

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

    @staticmethod
    def _serialize(
        value: dict[str, Any],
        *,
        text_quality: dict[str, Any] | None = None,
        decisions: builtins.list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        value["attempt_no"] = int(value.pop("version_no"))
        published_version = value.pop("published_version_no", None)
        value["version_no"] = (
            int(published_version) if published_version is not None else None
        )
        value["kind"] = "report" if published_version is not None else "generation_job"
        value["content"] = json_value(value.pop("content_json"), None)
        value["evidence"] = json_value(value.pop("evidence_json"), None)
        value["usage"] = json_value(value.pop("usage_json"), {})
        value["metrics"] = json_value(value.pop("metrics_json"), {})
        value["decisions"] = decisions or []
        if value["content"] and value["evidence"] and text_quality is not None:
            evaluator = (
                InsightReportService._evaluate_live_quality_v6
                if value.get("prompt_version") == PROMPT_VERSION
                else InsightReportService._evaluate_live_quality
            )
            evaluated = evaluator(value["content"], value["evidence"], text_quality)
            value.update(evaluated)
        value.pop("technical_error", None)
        return value
