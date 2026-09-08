from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import replace
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field

from return_semantics.model_client import Sub2APIClient
from web_backend.common import json_text, json_value, new_id
from web_backend.config_service import ConfigService
from web_backend.dashboard_service import TEXT_ENCODING_ANOMALY, DashboardService
from web_backend.database import Database
from web_backend.insight_report_profiles import (
    get_insight_report_profile,
    resolve_insight_report_profile,
)
from web_backend.model_catalog import validate_effort
from web_backend.security import utc_now

V5_PROMPT_VERSION = "ai-return-insight-v5"
PROMPT_VERSION = "ai-return-insight-v6"
GENERATION_ERROR_MESSAGE = (
    "报告生成未完成，请稍后重试。失败尝试已保留，且不会占用报告版本号。"
)


class InsightReportNotFound(ValueError):
    pass


class InsightReportConflict(ValueError):
    pass


class ReportSummaryItem(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    statement: str = Field(min_length=1, max_length=500)
    tone: Literal["primary", "neutral", "warning"] = "neutral"
    evidence_ids: list[str] = Field(min_length=1)


class ReportFinding(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    kind: Literal["structure", "diagnostic", "information"]
    title: str = Field(min_length=1, max_length=120)
    conclusion: str = Field(min_length=1, max_length=500)
    interpretation: str = Field(min_length=1, max_length=800)
    implication: str = Field(min_length=1, max_length=500)
    evidence_ids: list[str] = Field(min_length=1)


class ReportAction(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    priority: Literal["P0", "P1", "P2"]
    target: str = Field(min_length=1, max_length=160)
    action: str = Field(min_length=1, max_length=300)
    rationale: str = Field(min_length=1, max_length=500)
    success_signal: str = Field(min_length=1, max_length=300)
    evidence_ids: list[str] = Field(min_length=1)


class InsightReportContent(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    executive_summary: list[ReportSummaryItem] = Field(min_length=2, max_length=4)
    findings: list[ReportFinding] = Field(min_length=2, max_length=6)
    actions: list[ReportAction] = Field(min_length=2, max_length=6)
    further_questions: list[str] = Field(default_factory=list, max_length=5)
    caveats: list[str] = Field(min_length=1)


class ReportIssueScope(BaseModel):
    category: str | None = Field(default=None, max_length=120)
    listing: str | None = Field(default=None, max_length=200)
    product: str | None = Field(default=None, max_length=300)
    sku: str | None = Field(default=None, max_length=200)


class ReportIssueMetrics(BaseModel):
    matched_return_samples: int = Field(ge=0)
    scoped_return_samples: int = Field(ge=0)
    return_sample_share: float = Field(ge=0, le=100)
    baseline_return_sample_share: float | None = Field(default=None, ge=0, le=100)
    gap_percentage_points: float | None = None
    lift: float | None = Field(default=None, ge=0)
    recent_change_percentage_points: float | None = None
    trend_direction: Literal["rising", "stable", "falling", "insufficient"]


class ReportIssueReadiness(BaseModel):
    status: Literal["unusable", "diagnostic_only", "verification_ready"]
    label: str = Field(min_length=1, max_length=40)
    reason: str = Field(min_length=1, max_length=500)


class ReportIssueRecommendation(BaseModel):
    label: Literal["建议验证"] = "建议验证"
    validation_question: str = Field(min_length=1, max_length=300)
    rationale: str = Field(min_length=1, max_length=500)
    suggested_evidence: list[str] = Field(min_length=1, max_length=5)


class ReportIssue(BaseModel):
    id: str = Field(min_length=1, max_length=160)
    rank: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=200)
    scope: ReportIssueScope
    metrics: ReportIssueMetrics
    known: list[str] = Field(min_length=1, max_length=6)
    evidence_explanation: str = Field(min_length=1, max_length=800)
    unknown: list[str] = Field(min_length=1, max_length=5)
    recommendation: ReportIssueRecommendation
    readiness: ReportIssueReadiness
    evidence_ids: list[str] = Field(min_length=1)


class InsightDecisionReportContent(BaseModel):
    report_type: Literal["problem_decision"] = "problem_decision"
    title: str = Field(min_length=1, max_length=120)
    issues: list[ReportIssue] = Field(min_length=1, max_length=8)
    caveats: list[str] = Field(min_length=1, max_length=8)


class ReportQualityIssue(BaseModel):
    code: Literal[
        "report_consistency",
        "text_quality",
        "product_mapping",
        "pending_review",
    ]
    label: str = Field(min_length=1, max_length=80)
    detail: str = Field(min_length=1, max_length=500)
    evidence_ids: list[str] = Field(default_factory=list)


class ReportDecisionReadiness(BaseModel):
    status: Literal["actionable", "diagnostic_only", "unusable"]
    label: str = Field(min_length=1, max_length=40)
    reason: str = Field(min_length=1, max_length=500)


class ReportQualityGate(BaseModel):
    status: Literal["passed", "warning", "blocked"]
    issues: list[ReportQualityIssue]
    text_quality: dict[str, Any]
    product_mapping: dict[str, Any]
    consistency: dict[str, Any]
    decision_readiness: ReportDecisionReadiness


class DecisionReportQualityGate(BaseModel):
    status: Literal["passed", "warning", "blocked"]
    issues: list[ReportQualityIssue]
    text_quality: dict[str, Any]
    product_mapping: dict[str, Any]
    consistency: dict[str, Any]
    decision_readiness: ReportIssueReadiness


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
        dashboard = self.dashboard_service.create(
            name=f"AI 洞察 · {scope_name}",
            description="由分类结果自动创建，用于承载 AI 退货洞察报告。",
            result_version_ids=result_version_ids,
            filters=filters,
            plan_hash=plan_hash,
            reason="生成 AI 退货洞察报告",
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
                content = self._assemble_content_v6(evidence, result.payload)
                self._validate_issue_evidence_refs(
                    content,
                    set(evidence["catalog"]),
                )
                consistency = self._decision_report_consistency(
                    content.model_dump(),
                    evidence,
                )
            else:
                content = self._assemble_content(evidence, result.payload)
                self._validate_evidence_refs(content, set(evidence["catalog"]))
                consistency = self._report_consistency(
                    content.model_dump(),
                    evidence,
                    require_information_diagnostics=True,
                )
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
                        content.model_dump_json(),
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

    @staticmethod
    def _diagnostic_reason_codes(analysis: dict[str, Any]) -> list[str]:
        reasons = list(analysis.get("reasons", []))[:15]
        profile = resolve_insight_report_profile(analysis.get("sources"))
        reason_by_code = {
            str(reason.get("value") or ""): reason for reason in reasons
        }
        selected: list[str] = []
        actionable = [
            reason
            for reason in reasons
            if "PRODUCT" in reason.get("subjects", [])
            and str(reason.get("label_group") or "") != "其他原因"
        ]
        broad_reason = next(
            (
                reason
                for reason in reasons
                if len(reason.get("subjects", [])) > 1
                or str(reason.get("label_group") or "") == "其他原因"
            ),
            None,
        )
        candidates = [
            reason_by_code[code]
            for code in profile.preferred_reason_codes
            if code in reason_by_code
        ]
        candidates.extend(actionable[:2])
        if broad_reason:
            candidates.append(broad_reason)
        if not candidates and reasons:
            candidates.append(reasons[0])

        for reason in candidates:
            code = str(reason.get("value") or "")
            if code and code not in selected:
                selected.append(code)
        return [code for code in selected if code][:4]

    @staticmethod
    def _trend_summary(
        trend: list[dict[str, Any]],
        date_to: str | None,
    ) -> dict[str, Any]:
        usable = [
            item
            for item in trend
            if not item.get("low_sample")
            and (not date_to or str(item.get("period_end") or "") <= date_to)
        ]
        if len(usable) < 8:
            return {"status": "insufficient", "point_count": len(usable)}

        window = min(4, len(usable) // 2)
        early = sum(float(item.get("percentage") or 0) for item in usable[:window])
        recent = sum(float(item.get("percentage") or 0) for item in usable[-window:])
        early_rate = round(early / window, 1)
        recent_rate = round(recent / window, 1)
        delta = round(recent_rate - early_rate, 1)
        direction = "stable"
        if delta >= 2:
            direction = "rising"
        elif delta <= -2:
            direction = "falling"
        return {
            "status": "available",
            "point_count": len(usable),
            "window_weeks": window,
            "early_rate": early_rate,
            "recent_rate": recent_rate,
            "delta_percentage_points": delta,
            "direction": direction,
            "early_period": {
                "date_from": usable[0].get("period_start"),
                "date_to": usable[window - 1].get("period_end"),
            },
            "recent_period": {
                "date_from": usable[-window].get("period_start"),
                "date_to": usable[-1].get("period_end"),
            },
        }

    @staticmethod
    def _rank_hotspots(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
        hotspots = []
        for product in products:
            total = int(product.get("total_record_count") or 0)
            related = int(product.get("record_count") or 0)
            baseline = float(product.get("overall_reason_rate") or 0)
            excess = round(related - total * baseline / 100)
            if (
                product.get("reliable")
                and related >= 10
                and float(product.get("lift") or 0) > 1
                and excess > 0
            ):
                hotspots.append({**product, "excess_record_count": excess})
        return sorted(
            hotspots,
            key=lambda item: (
                int(item.get("excess_record_count") or 0),
                float(item.get("lift") or 0),
            ),
            reverse=True,
        )[:4]

    @staticmethod
    def _compact_diagnostic(data: dict[str, Any]) -> dict[str, Any]:
        date_range = data.get("date_range", {})
        trend = list(data.get("trend", []))
        selected_reason = data.get("selected_reason") or {}
        samples = [
            {
                "comment": item.get("comment"),
                "reason": item.get("reason"),
                "product_name": item.get("product_name"),
                "product_sku": item.get("product_sku"),
                "return_date": item.get("return_date"),
                "problem_labels": item.get("problem_labels", []),
            }
            for item in data.get("evidence", {}).get("items", [])[:4]
        ]
        semantic_profile = data.get("semantic_profile", {})
        return {
            "reason_code": selected_reason.get("value"),
            "selected_reason": selected_reason,
            "date_range": date_range,
            "trend": trend[:36],
            "trend_summary": InsightReportService._trend_summary(
                trend,
                str(date_range.get("date_to") or "") or None,
            ),
            "hotspots": InsightReportService._rank_hotspots(
                list(data.get("products", []))
            ),
            "variants": InsightReportService._rank_hotspots(
                list(data.get("variants", []))
            ),
            "co_reasons": list(data.get("co_reasons", []))[:6],
            "semantic_profile": {
                "record_count": semantic_profile.get("record_count", 0),
                "coverage": semantic_profile.get("coverage", 0),
                "parts": list(semantic_profile.get("parts", []))[:6],
                "opinions": list(semantic_profile.get("opinions", []))[:4],
            },
            "samples": samples,
        }

    @staticmethod
    def _has_text_anomaly(*values: Any) -> bool:
        text = " ".join(str(value or "") for value in values)
        return bool(TEXT_ENCODING_ANOMALY.search(text))

    @staticmethod
    def _filter_diagnostic_text(
        diagnostic: dict[str, Any],
    ) -> dict[str, Any]:
        semantic_profile = diagnostic.get("semantic_profile", {})
        opinions = [
            opinion
            for opinion in semantic_profile.get("opinions", [])
            if not InsightReportService._has_text_anomaly(
                opinion.get("opinion"),
                opinion.get("evidence"),
            )
        ]
        samples = [
            sample
            for sample in diagnostic.get("samples", [])
            if not InsightReportService._has_text_anomaly(
                sample.get("comment"),
                sample.get("reason"),
            )
        ]
        return {
            **diagnostic,
            "semantic_profile": {
                **semantic_profile,
                "opinions": opinions,
            },
            "samples": samples,
            "text_evidence": {
                "status": "available" if opinions or samples else "limited",
                "opinion_count": len(opinions),
                "sample_count": len(samples),
            },
        }

    @staticmethod
    def _filter_issue_case_text(case: dict[str, Any]) -> dict[str, Any]:
        semantic_profile = case.get("semantic_profile", {})
        opinions = [
            opinion
            for opinion in semantic_profile.get("opinions", [])
            if not InsightReportService._has_text_anomaly(
                opinion.get("opinion"),
                opinion.get("evidence"),
            )
        ]
        samples = [
            sample
            for sample in case.get("samples", [])
            if not InsightReportService._has_text_anomaly(
                sample.get("comment"),
                sample.get("reason"),
            )
        ]
        return {
            **case,
            "semantic_profile": {
                **semantic_profile,
                "opinions": opinions,
            },
            "samples": samples,
        }

    @staticmethod
    def _filter_business_issue_text(
        issue: dict[str, Any],
    ) -> dict[str, Any]:
        contexts = issue.get("contexts", {})
        opinions = [
            opinion
            for opinion in contexts.get("opinions", [])
            if not InsightReportService._has_text_anomaly(
                opinion.get("opinion"),
                opinion.get("evidence"),
            )
        ]
        samples = [
            sample
            for sample in contexts.get("samples", [])
            if not InsightReportService._has_text_anomaly(
                sample.get("comment"),
                sample.get("reason"),
            )
        ]
        return {
            **issue,
            "contexts": {
                **contexts,
                "opinions": opinions,
                "samples": samples,
            },
        }

    @staticmethod
    def _build_business_issues(
        diagnostics: list[dict[str, Any]],
        issue_cases: list[dict[str, Any]],
        *,
        profile: Any,
    ) -> list[dict[str, Any]]:
        preferred_codes = set(profile.preferred_reason_codes)
        cases_by_code: dict[str, list[dict[str, Any]]] = {}
        for case in issue_cases:
            code = str(case.get("reason_code") or "")
            if code:
                cases_by_code.setdefault(code, []).append(case)
        issues = []
        for diagnostic in diagnostics:
            reason = diagnostic.get("selected_reason") or {}
            code = str(diagnostic.get("reason_code") or "")
            if not code:
                continue
            cases = []
            for case in cases_by_code.get(code, [])[:3]:
                trend = list(case.get("trend", []))
                cases.append(
                    {
                        **case,
                        "value": str(case.get("product_sku") or ""),
                        "product_reason_rate": float(case.get("issue_rate") or 0),
                        "overall_reason_rate": float(case.get("overall_rate") or 0),
                        "trend_summary": InsightReportService._trend_summary(
                            trend,
                            str(
                                diagnostic.get("date_range", {}).get("date_to")
                                or ""
                            )
                            or None,
                        ),
                    }
                )

            if cases:
                dimension = "variant"
                hotspots = cases
                primary_case = cases[0]
                trend_summary = primary_case["trend_summary"]
                trend = list(primary_case.get("trend", []))
                semantic_profile = primary_case.get("semantic_profile", {})
                opinions = list(semantic_profile.get("opinions", []))[:3]
                samples = list(primary_case.get("samples", []))[:3]
                parts = list(semantic_profile.get("parts", []))[:4]
                top_opinion = next(iter(opinions), None)
                validation_focus = (
                    f"先复核 {primary_case.get('product_sku')} 中"
                    f"“{top_opinion.get('opinion')}”对应的评论，"
                    "再核对实物规格、页面说明与使用情境"
                    if top_opinion
                    else (
                        f"先复核 {primary_case.get('product_sku')} 的"
                        f"{reason.get('label') or code}评论，再核对实物和页面说明"
                    )
                )
            else:
                dimension = (
                    "variant" if diagnostic.get("variants") else "product"
                )
                hotspots = list(
                    diagnostic.get(
                        "variants" if dimension == "variant" else "hotspots",
                        [],
                    )
                )[:3]
                trend_summary = diagnostic.get("trend_summary", {})
                trend = list(diagnostic.get("trend", []))
                semantic_profile = diagnostic.get("semantic_profile", {})
                opinions = list(semantic_profile.get("opinions", []))[:3]
                samples = list(diagnostic.get("samples", []))[:3]
                parts = list(semantic_profile.get("parts", []))[:4]
                validation_focus = profile.diagnostic_action

            evidence_ids = [f"reason.{code}"]
            if cases:
                evidence_ids.extend(str(case.get("id")) for case in cases)
                primary_id = str(cases[0].get("id"))
                if cases[0].get("trend"):
                    evidence_ids.append(f"{primary_id}.trend")
                evidence_ids.extend(
                    f"{primary_id}.opinion.{index}"
                    for index in range(1, len(opinions) + 1)
                )
                evidence_ids.extend(
                    f"{primary_id}.sample.{index}"
                    for index in range(1, len(samples) + 1)
                )
            elif trend_summary.get("status") == "available":
                evidence_ids.append(f"diagnostic.{code}.trend")
                evidence_ids.extend(
                    f"diagnostic.{code}.{dimension}.{index}"
                    for index in range(1, len(hotspots) + 1)
                )
                evidence_ids.extend(
                    f"diagnostic.{code}.opinion.{index}"
                    for index in range(1, len(opinions) + 1)
                )
                evidence_ids.extend(
                    f"diagnostic.{code}.sample.{index}"
                    for index in range(1, len(samples) + 1)
                )
            issues.append(
                {
                    "id": f"business_issue.{code}",
                    "reason_code": code,
                    "label": str(reason.get("label") or code),
                    "label_group": str(reason.get("label_group") or ""),
                    "role": (
                        "supporting"
                        if (
                            str(reason.get("label_group") or "") == "其他原因"
                            or len(reason.get("subjects", [])) > 1
                        )
                        else "primary"
                        if not preferred_codes or code in preferred_codes
                        else "supporting"
                    ),
                    "record_count": int(reason.get("record_count") or 0),
                    "percentage": float(reason.get("percentage") or 0),
                    "trend_summary": trend_summary,
                    "trend": trend,
                    "hotspot_dimension": dimension,
                    "hotspot_label": (
                        profile.variant_label if dimension == "variant" else "商品"
                    ),
                    "hotspots": hotspots,
                    "cases": cases,
                    "contexts": {
                        "parts": parts,
                        "opinions": opinions,
                        "samples": samples,
                    },
                    "validation_focus": validation_focus,
                    "evidence_ids": list(dict.fromkeys(evidence_ids)),
                }
            )
        return issues

    @staticmethod
    def _product_mapping_check(
        summary: dict[str, Any],
        listings: list[str],
    ) -> dict[str, Any]:
        unmatched = int(summary.get("product_unmatched_count") or 0)
        missing = int(summary.get("product_name_missing_count") or 0)
        listing = str(listings[0]).strip() if len(listings) == 1 else None
        if not unmatched and not missing:
            return {
                "status": "consistent",
                "listing": listing,
                "unmatched_record_count": 0,
                "missing_name_record_count": 0,
                "examples": [],
                "note": "商品关系以已发布商品主数据为准，未发现未匹配记录。",
            }

        return {
            "status": "needs_review",
            "listing": listing,
            "unmatched_record_count": unmatched,
            "missing_name_record_count": missing,
            "examples": [],
            "note": (
                f"当前有 {unmatched} 条未匹配商品记录、{missing} 条缺少商品名称，"
                "商品级行动前需补全已发布商品主数据关系。"
            ),
        }

    @staticmethod
    def _build_evidence(
        analysis: dict[str, Any],
        *,
        prompt_version: str = V5_PROMPT_VERSION,
    ) -> dict[str, Any]:
        summary = analysis.get("summary", {})
        groups = list(analysis.get("label_group_breakdown", []))[:12]
        reasons = list(analysis.get("reasons", []))[:15]
        subjects = list(analysis.get("subject_breakdown", []))[:10]
        products = list(analysis.get("product_reason_matrix", []))[:8]
        diagnostics = list(analysis.get("diagnostics", []))[:4]
        issue_cases = list(analysis.get("issue_cases", []))[:12]
        review_bias = analysis.get("review_bias", {})
        text_quality = analysis.get("text_quality", {})
        listings = list(analysis.get("filter_options", {}).get("listings", []))
        product_names = list(
            analysis.get("filter_options", {}).get("product_names", [])
        )
        sources = list(analysis.get("sources", []))
        profile = resolve_insight_report_profile(sources)
        product_mapping = InsightReportService._product_mapping_check(
            summary,
            listings,
        )
        mapping_trusted = product_mapping.get("status") != "needs_review"
        text_trusted = text_quality.get("status") != "needs_review"
        product_level_trusted = mapping_trusted
        safe_products = products if product_level_trusted else []
        safe_diagnostics = deepcopy(diagnostics)
        safe_issue_cases = deepcopy(issue_cases) if product_level_trusted else []
        if not product_level_trusted:
            safe_diagnostics = [
                {
                    **diagnostic,
                    "hotspots": [],
                    "variants": [],
                    "samples": [
                        {
                            **sample,
                            "product_name": None,
                            "product_sku": None,
                        }
                        for sample in diagnostic.get("samples", [])
                    ],
                }
                for diagnostic in diagnostics
            ]
        if not text_trusted:
            safe_diagnostics = [
                InsightReportService._filter_diagnostic_text(diagnostic)
                for diagnostic in safe_diagnostics
            ]
            safe_issue_cases = [
                InsightReportService._filter_issue_case_text(case)
                for case in safe_issue_cases
            ]
        catalog: dict[str, dict[str, Any]] = {
            "scope": {
                "label": "分析范围",
                "value": (
                    f"纳入 {int(summary.get('record_count') or 0)} 条，"
                    f"待审核 {int(summary.get('pending_review_record_count') or 0)} 条"
                ),
                "data": summary,
            },
            "review_bias": {
                "label": "待审核集中偏差",
                "value": str(review_bias.get("note") or "尚未评估"),
                "data": review_bias,
            },
            "product_mapping": {
                "label": "商品主数据映射",
                "value": str(product_mapping.get("note") or "未发现明显前缀冲突"),
                "data": product_mapping,
            },
            "text_quality": {
                "label": "评论文本质量",
                "value": str(text_quality.get("note") or "尚未评估"),
                "data": text_quality,
            },
            "report_profile": {
                "label": "报告品类配置",
                "value": f"{profile.category_name} · {profile.version}",
                "data": profile.snapshot(),
            },
        }
        for index, group in enumerate(groups, 1):
            catalog[f"group.{index}"] = {
                "label": str(group.get("value") or "其他原因"),
                "value": (
                    f"{int(group.get('record_count') or 0)} 条 · "
                    f"{float(group.get('percentage') or 0):.1f}%"
                ),
                "data": group,
            }
        for reason in reasons:
            code = str(reason.get("value") or "unknown")
            catalog[f"reason.{code}"] = {
                "label": str(reason.get("label") or code),
                "value": (
                    f"{int(reason.get('record_count') or 0)} 条 · "
                    f"{float(reason.get('percentage') or 0):.1f}%"
                ),
                "data": reason,
            }
        for subject in subjects:
            code = str(subject.get("value") or "unknown")
            catalog[f"subject.{code}"] = {
                "label": str(subject.get("label") or code),
                "value": (
                    f"{int(subject.get('record_count') or 0)} 条 · "
                    f"{float(subject.get('percentage') or 0):.1f}%"
                ),
                "data": subject,
            }
        for index, product in enumerate(safe_products, 1):
            catalog[f"product.{index}"] = {
                "label": str(product.get("value") or f"商品 {index}"),
                "value": f"{int(product.get('total_record_count') or 0)} 条已分析退货",
                "data": product,
            }
        for case in safe_issue_cases:
            case_id = str(case.get("id") or "")
            if not case_id:
                continue
            catalog[case_id] = {
                "label": (
                    f"{case.get('label') or case.get('reason_code')} · "
                    f"{case.get('product_sku') or '未提供 SKU'}"
                ),
                "value": (
                    f"{int(case.get('record_count') or 0)} / "
                    f"{int(case.get('total_record_count') or 0)} 条，"
                    f"变体内 {float(case.get('issue_rate') or 0):.1f}%，"
                    f"整体 {float(case.get('overall_rate') or 0):.1f}%，"
                    f"{float(case.get('lift') or 0):.2f}×"
                ),
                "data": case,
            }
            if case.get("trend"):
                catalog[f"{case_id}.trend"] = {
                    "label": f"{case.get('product_sku') or '商品变体'}问题趋势",
                    "value": f"{len(case.get('trend', []))} 个周度数据点",
                    "data": case.get("trend", []),
                }
            for index, opinion in enumerate(
                case.get("semantic_profile", {}).get("opinions", []),
                1,
            ):
                catalog[f"{case_id}.opinion.{index}"] = {
                    "label": str(opinion.get("opinion") or f"高频表述 {index}"),
                    "value": f"{int(opinion.get('record_count') or 0)} 条",
                    "data": opinion,
                }
            for index, sample in enumerate(case.get("samples", []), 1):
                text = str(sample.get("comment") or sample.get("reason") or "").strip()
                catalog[f"{case_id}.sample.{index}"] = {
                    "label": str(case.get("product_sku") or "原始评论"),
                    "value": text[:160] or "未提供评论",
                    "data": sample,
                }
        samples = []
        seen_samples: set[str] = set()
        for diagnostic in safe_diagnostics:
            code = str(diagnostic.get("reason_code") or "unknown")
            trend_summary = diagnostic.get("trend_summary", {})
            if trend_summary.get("status") == "available":
                catalog[f"diagnostic.{code}.trend"] = {
                    "label": f"{diagnostic.get('selected_reason', {}).get('label') or code}趋势",
                    "value": (
                        f"最早 {trend_summary.get('window_weeks')} 个完整周 "
                        f"{float(trend_summary.get('early_rate') or 0):.1f}% → "
                        f"最近 {trend_summary.get('window_weeks')} 个完整周 "
                        f"{float(trend_summary.get('recent_rate') or 0):.1f}%（"
                        f"{float(trend_summary.get('delta_percentage_points') or 0):+.1f}pp）"
                    ),
                    "data": trend_summary,
                }
            for index, hotspot in enumerate(diagnostic.get("hotspots", []), 1):
                catalog[f"diagnostic.{code}.hotspot.{index}"] = {
                    "label": str(hotspot.get("value") or f"商品 {index}"),
                    "value": (
                        f"{int(hotspot.get('record_count') or 0)} / "
                        f"{int(hotspot.get('total_record_count') or 0)} 条，"
                        f"商品内 {float(hotspot.get('product_reason_rate') or 0):.1f}%，"
                        f"整体 {float(hotspot.get('overall_reason_rate') or 0):.1f}%，"
                        f"{float(hotspot.get('lift') or 0):.2f}×"
                    ),
                    "data": hotspot,
                }
            for index, variant in enumerate(diagnostic.get("variants", []), 1):
                catalog[f"diagnostic.{code}.variant.{index}"] = {
                    "label": str(variant.get("value") or f"商品变体 {index}"),
                    "value": (
                        f"{int(variant.get('record_count') or 0)} / "
                        f"{int(variant.get('total_record_count') or 0)} 条，"
                        f"变体内 {float(variant.get('product_reason_rate') or 0):.1f}%，"
                        f"整体 {float(variant.get('overall_reason_rate') or 0):.1f}%，"
                        f"{float(variant.get('lift') or 0):.2f}×"
                    ),
                    "data": variant,
                }
            opinions = diagnostic.get("semantic_profile", {}).get("opinions", [])
            for index, opinion in enumerate(opinions, 1):
                catalog[f"diagnostic.{code}.opinion.{index}"] = {
                    "label": str(opinion.get("opinion") or f"高频表述 {index}"),
                    "value": f"{int(opinion.get('record_count') or 0)} 条",
                    "data": opinion,
                }
            for index, sample in enumerate(diagnostic.get("samples", []), 1):
                text = str(sample.get("comment") or sample.get("reason") or "").strip()
                sample_id = f"diagnostic.{code}.sample.{index}"
                catalog[sample_id] = {
                    "label": str(sample.get("product_name") or "原始评论"),
                    "value": text[:160] or "未提供评论",
                    "data": sample,
                }
                if text and text not in seen_samples and len(samples) < 8:
                    samples.append(
                        {**sample, "reason_code": code, "evidence_id": sample_id}
                    )
                    seen_samples.add(text)
        business_issues = InsightReportService._build_business_issues(
            safe_diagnostics,
            safe_issue_cases,
            profile=profile,
        )
        for issue in business_issues:
            catalog[issue["id"]] = {
                "label": str(issue.get("label") or "业务问题"),
                "value": (
                    f"{int(issue.get('record_count') or 0)} 条 · "
                    f"{float(issue.get('percentage') or 0):.1f}%"
                ),
                "data": issue,
            }
        total_record_count = int(
            summary.get("total_record_count") or summary.get("record_count") or 0
        )
        pending_review_count = int(summary.get("pending_review_record_count") or 0)
        coverage_rate = float(
            summary.get("coverage_rate")
            if summary.get("coverage_rate") is not None
                else (100 if total_record_count else 0)
        )
        checked_comment_count = int(
            text_quality.get("checked_record_count") or 0
        )
        anomaly_comment_count = int(
            text_quality.get("anomaly_record_count") or 0
        )
        clean_comment_count = max(
            checked_comment_count - anomaly_comment_count,
            0,
        )
        clean_comment_rate = round(
            clean_comment_count / checked_comment_count * 100,
            1,
        ) if checked_comment_count else 0.0
        quality_issue_codes = []
        if pending_review_count:
            quality_issue_codes.append("pending_review")
        if not text_trusted:
            quality_issue_codes.append("text_quality")
        if not mapping_trusted:
            quality_issue_codes.append("product_mapping")
        evidence = {
            "source": {
                "dashboard_id": analysis.get("dashboard_id"),
                "dashboard_version_id": analysis.get("version_id"),
                "date_range": analysis.get("date_range", {}),
                "label_coverage": analysis.get("label_coverage", 0),
                "listings": listings,
                "product_count": len(product_names),
                "total_record_count": total_record_count,
                "included_record_count": int(summary.get("record_count") or 0),
                "pending_review_record_count": pending_review_count,
                "coverage_rate": coverage_rate,
                "product_mapping": product_mapping,
                "text_quality": text_quality,
                "clean_comment_record_count": clean_comment_count,
                "clean_comment_rate": clean_comment_rate,
                "quality_issue_codes": quality_issue_codes,
                "report_status": "provisional" if quality_issue_codes else "final",
                "agent_keys": sorted(
                    {
                        str(source.get("agent_key"))
                        for source in sources
                        if source.get("agent_key")
                    }
                ),
                "taxonomy_versions": sorted(
                    {
                        str(
                            source.get("taxonomy_version")
                            or source.get("taxonomy_version_id")
                        )
                        for source in sources
                        if source.get("taxonomy_version")
                        or source.get("taxonomy_version_id")
                    }
                ),
                "report_profile": profile.snapshot(),
            },
            "catalog": catalog,
            "analysis": {
                "summary": summary,
                "label_group_breakdown": groups,
                "reasons": reasons,
                "subject_breakdown": subjects,
                "product_reason_matrix": safe_products,
                "diagnostics": safe_diagnostics,
                "issue_cases": safe_issue_cases,
                "business_issues": business_issues,
                "review_bias": review_bias,
                "text_quality": text_quality,
                "report_profile": profile.snapshot(),
                "samples": samples,
            },
        }
        evidence["blueprint"] = (
            InsightReportService._build_decision_blueprint(evidence)
            if prompt_version == PROMPT_VERSION
            else InsightReportService._build_blueprint(evidence)
        )
        return evidence

    @staticmethod
    def _build_decision_blueprint(evidence: dict[str, Any]) -> dict[str, Any]:
        source = evidence["source"]
        analysis = evidence["analysis"]
        catalog = evidence["catalog"]
        profile = get_insight_report_profile(
            source.get("report_profile", {}).get("key")
        )
        listings = list(source.get("listings", []))
        listing = str(listings[0]) if len(listings) == 1 else None
        category = profile.category_name if profile.key != "generic" else None
        source_limited = bool(source.get("quality_issue_codes"))
        candidates = []

        for business_issue in analysis.get("business_issues", []):
            code = str(business_issue.get("reason_code") or "")
            if not code:
                continue
            rows = list(business_issue.get("cases", []))
            dimension = str(business_issue.get("hotspot_dimension") or "product")
            if not rows:
                rows = list(business_issue.get("hotspots", []))
            if not rows:
                rows = [None]

            for index, row in enumerate(rows[:2], 1):
                row = row or {}
                case_id = str(row.get("id") or "")
                value = str(row.get("value") or "").strip()
                product = str(row.get("product_name") or "").strip() or None
                sku = str(row.get("product_sku") or "").strip() or None
                if not case_id and value:
                    if dimension == "variant":
                        sku = value
                    else:
                        product = value

                issue_id = case_id
                if not issue_id:
                    if not product and not sku:
                        issue_id = f"issue.reason.{code}"
                    else:
                        identity = "\x1f".join(
                            [code, dimension, product or "", sku or ""]
                        )
                        suffix = hashlib.sha256(
                            identity.encode("utf-8")
                        ).hexdigest()[:12]
                        issue_id = f"issue.{code}.{suffix}"

                matched = int(
                    row.get("record_count")
                    or business_issue.get("record_count")
                    or 0
                )
                scoped = int(
                    row.get("total_record_count")
                    or source.get("included_record_count")
                    or 0
                )
                share = float(
                    row.get("product_reason_rate")
                    if row.get("product_reason_rate") is not None
                    else row.get("issue_rate")
                    if row.get("issue_rate") is not None
                    else business_issue.get("percentage")
                    or 0
                )
                baseline_value = (
                    row.get("overall_reason_rate")
                    if row.get("overall_reason_rate") is not None
                    else row.get("overall_rate")
                )
                baseline = (
                    float(baseline_value) if baseline_value is not None else None
                )
                gap = round(share - baseline, 1) if baseline is not None else None
                lift_value = row.get("lift")
                lift = float(lift_value) if lift_value is not None else None
                trend = row.get("trend_summary") or business_issue.get(
                    "trend_summary", {}
                )
                trend_available = trend.get("status") == "available"
                recent_change = (
                    float(trend.get("delta_percentage_points") or 0)
                    if trend_available
                    else None
                )
                direction = (
                    str(trend.get("direction") or "stable")
                    if trend_available
                    else "insufficient"
                )
                if direction not in {"rising", "stable", "falling"}:
                    direction = "insufficient"

                evidence_ids = [f"reason.{code}", "scope"]
                if case_id:
                    evidence_ids.insert(1, case_id)
                    evidence_ids.extend(
                        evidence_id
                        for evidence_id in (
                            f"{case_id}.trend",
                            f"{case_id}.opinion.1",
                            f"{case_id}.sample.1",
                        )
                        if evidence_id in catalog
                    )
                else:
                    evidence_dimension = (
                        "variant" if dimension == "variant" else "hotspot"
                    )
                    hotspot_id = f"diagnostic.{code}.{evidence_dimension}.{index}"
                    for evidence_id in (
                        hotspot_id,
                        f"diagnostic.{code}.trend",
                        f"diagnostic.{code}.opinion.1",
                        f"diagnostic.{code}.sample.1",
                    ):
                        if evidence_id in catalog:
                            evidence_ids.append(evidence_id)
                evidence_ids = list(dict.fromkeys(evidence_ids))

                label = str(business_issue.get("label") or code)
                target = sku or product
                title = f"{target} · {label}" if target else label
                known = [
                    f"{matched} / {scoped} 条退货样本命中“{label}”，"
                    f"退货样本内占比 {share:.1f}%。"
                ]
                if baseline is not None:
                    known.append(
                        f"相同范围整体基线为 {baseline:.1f}%，"
                        f"当前高出 {gap:+.1f} 个百分点。"
                    )
                if trend_available:
                    known.append(
                        f"最近窗口较早期同长度窗口变化 {recent_change:+.1f} 个百分点。"
                    )
                top_opinion = next(
                    iter(business_issue.get("contexts", {}).get("opinions", [])),
                    None,
                )
                if top_opinion:
                    known.append(
                        f"高频反馈为“{top_opinion.get('opinion')}”，"
                        f"覆盖 {int(top_opinion.get('record_count') or 0)} 条记录。"
                    )

                concrete_scope = bool(product or sku)
                reliable = bool(row.get("reliable", concrete_scope))
                if source_limited:
                    readiness = {
                        "status": "diagnostic_only",
                        "label": "仅供诊断",
                        "reason": "当前仍有数据质量或待审核问题，需先补齐证据。",
                    }
                elif not concrete_scope or not reliable or matched < 10 or scoped < 10:
                    readiness = {
                        "status": "diagnostic_only",
                        "label": "仅供诊断",
                        "reason": "当前信号尚未形成稳定的商品范围或样本基础。",
                    }
                else:
                    readiness = {
                        "status": "verification_ready",
                        "label": "可进入验证",
                        "reason": "样本量、对照基线和可追溯证据已具备。",
                    }

                questions = list(profile.further_questions)[:3]
                if target:
                    questions.insert(0, f"{target} 的该问题是否在相同条件下重复出现？")
                candidates.append(
                    {
                        "id": issue_id,
                        "rank_key": (
                            0 if business_issue.get("role") == "primary" else 1,
                            -int(row.get("excess_record_count") or 0),
                            -float(lift or 0),
                            -matched,
                            title,
                        ),
                        "title": title,
                        "scope": {
                            "category": category,
                            "listing": listing,
                            "product": product,
                            "sku": sku,
                        },
                        "metrics": {
                            "matched_return_samples": matched,
                            "scoped_return_samples": scoped,
                            "return_sample_share": round(share, 1),
                            "baseline_return_sample_share": (
                                round(baseline, 1) if baseline is not None else None
                            ),
                            "gap_percentage_points": gap,
                            "lift": round(lift, 2) if lift is not None else None,
                            "recent_change_percentage_points": recent_change,
                            "trend_direction": direction,
                        },
                        "known": known[:6],
                        "fallback_evidence_explanation": (
                            "该信号在当前退货样本中形成集中分化，"
                            "但仅凭评论与样本结构不能判断真实发生率或因果。"
                        ),
                        "fallback_unknown": list(dict.fromkeys(questions))[:5],
                        "fallback_recommendation": {
                            "label": "建议验证",
                            "validation_question": (
                                f"是否需要进一步验证 {target or label} 的{label}风险？"
                            ),
                            "rationale": (
                                "当前证据足以定位问题范围，但仍需结合实物、"
                                "页面信息或业务分母验证原因与影响。"
                            ),
                            "suggested_evidence": [
                                "复核命中的原始评论",
                                "核对相同范围的商品信息与实物表现",
                                "补充订单量或销量分母",
                            ],
                        },
                        "readiness": readiness,
                        "evidence_ids": evidence_ids,
                    }
                )

        if not candidates:
            candidates.append(
                {
                    "id": "issue.scope.coverage",
                    "rank_key": (1, 0, 0, 0, "数据覆盖"),
                    "title": "当前范围尚未形成可定位的问题信号",
                    "scope": {
                        "category": category,
                        "listing": listing,
                        "product": None,
                        "sku": None,
                    },
                    "metrics": {
                        "matched_return_samples": 0,
                        "scoped_return_samples": int(
                            source.get("included_record_count") or 0
                        ),
                        "return_sample_share": 0.0,
                        "baseline_return_sample_share": None,
                        "gap_percentage_points": None,
                        "lift": None,
                        "recent_change_percentage_points": None,
                        "trend_direction": "insufficient",
                    },
                    "known": ["当前已分析范围内没有形成可定位到具体问题的稳定信号。"],
                    "fallback_evidence_explanation": "现有数据只能说明覆盖范围，不能支持具体问题判断。",
                    "fallback_unknown": list(profile.further_questions)[:5]
                    or ["是否需要补充更完整的分类与商品信息？"],
                    "fallback_recommendation": {
                        "label": "建议验证",
                        "validation_question": "是否需要先补充分类与商品证据？",
                        "rationale": "当前缺少可定位的问题信号。",
                        "suggested_evidence": ["补充已审核分类结果"],
                    },
                    "readiness": {
                        "status": "diagnostic_only",
                        "label": "仅供诊断",
                        "reason": "当前证据不足以定位具体问题。",
                    },
                    "evidence_ids": ["scope"],
                }
            )

        issues = []
        for rank, candidate in enumerate(
            sorted(candidates, key=lambda item: item["rank_key"])[:8],
            1,
        ):
            issue = {key: value for key, value in candidate.items() if key != "rank_key"}
            issue["rank"] = rank
            issues.append(issue)

        scope_name = (
            listing
            if listing
            else f"{len(listings)} 个 Listing"
            if listings
            else "当前范围"
        )
        caveats = [
            "所有占比均为退货样本内占比，不代表真实退货率。",
            "当前缺少订单量、销量、成本和批次等分母，不能据此推断因果。",
        ]
        if source.get("pending_review_record_count"):
            caveats.append("待审核记录未进入本次统计，结论可能随复核推进而变化。")
        return {
            "report_type": "problem_decision",
            "title": f"{scope_name} 退货问题判断报告",
            "issues": issues,
            "caveats": caveats,
        }

    @staticmethod
    def _build_blueprint(evidence: dict[str, Any]) -> dict[str, Any]:
        source = evidence["source"]
        analysis = evidence["analysis"]
        profile = get_insight_report_profile(
            source.get("report_profile", {}).get("key")
        )
        reasons = list(analysis.get("reasons", []))
        groups = list(analysis.get("label_group_breakdown", []))
        diagnostics = {
            str(item.get("reason_code")): item
            for item in analysis.get("diagnostics", [])
            if item.get("reason_code")
        }
        business_issues = list(analysis.get("business_issues", []))
        primary_issues = [
            issue for issue in business_issues if issue.get("role") == "primary"
        ]
        issues_by_code = {
            str(issue.get("reason_code") or ""): issue
            for issue in business_issues
            if issue.get("reason_code")
        }
        listings = list(source.get("listings", []))
        scope_name = (
            str(listings[0])
            if len(listings) == 1
            else f"{len(listings)} 个 Listing"
            if listings
            else "当前范围"
        )
        provisional = source.get("report_status") == "provisional"
        included = int(source.get("included_record_count") or 0)
        total = int(source.get("total_record_count") or included)
        pending = int(source.get("pending_review_record_count") or 0)
        coverage = float(source.get("coverage_rate") or 0)
        review_bias = analysis.get("review_bias", {})
        bias_note = str(review_bias.get("note") or "")
        product_mapping = source.get("product_mapping", {})
        mapping_trusted = product_mapping.get("status") != "needs_review"
        text_quality = source.get("text_quality", {})
        text_trusted = text_quality.get("status") != "needs_review"
        product_level_trusted = mapping_trusted
        scope_statement = (
            f"报告纳入 {included} / {total} 条记录，覆盖率 {coverage:.1f}%；"
            f"另有 {pending} 条待审核记录未进入本次统计。{bias_note}"
            if pending
            else f"报告纳入 {included} 条记录，当前范围内无待审核记录。"
        )
        generic_actionable_reasons = [
            reason
            for reason in reasons
            if "PRODUCT" in reason.get("subjects", [])
            and str(reason.get("label_group") or "") != "其他原因"
        ]
        reason_by_code = {
            str(reason.get("value") or ""): reason
            for reason in generic_actionable_reasons
        }
        actionable_reasons = [
            reason_by_code[code]
            for code in profile.preferred_reason_codes
            if code in reason_by_code
        ]
        for reason in generic_actionable_reasons:
            if reason not in actionable_reasons:
                actionable_reasons.append(reason)
            if len(actionable_reasons) >= 3:
                break
        actionable_reasons = actionable_reasons[:3]
        broad_reason = next(
            (
                reason
                for reason in reasons
                if len(reason.get("subjects", [])) > 1
                or str(reason.get("label_group") or "") == "其他原因"
            ),
            None,
        )
        primary_group = next(
            (group for group in groups if str(group.get("value")) != "其他原因"),
            groups[0] if groups else None,
        )
        group_evidence_id = "scope"
        if primary_group:
            group_evidence_id = next(
                (
                    f"group.{index}"
                    for index, group in enumerate(groups, 1)
                    if group.get("value") == primary_group.get("value")
                ),
                "scope",
            )
        reason_evidence_ids = [
            f"reason.{reason.get('value') or 'unknown'}"
            for reason in actionable_reasons
        ]
        structure_statement = (
            f"{primary_group.get('value')}覆盖 "
            f"{int(primary_group.get('record_count') or 0)} 条记录，"
            f"占已纳入样本 {float(primary_group.get('percentage') or 0):.1f}%。"
            if primary_group
            else f"当前共纳入 {included} 条可分析退货记录。"
        )
        if actionable_reasons:
            reason_text = "；".join(
                f"{reason.get('label')} {int(reason.get('record_count') or 0)} 条"
                f"（{float(reason.get('percentage') or 0):.1f}%）"
                for reason in actionable_reasons
            )
            structure_statement = (
                f"{structure_statement.rstrip('。')}；其中{reason_text}。"
            )
        business_headlines = []
        business_evidence_ids = []
        for issue in primary_issues[:3]:
            hotspot = next(iter(issue.get("hotspots", [])), None)
            if not hotspot:
                continue
            rate = float(hotspot.get("product_reason_rate") or 0)
            baseline = float(hotspot.get("overall_reason_rate") or 0)
            business_headlines.append(
                f"{issue.get('label')}在{hotspot.get('value')}为{rate:.1f}%，"
                f"比整体基线高{rate - baseline:+.1f}pp"
            )
            business_evidence_ids.append(str(issue.get("id")))
        business_statement = (
            "；".join(business_headlines) + "。"
            if business_headlines
            else structure_statement
        )

        findings = [
            {
                "id": "finding.structure",
                "kind": "structure",
                "title": (
                    f"{profile.category_name}问题已经分化到具体{profile.variant_label}"
                    if business_headlines
                    else f"{primary_group.get('value')}是当前最值得优先处理的商品问题"
                    if primary_group
                    else "当前问题结构需要先完成业务归类"
                ),
                "conclusion": business_statement,
                "evidence_ids": [
                    *business_evidence_ids,
                    group_evidence_id,
                    *reason_evidence_ids,
                    "scope",
                ],
            }
        ]

        diagnostic_ids = []
        trend_sentences = []
        hotspot_sentences = []
        hotspot_targets = []
        for reason in actionable_reasons:
            code = str(reason.get("value") or "")
            issue = issues_by_code.get(code, {})
            issue_case = next(iter(issue.get("cases", [])), None)
            if issue_case:
                case_id = str(issue_case.get("id") or "")
                trend_summary = issue_case.get("trend_summary", {})
                if (
                    trend_summary.get("status") == "available"
                    and f"{case_id}.trend" in evidence["catalog"]
                ):
                    diagnostic_ids.append(f"{case_id}.trend")
                    trend_sentences.append(
                        f"{reason.get('label')}在"
                        f"{issue_case.get('product_sku')}最近"
                        f"{trend_summary.get('window_weeks')}个完整周均值为"
                        f"{float(trend_summary.get('recent_rate') or 0):.1f}%，"
                        f"较最早同长度窗口"
                        f"{float(trend_summary.get('delta_percentage_points') or 0):+.1f}pp"
                    )
                diagnostic_ids.append(case_id)
                hotspot_targets.append(str(issue_case.get("product_sku") or ""))
                hotspot_sentences.append(
                    f"{reason.get('label')}集中在"
                    f"{issue_case.get('product_sku')}："
                    f"{int(issue_case.get('record_count') or 0)} / "
                    f"{int(issue_case.get('total_record_count') or 0)}条，"
                    f"变体内占比"
                    f"{float(issue_case.get('product_reason_rate') or 0):.1f}%，"
                    f"整体基线"
                    f"{float(issue_case.get('overall_reason_rate') or 0):.1f}%，"
                    f"为基线的{float(issue_case.get('lift') or 0):.2f}倍，"
                    f"超出按整体基线预期约"
                    f"{int(issue_case.get('excess_record_count') or 0)}条"
                )
                continue
            diagnostic = diagnostics.get(code, {})
            trend_summary = diagnostic.get("trend_summary", {})
            trend_id = f"diagnostic.{code}.trend"
            if trend_id in evidence["catalog"]:
                diagnostic_ids.append(trend_id)
                trend_sentences.append(
                    f"{reason.get('label')}最近"
                    f"{trend_summary.get('window_weeks')}个完整周均值为"
                    f"{float(trend_summary.get('recent_rate') or 0):.1f}%，"
                    f"较最早同长度窗口"
                    f"{float(trend_summary.get('delta_percentage_points') or 0):+.1f}pp"
                )
            diagnostic_dimension = (
                "variants" if diagnostic.get("variants") else "hotspots"
            )
            hotspot = next(iter(diagnostic.get(diagnostic_dimension, [])), None)
            evidence_dimension = (
                "variant" if diagnostic_dimension == "variants" else "hotspot"
            )
            hotspot_id = f"diagnostic.{code}.{evidence_dimension}.1"
            if hotspot and hotspot_id in evidence["catalog"]:
                diagnostic_ids.append(hotspot_id)
                hotspot_targets.append(str(hotspot.get("value") or ""))
                hotspot_sentences.append(
                    f"{reason.get('label')}在{hotspot.get('value')}达到"
                    f"{float(hotspot.get('product_reason_rate') or 0):.1f}%，"
                    f"为整体基线的{float(hotspot.get('lift') or 0):.2f}倍"
                )
        hotspot_targets = list(
            dict.fromkeys(target for target in hotspot_targets if target)
        )
        if actionable_reasons:
            diagnostic_conclusion = "；".join(trend_sentences + hotspot_sentences)
            if not diagnostic_conclusion:
                diagnostic_conclusion = profile.diagnostic_empty
            findings.append(
                {
                    "id": "finding.diagnostic",
                    "kind": "diagnostic",
                    "title": (
                        f"{'、'.join(hotspot_targets[:2])}是当前最需要验证的具体 SKU"
                        if hotspot_targets
                        else profile.diagnostic_title
                    ),
                    "conclusion": f"{diagnostic_conclusion}。",
                    "evidence_ids": [
                        *reason_evidence_ids,
                        *diagnostic_ids,
                    ],
                }
            )

        information_ids = []
        if broad_reason:
            broad_code = str(broad_reason.get("value") or "")
            broad_diagnostic = diagnostics.get(broad_code, {})
            semantic = broad_diagnostic.get("semantic_profile", {})
            unspecified = next(
                (
                    part
                    for part in semantic.get("parts", [])
                    if part.get("value") == "UNSPECIFIED"
                ),
                None,
            )
            top_opinion = next(iter(semantic.get("opinions", [])), None)
            broad_reason_id = f"reason.{broad_code}"
            information_ids.append(broad_reason_id)
            details = []
            if unspecified:
                details.append(
                    f"{float(unspecified.get('percentage') or 0):.1f}%未明确商品部位"
                )
            if top_opinion:
                opinion_id = f"diagnostic.{broad_code}.opinion.1"
                information_ids.append(opinion_id)
                details.append(
                    f"最高频语义为“{top_opinion.get('opinion')}”"
                    f"（{int(top_opinion.get('record_count') or 0)}条）"
                )
            information_conclusion = (
                f"{broad_reason.get('label')}涉及"
                f"{int(broad_reason.get('record_count') or 0)}条记录，"
                f"占{float(broad_reason.get('percentage') or 0):.1f}%"
            )
            if details:
                information_conclusion += "；" + "；".join(details)
            findings.append(
                {
                    "id": "finding.information",
                    "kind": "information",
                    "title": f"“{broad_reason.get('label')}”需要按意图拆解，而不是当作商品缺陷",
                    "conclusion": f"{information_conclusion}。",
                    "evidence_ids": [*information_ids, "scope"],
                }
            )

        if len(findings) < 2:
            findings.append(
                {
                    "id": "finding.coverage",
                    "kind": "information",
                    "title": "数据覆盖决定当前结论可用于什么决策",
                    "conclusion": scope_statement,
                    "evidence_ids": ["scope", "review_bias"],
                }
            )

        actions = []
        if not text_trusted:
            actions.append(
                {
                    "id": "action.text_quality",
                    "priority": "P0",
                    "target": "退货评论源数据",
                    "finding_id": "finding.structure",
                    "evidence_ids": ["text_quality", "scope"],
                    "fallback_action": "重新导出并导入未发生乱码的原始退货数据，再重新生成分类结果。",
                    "fallback_rationale": "评论文本已经出现编码异常，语义分类和原始证据均可能失真。",
                    "fallback_success_signal": "重新导入后不再检测到中英文异常混排，抽样评论与源文件一致。",
                }
            )
        if not mapping_trusted:
            actions.append(
                {
                    "id": "action.mapping",
                    "priority": "P0",
                    "target": f"Listing {product_mapping.get('listing')} 的商品主数据映射",
                    "finding_id": "finding.structure",
                    "evidence_ids": ["product_mapping", "scope"],
                    "fallback_action": "核对源 SKU、商品 SKU 与商品名称的对应关系后再下发商品级整改。",
                    "fallback_rationale": "存在未匹配或缺少名称的商品记录，当前不能确认商品级热点对应的真实对象。",
                    "fallback_success_signal": "源 SKU、商品 SKU 与商品名称形成唯一且可追溯的映射。",
                }
            )
        if actionable_reasons and product_level_trusted:
            validation_issues = [
                issue
                for issue in primary_issues
                if issue.get("cases")
            ][:3]
            validation_cases = [
                issue["cases"][0] for issue in validation_issues
            ]
            target = (
                "、".join(
                    dict.fromkeys(
                        str(case.get("product_sku") or "")
                        for case in validation_cases
                        if case.get("product_sku")
                    )
                )
                or "、".join(hotspot_targets[:2])
                or f"高频{profile.variant_label}"
            )
            case_actions = [
                str(issue.get("validation_focus") or "")
                for issue in validation_issues
                if issue.get("validation_focus")
            ]
            case_rationales = [
                (
                    f"{case.get('product_sku')}的{case.get('label')}为"
                    f"{float(case.get('product_reason_rate') or 0):.1f}%"
                    f"（整体{float(case.get('overall_reason_rate') or 0):.1f}%，"
                    f"{float(case.get('lift') or 0):.2f}倍）"
                )
                for case in validation_cases
            ]
            action_evidence_ids = list(
                dict.fromkeys(
                    [
                        *reason_evidence_ids,
                        *diagnostic_ids,
                        *(
                            str(case.get("id"))
                            for case in validation_cases
                            if case.get("id")
                        ),
                    ]
                )
            )
            actions.append(
                {
                    "id": "action.diagnostic",
                    "priority": "P0",
                    "target": target,
                    "finding_id": "finding.diagnostic",
                    "evidence_ids": action_evidence_ids,
                    "fallback_action": (
                        "；".join(case_actions)
                        if case_actions
                        else profile.diagnostic_action
                    ),
                    "fallback_rationale": (
                        "；".join(case_rationales)
                        + "。这些集中信号值得优先验证，但不能单凭评论结构推断原因。"
                        if case_rationales
                        else profile.diagnostic_rationale
                    ),
                    "fallback_success_signal": (
                        "每个目标 SKU 都形成可复核的原因结论；后续同口径评论中，"
                        "对应问题连续两个完整周期下降，且反向问题不升高。"
                        if validation_cases
                        else profile.diagnostic_success_signal
                    ),
                }
            )
        if broad_reason:
            actions.append(
                {
                    "id": "action.information",
                    "priority": "P1",
                    "target": f"{broad_reason.get('label')}相关记录",
                    "finding_id": "finding.information",
                    "evidence_ids": information_ids,
                    "fallback_action": "按评论表达的具体意图、对象和使用场景拆分宽泛原因。",
                    "fallback_rationale": "宽泛标签混合多种退货情境，不能直接转化为单一商品整改。",
                    "fallback_success_signal": "宽泛原因被稳定拆分为可解释子类，且未明确对象占比下降。",
                }
            )
        actions.append(
            {
                "id": "action.scope",
                "priority": "P2",
                "target": "待审核记录与商品销量分母",
                "finding_id": "finding.structure",
                "evidence_ids": ["scope", "review_bias"],
                "fallback_action": "持续处理待审核记录，并补充商品销量或订单量分母。",
                "fallback_rationale": "退货记录占比只能描述问题结构，不能代替真实退货率。",
                "fallback_success_signal": "待审核占比下降并形成商品级真实退货率基线。",
            }
        )
        action_order = {
            "action.mapping": 0,
            "action.diagnostic": 1,
            "action.text_quality": 2,
            "action.information": 3,
            "action.scope": 4,
        }
        actions.sort(key=lambda item: action_order.get(str(item.get("id")), 99))
        caveats = [
            "本报告只描述所选分类结果版本中的退货问题结构，不代表真实退货率。",
            "当前缺少销量、订单量、成本和批次等分母数据，不能据此推断因果。",
        ]
        if provisional:
            caveats.insert(
                0,
                f"这是临时报告：{pending} 条待审核记录未纳入，结论可能随复核推进而变化。",
            )
            if review_bias.get("status") == "concentrated":
                caveats.insert(1, bias_note)
        if product_mapping.get("status") == "needs_review":
            caveats.append(str(product_mapping.get("note")))
        if not text_trusted:
            caveats.append(str(text_quality.get("note")))

        diagnostic_summary = (
            findings[1]["conclusion"] if len(findings) > 1 else structure_statement
        )
        diagnostic_action = next(
            (
                action
                for action in actions
                if action.get("id") == "action.diagnostic"
            ),
            None,
        )
        validation_target = (
            str(diagnostic_action.get("target") or "")
            if diagnostic_action
            else "、".join(hotspot_targets[:2])
        )
        validation_statement = (
            f"优先验证{validation_target}："
            f"{diagnostic_action.get('fallback_action')}"
            if validation_target and diagnostic_action
            else diagnostic_summary
        )
        return {
            "title": f"{scope_name} 退货问题{'临时' if provisional else ''}诊断报告",
            "executive_summary": [
                {
                    "id": "summary.1",
                    "title": "最明确的问题分化",
                    "statement": business_statement,
                    "tone": "primary",
                    "evidence_ids": [
                        *business_evidence_ids,
                        group_evidence_id,
                        *reason_evidence_ids,
                    ],
                },
                {
                    "id": "summary.2",
                    "title": "优先验证对象",
                    "statement": validation_statement,
                    "tone": "neutral",
                    "evidence_ids": findings[1]["evidence_ids"],
                },
                {
                    "id": "summary.3",
                    "title": "结论可信边界",
                    "statement": scope_statement,
                    "tone": "warning" if provisional else "neutral",
                    "evidence_ids": ["scope", "review_bias"],
                },
            ],
            "findings": findings,
            "actions": actions,
            "further_questions": list(profile.further_questions),
            "caveats": caveats,
        }

    @staticmethod
    def _messages_v6(evidence: dict[str, Any]) -> list[dict[str, str]]:
        schema = {
            "issues": [
                {
                    "id": "使用 fixed_blueprint 中的 issue id",
                    "evidence_explanation": "解释已知证据说明了什么",
                    "unknown": ["尚未回答的问题"],
                    "validation_question": "下一步要验证的问题",
                    "recommendation_rationale": "为什么需要验证",
                    "suggested_evidence": ["验证需要补充的证据"],
                }
            ]
        }
        return [
            {
                "role": "system",
                "content": (
                    "你是资深电商退货分析负责人。系统已经确定问题列表、排序、"
                    "范围、指标、已知事实、证据引用和可信状态。你只负责用中文解释"
                    "这些证据、列出尚未回答的问题，并给出验证建议。不得增加或修改"
                    "任何数字，不得改写问题 id、排序、范围、指标、已知事实、证据引用"
                    "和可信状态。不得把退货样本内占比称为退货率，不得推断因果，"
                    "不得提出直接整改、任务、负责人、截止时间或商品开发方案。"
                    "只返回 JSON，不要返回 Markdown。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "output_schema": schema,
                        "fixed_blueprint": evidence["blueprint"],
                        "evidence": {
                            "source": evidence["source"],
                            "catalog": evidence["catalog"],
                            "analysis": evidence["analysis"],
                        },
                    },
                    ensure_ascii=False,
                ),
            },
        ]

    @staticmethod
    def _assemble_content_v6(
        evidence: dict[str, Any],
        payload: Any,
    ) -> InsightDecisionReportContent:
        if not isinstance(payload, dict):
            raise ValueError("模型返回的报告解释不是 JSON 对象")
        blueprint = evidence["blueprint"]
        generated_by_id = InsightReportService._items_by_id(payload.get("issues"))
        issues = []
        for item in blueprint["issues"]:
            generated = generated_by_id.get(item["id"], {})
            fallback_recommendation = item["fallback_recommendation"]
            unknown = [
                text
                for value in generated.get("unknown", [])
                if isinstance(value, str) and value.strip()
                if (text := InsightReportService._narrative_text(value, "", 300))
            ][:5]
            suggested_evidence = [
                text
                for value in generated.get("suggested_evidence", [])
                if isinstance(value, str) and value.strip()
                if (text := InsightReportService._narrative_text(value, "", 200))
            ][:5]
            issues.append(
                {
                    "id": item["id"],
                    "rank": item["rank"],
                    "title": item["title"],
                    "scope": item["scope"],
                    "metrics": item["metrics"],
                    "known": item["known"],
                    "evidence_explanation": InsightReportService._narrative_text(
                        generated.get("evidence_explanation"),
                        item["fallback_evidence_explanation"],
                        800,
                    ),
                    "unknown": unknown or item["fallback_unknown"],
                    "recommendation": {
                        "label": "建议验证",
                        "validation_question": InsightReportService._narrative_text(
                            generated.get("validation_question"),
                            fallback_recommendation["validation_question"],
                            300,
                        ),
                        "rationale": InsightReportService._narrative_text(
                            generated.get("recommendation_rationale"),
                            fallback_recommendation["rationale"],
                            500,
                        ),
                        "suggested_evidence": (
                            suggested_evidence
                            or fallback_recommendation["suggested_evidence"]
                        ),
                    },
                    "readiness": item["readiness"],
                    "evidence_ids": item["evidence_ids"],
                }
            )
        return InsightDecisionReportContent.model_validate(
            {
                "report_type": blueprint["report_type"],
                "title": blueprint["title"],
                "issues": issues,
                "caveats": blueprint["caveats"],
            }
        )

    @staticmethod
    def _messages(evidence: dict[str, Any]) -> list[dict[str, str]]:
        schema = {
            "findings": [
                {
                    "id": "使用 fixed_blueprint 中的 finding id",
                    "interpretation": "证据解释",
                    "implication": "业务含义",
                }
            ],
            "actions": [
                {
                    "id": "使用 fixed_blueprint 中的 action id",
                    "action": "行动",
                    "rationale": "行动理由",
                    "success_signal": "验证是否有效的信号",
                }
            ],
            "further_questions": ["仍需回答的问题"],
        }
        return [
            {
                "role": "system",
                "content": (
                    "你是资深电商退货分析负责人。请用中文生成面向产品和业务负责人的"
                    "退货原因洞察报告。系统已经固定事实、结论、报告结构和证据引用；你只负责"
                    "解释这些事实的业务含义，并提出可验证的行动假设。解释必须结合商品热点、"
                    "趋势、伴随原因、语义观点或原始评论中的至少一类诊断证据，不能只改写结论。"
                    "优先使用 business_issues.cases 中的具体 SKU、分子分母、整体基线、"
                    "提升倍数、趋势和已过滤评论上下文，"
                    "每项解释先说明信号集中在哪里，再说明仍需验证什么。"
                    "明确区分已验证事实、待验证解释和行动假设。"
                    "行动必须说明验证对象和判断是否有效的条件。只能使用 evidence 中已有事实，"
                    "不要引入新数字，不要把样本占比称为真实退货率，不要推断因果，也不要把"
                    "总量最大直接等同于最高行动优先级。"
                    "不得输出或修改 evidence_ids、标题、结论和优先级。只返回 JSON，不要返回 Markdown。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "output_schema": schema,
                        "fixed_blueprint": evidence["blueprint"],
                        "evidence": {
                            "source": evidence["source"],
                            "catalog": evidence["catalog"],
                            "analysis": evidence["analysis"],
                        },
                    },
                    ensure_ascii=False,
                ),
            },
        ]

    @staticmethod
    def _assemble_content(
        evidence: dict[str, Any],
        payload: Any,
    ) -> InsightReportContent:
        if not isinstance(payload, dict):
            raise ValueError("模型返回的报告解释不是 JSON 对象")
        blueprint = evidence["blueprint"]
        finding_text = InsightReportService._items_by_id(payload.get("findings"))
        action_text = InsightReportService._items_by_id(payload.get("actions"))
        findings = []
        for item in blueprint["findings"]:
            generated = finding_text.get(item["id"], {})
            findings.append(
                {
                    "id": item["id"],
                    "kind": item["kind"],
                    "title": item["title"],
                    "conclusion": item["conclusion"],
                    "interpretation": InsightReportService._text(
                        generated.get("interpretation"),
                        "该信号来自当前分类结果版本中的重复退货反馈，仍需回看原始评论确认具体情境。",
                        800,
                    ),
                    "implication": InsightReportService._text(
                        generated.get("implication"),
                        "应把该信号作为排查入口，并通过商品、批次或订单维度验证其影响范围。",
                        500,
                    ),
                    "evidence_ids": item["evidence_ids"],
                }
            )
        actions = []
        for item in blueprint["actions"]:
            generated = action_text.get(item["id"], {})
            actions.append(
                {
                    "id": item["id"],
                    "priority": item["priority"],
                    "target": item["target"],
                    "action": InsightReportService._text(
                        generated.get("action"), item["fallback_action"], 300
                    ),
                    "rationale": InsightReportService._text(
                        generated.get("rationale"), item["fallback_rationale"], 500
                    ),
                    "success_signal": InsightReportService._text(
                        generated.get("success_signal"),
                        item["fallback_success_signal"],
                        300,
                    ),
                    "evidence_ids": item["evidence_ids"],
                }
            )
        questions = [
            InsightReportService._text(value, "", 300)
            for value in payload.get("further_questions", [])
            if isinstance(value, str) and value.strip()
        ][:5]
        return InsightReportContent.model_validate(
            {
                "title": blueprint["title"],
                "executive_summary": blueprint["executive_summary"],
                "findings": findings,
                "actions": actions,
                "further_questions": questions or blueprint["further_questions"],
                "caveats": blueprint["caveats"],
            }
        )

    @staticmethod
    def _items_by_id(value: Any) -> dict[str, dict[str, Any]]:
        if isinstance(value, dict):
            return {
                str(key): item for key, item in value.items() if isinstance(item, dict)
            }
        if not isinstance(value, list):
            return {}
        return {
            str(item["id"]): item
            for item in value
            if isinstance(item, dict) and item.get("id")
        }

    @staticmethod
    def _text(value: Any, fallback: str, limit: int) -> str:
        text = str(value or "").strip() or fallback
        return text[:limit]

    @staticmethod
    def _narrative_text(value: Any, fallback: str, limit: int) -> str:
        text = str(value or "").strip()
        if not text or re.search(r"\d", text):
            return fallback
        return text[:limit]

    @staticmethod
    def _validate_evidence_refs(
        content: InsightReportContent,
        known_ids: set[str],
    ) -> None:
        references = [
            evidence_id
            for item in [
                *content.executive_summary,
                *content.findings,
                *content.actions,
            ]
            for evidence_id in item.evidence_ids
        ]
        unknown = sorted(set(references) - known_ids)
        if unknown:
            raise ValueError(f"报告引用了不存在的证据: {', '.join(unknown)}")

    @staticmethod
    def _validate_issue_evidence_refs(
        content: InsightDecisionReportContent,
        known_ids: set[str],
    ) -> None:
        references = [
            evidence_id
            for issue in content.issues
            for evidence_id in issue.evidence_ids
        ]
        unknown = sorted(set(references) - known_ids)
        if unknown:
            raise ValueError(f"报告引用了不存在的证据: {', '.join(unknown)}")

    @staticmethod
    def _decision_report_consistency(
        content: dict[str, Any],
        evidence: dict[str, Any],
    ) -> dict[str, Any]:
        consistency = InsightReportService._report_consistency(
            content,
            evidence,
            require_information_diagnostics=False,
        )
        issues = list(consistency["issues"])
        blueprint_issues = evidence.get("blueprint", {}).get("issues", [])
        expected = {
            str(item.get("id")): item for item in blueprint_issues if item.get("id")
        }
        actual = {
            str(item.get("id")): item
            for item in content.get("issues", [])
            if item.get("id")
        }
        if list(actual) != list(expected):
            issues.append("问题列表或排序与确定性证据不一致")
        for issue_id, blueprint in expected.items():
            issue = actual.get(issue_id)
            if issue is None:
                continue
            if issue.get("metrics") != blueprint.get("metrics"):
                issues.append(f"问题 {issue_id} 的指标与确定性证据不一致")
            if issue.get("evidence_ids") != blueprint.get("evidence_ids"):
                issues.append(f"问题 {issue_id} 的证据引用不一致")
        return {
            "status": "blocked" if issues else "passed",
            "issues": list(dict.fromkeys(issues)),
        }

    @staticmethod
    def _report_consistency(
        content: dict[str, Any],
        evidence: dict[str, Any],
        *,
        require_information_diagnostics: bool,
    ) -> dict[str, Any]:
        analysis = evidence.get("analysis", {})
        reasons = {
            str(item.get("value")): item
            for item in analysis.get("reasons", [])
            if item.get("value")
        }
        diagnostics: dict[str, dict[str, Any]] = {}
        issues: list[str] = []

        for diagnostic in analysis.get("diagnostics", []):
            code = str(diagnostic.get("reason_code") or "")
            if not code:
                issues.append("存在未标明原因代码的诊断数据")
                continue
            if code in diagnostics:
                issues.append(f"原因 {code} 存在重复诊断数据")
                continue
            diagnostics[code] = diagnostic
            reason = reasons.get(code)
            if reason is None:
                issues.append(f"诊断原因 {code} 不在分类结果中")
                continue

            selected_reason = diagnostic.get("selected_reason") or {}
            if str(selected_reason.get("value") or "") != code:
                issues.append(f"诊断原因 {code} 与选中原因不一致")
            if selected_reason.get("record_count") is None or int(
                selected_reason.get("record_count") or 0
            ) != int(reason.get("record_count") or 0):
                issues.append(f"诊断原因 {code} 的记录数与分类结果不一致")
            selected_percentage = selected_reason.get("percentage")
            if (
                selected_percentage is None
                or abs(
                    float(selected_percentage or 0)
                    - float(reason.get("percentage") or 0)
                )
                > 0.05
            ):
                issues.append(f"诊断原因 {code} 的占比与分类结果不一致")

        for finding in content.get("findings", []):
            if finding.get("kind") != "information":
                continue
            reason_codes = [
                str(evidence_id)[len("reason.") :]
                for evidence_id in finding.get("evidence_ids", [])
                if str(evidence_id).startswith("reason.")
            ]
            if len(reason_codes) != 1:
                issues.append("信息诊断未绑定唯一的分类原因")
                continue
            code = reason_codes[0]
            if code not in reasons:
                issues.append(f"信息诊断原因 {code} 不在分类结果中")
            if require_information_diagnostics and code not in diagnostics:
                issues.append(f"信息诊断原因 {code} 缺少语义诊断数据")

        return {
            "status": "blocked" if issues else "passed",
            "issues": list(dict.fromkeys(issues)),
        }

    @staticmethod
    def _evaluate_live_quality_v6(
        content: dict[str, Any],
        evidence: dict[str, Any],
        text_quality: dict[str, Any],
    ) -> dict[str, Any]:
        safe_content = deepcopy(content)
        safe_evidence = deepcopy(evidence)
        source = safe_evidence.setdefault("source", {})
        analysis = safe_evidence.setdefault("analysis", {})
        catalog = safe_evidence.setdefault("catalog", {})
        product_mapping = source.get("product_mapping", {})
        review_bias = analysis.get("review_bias", {})
        pending_count = int(source.get("pending_review_record_count") or 0)
        quality_issues = []

        source["text_quality"] = text_quality
        analysis["text_quality"] = text_quality
        catalog["text_quality"] = {
            "label": "评论文本质量",
            "value": str(text_quality.get("note") or "未发现明显编码异常"),
            "data": text_quality,
        }
        if text_quality.get("status") == "needs_review":
            quality_issues.append(
                {
                    "code": "text_quality",
                    "label": "评论文本质量未通过",
                    "detail": str(text_quality.get("note") or "评论文本需要核对。"),
                    "evidence_ids": ["text_quality", "scope"],
                }
            )
            analysis["diagnostics"] = [
                InsightReportService._filter_diagnostic_text(item)
                for item in analysis.get("diagnostics", [])
            ]
            analysis["issue_cases"] = [
                InsightReportService._filter_issue_case_text(item)
                for item in analysis.get("issue_cases", [])
            ]
            analysis["business_issues"] = [
                InsightReportService._filter_business_issue_text(item)
                for item in analysis.get("business_issues", [])
            ]
            analysis["samples"] = []
            for evidence_id, item in catalog.items():
                if not any(
                    marker in evidence_id for marker in (".sample.", ".opinion.")
                ):
                    continue
                data = item.get("data", {})
                if InsightReportService._has_text_anomaly(
                    data.get("opinion"),
                    data.get("evidence"),
                    data.get("comment"),
                    data.get("reason"),
                ):
                    item["value"] = "文本质量未通过，原始文本证据暂不可用"
                    item["data"] = {}
            for issue in safe_content.get("issues", []):
                issue["known"] = [
                    value
                    for value in issue.get("known", [])
                    if not str(value).startswith("高频反馈为")
                ]
                issue["evidence_explanation"] = (
                    "评论文本质量未通过，当前仅保留结构化指标用于定位，"
                    "不能据此判断原因。"
                )

        if product_mapping.get("status") == "needs_review":
            quality_issues.append(
                {
                    "code": "product_mapping",
                    "label": "商品主数据需核对",
                    "detail": str(
                        product_mapping.get("note") or "商品主数据映射需要核对。"
                    ),
                    "evidence_ids": ["product_mapping", "scope"],
                }
            )
        if pending_count:
            quality_issues.append(
                {
                    "code": "pending_review",
                    "label": "存在待审核记录",
                    "detail": str(
                        review_bias.get("note")
                        or f"{pending_count} 条待审核记录未进入本次统计。"
                    ),
                    "evidence_ids": ["scope", "review_bias"],
                }
            )

        consistency = InsightReportService._decision_report_consistency(
            safe_content,
            safe_evidence,
        )
        if consistency["status"] == "blocked":
            quality_issues.insert(
                0,
                {
                    "code": "report_consistency",
                    "label": "报告内部数据不一致",
                    "detail": "；".join(consistency["issues"][:3]),
                    "evidence_ids": [],
                },
            )
            readiness = {
                "status": "unusable",
                "label": "不可使用",
                "reason": "报告内部数据不一致，请重新生成报告。",
            }
            gate_status = "blocked"
        elif quality_issues:
            readiness = {
                "status": "diagnostic_only",
                "label": "仅供诊断",
                "reason": "数据质量或审核范围仍有限，只能用于定位问题。",
            }
            gate_status = "warning"
        else:
            readiness = {
                "status": "verification_ready",
                "label": "可进入验证",
                "reason": "数据质量和报告一致性校验均已通过。",
            }
            gate_status = "passed"

        if readiness["status"] != "verification_ready":
            for issue in safe_content.get("issues", []):
                issue["readiness"] = readiness
        source["quality_issue_codes"] = [item["code"] for item in quality_issues]
        source["report_status"] = "provisional" if quality_issues else "final"
        quality_gate = DecisionReportQualityGate.model_validate(
            {
                "status": gate_status,
                "issues": quality_issues,
                "text_quality": text_quality,
                "product_mapping": product_mapping,
                "consistency": consistency,
                "decision_readiness": readiness,
            }
        ).model_dump()
        return {
            "content": safe_content,
            "evidence": safe_evidence,
            "quality_gate": quality_gate,
        }

    @staticmethod
    def _evaluate_live_quality(
        content: dict[str, Any],
        evidence: dict[str, Any],
        text_quality: dict[str, Any],
    ) -> dict[str, Any]:
        safe_content = deepcopy(content)
        safe_evidence = deepcopy(evidence)
        source = safe_evidence.setdefault("source", {})
        analysis = safe_evidence.setdefault("analysis", {})
        catalog = safe_evidence.setdefault("catalog", {})
        consistency = InsightReportService._report_consistency(
            safe_content,
            safe_evidence,
            require_information_diagnostics=True,
        )
        product_mapping = source.get("product_mapping", {})
        text_trusted = text_quality.get("status") != "needs_review"
        mapping_trusted = product_mapping.get("status") != "needs_review"
        product_level_trusted = mapping_trusted
        pending_count = int(source.get("pending_review_record_count") or 0)
        review_bias = analysis.get("review_bias", {})
        source_issues = []
        if not text_trusted:
            source_issues.append(
                {
                    "code": "text_quality",
                    "label": "评论文本质量未通过",
                    "detail": str(
                        text_quality.get("note") or "评论文本质量需要核对。"
                    ),
                    "evidence_ids": ["text_quality", "scope"],
                }
            )
        if not mapping_trusted:
            source_issues.append(
                {
                    "code": "product_mapping",
                    "label": "商品主数据需核对",
                    "detail": str(
                        product_mapping.get("note") or "商品主数据映射需要核对。"
                    ),
                    "evidence_ids": ["product_mapping", "scope"],
                }
            )
        if pending_count:
            source_issues.append(
                {
                    "code": "pending_review",
                    "label": "存在待审核记录",
                    "detail": str(
                        review_bias.get("note")
                        or f"{pending_count} 条待审核记录未进入本次统计。"
                    ),
                    "evidence_ids": ["scope", "review_bias"],
                }
            )
        product_names = [
            str(item.get("value") or "")
            for item in analysis.get("product_reason_matrix", [])
            if item.get("value")
        ]

        source["text_quality"] = text_quality
        source["quality_issue_codes"] = [item["code"] for item in source_issues]
        source["report_status"] = "provisional" if source_issues else "final"
        analysis["text_quality"] = text_quality
        catalog["text_quality"] = {
            "label": "评论文本质量",
            "value": str(text_quality.get("note") or "未发现明显编码异常"),
            "data": text_quality,
        }

        if not product_level_trusted:
            analysis["product_reason_matrix"] = []
            analysis["business_issues"] = []
            analysis["issue_cases"] = []
            analysis["diagnostics"] = [
                {
                    **diagnostic,
                    "hotspots": [],
                    "variants": [],
                    "samples": [
                        {
                            **sample,
                            "product_name": None,
                            "product_sku": None,
                        }
                        for sample in diagnostic.get("samples", [])
                    ],
                }
                for diagnostic in analysis.get("diagnostics", [])
            ]
            analysis["samples"] = [
                {
                    **sample,
                    "product_name": None,
                    "product_sku": None,
                }
                for sample in analysis.get("samples", [])
            ]
        if not text_trusted:
            analysis["diagnostics"] = [
                InsightReportService._filter_diagnostic_text(diagnostic)
                for diagnostic in analysis.get("diagnostics", [])
            ]
            analysis["issue_cases"] = [
                InsightReportService._filter_issue_case_text(case)
                for case in analysis.get("issue_cases", [])
            ]
            analysis["business_issues"] = [
                InsightReportService._filter_business_issue_text(issue)
                for issue in analysis.get("business_issues", [])
            ]
            analysis["samples"] = [
                sample
                for sample in analysis.get("samples", [])
                if not InsightReportService._has_text_anomaly(
                    sample.get("comment"),
                    sample.get("reason"),
                )
            ]

        blocked_catalog_markers = []
        if not product_level_trusted:
            blocked_catalog_markers.extend(
                [
                    ".hotspot.",
                    ".variant.",
                    "business_issue.",
                    "issue_case.",
                ]
            )
        for evidence_id in list(catalog):
            if any(marker in evidence_id for marker in blocked_catalog_markers):
                catalog.pop(evidence_id, None)
                continue
            if not text_trusted and any(
                marker in evidence_id for marker in (".sample.", ".opinion.")
            ):
                data = catalog[evidence_id].get("data", {})
                if InsightReportService._has_text_anomaly(
                    data.get("opinion"),
                    data.get("evidence"),
                    data.get("comment"),
                    data.get("reason"),
                ):
                    catalog.pop(evidence_id, None)
            elif not text_trusted and evidence_id.startswith("business_issue."):
                catalog[evidence_id]["data"] = (
                    InsightReportService._filter_business_issue_text(
                        catalog[evidence_id].get("data", {})
                    )
                )

        if not product_level_trusted:
            safe_content["findings"] = [
                finding
                for finding in safe_content.get("findings", [])
                if finding.get("kind") != "diagnostic"
            ]

        summaries = []
        for summary in safe_content.get("executive_summary", []):
            summary_text = f"{summary.get('title', '')} {summary.get('statement', '')}"
            references = summary.get("evidence_ids", [])
            if not product_level_trusted and (
                any(name in summary_text for name in product_names)
                or any(
                    marker in item
                    for item in references
                    for marker in (
                        ".hotspot.",
                        ".variant.",
                        "business_issue.",
                        "issue_case.",
                    )
                )
            ):
                continue
            if not text_trusted and any(
                marker in item
                for item in references
                for marker in (".sample.", ".opinion.")
            ):
                continue
            summaries.append(summary)

        quality_issues = list(source_issues)
        if consistency["status"] == "blocked":
            quality_issues.insert(
                0,
                {
                    "code": "report_consistency",
                    "label": "报告内部数据不一致",
                    "detail": "；".join(consistency["issues"][:3]),
                    "evidence_ids": [],
                },
            )
            summaries = []
        gate_summary = None
        if quality_issues:
            issue_labels = "、".join(item["label"] for item in quality_issues)
            evidence_ids = list(
                dict.fromkeys(
                    evidence_id
                    for item in quality_issues
                    for evidence_id in item["evidence_ids"]
                )
            )
            gate_summary = {
                "id": "summary.quality_gate",
                "title": (
                    "当前报告不可使用"
                    if consistency["status"] == "blocked"
                    else "当前结论仅供诊断"
                ),
                "statement": (
                    f"{issue_labels}。"
                    + (
                        "请重新生成报告后再使用。"
                        if consistency["status"] == "blocked"
                        else "问题修复前，不应直接下发商品整改。"
                    )
                ),
                "tone": "warning",
                "evidence_ids": evidence_ids or ["scope"],
            }
        summary_candidates = [gate_summary, *summaries] if gate_summary else summaries
        unique_summaries = []
        seen_summaries = set()
        for summary in summary_candidates:
            key = (summary.get("title"), summary.get("statement"))
            if key in seen_summaries:
                continue
            seen_summaries.add(key)
            unique_summaries.append(summary)
        safe_content["executive_summary"] = unique_summaries[:4]

        actions = [
            action
            for action in safe_content.get("actions", [])
            if action.get("id") != "action.diagnostic" or product_level_trusted
        ]
        gate_actions = []
        if not text_trusted:
            gate_actions.append(
                {
                    "id": "action.text_quality",
                    "priority": "P0",
                    "target": "退货评论源数据",
                    "action": (
                        "重新导出并导入未发生乱码的原始退货数据，"
                        "再重新生成分类结果和 AI 洞察报告。"
                    ),
                    "rationale": (
                        "评论文本检测到中英文异常混排，语义分类和原始证据可能失真。"
                    ),
                    "success_signal": (
                        "重新导入后不再检测到异常混排，抽样评论与源文件一致。"
                    ),
                    "evidence_ids": ["text_quality", "scope"],
                }
            )
        if not mapping_trusted:
            actions = [
                action for action in actions if action.get("id") != "action.mapping"
            ]
            gate_actions.append(
                {
                    "id": "action.mapping",
                    "priority": "P0",
                    "target": "商品主数据映射",
                    "action": (
                        "核对源 SKU、商品 SKU 与商品名称的对应关系后，"
                        "再下发商品级整改。"
                    ),
                    "rationale": (
                        "存在未匹配或缺少名称的商品记录，"
                        "当前不能确认商品级热点对应的真实对象。"
                    ),
                    "success_signal": (
                        "源 SKU、商品 SKU 与商品名称形成唯一且可追溯的映射。"
                    ),
                    "evidence_ids": ["product_mapping", "scope"],
                }
            )
        actions = [
            action
            for action in actions
            if action.get("id") not in {item["id"] for item in gate_actions}
        ]
        action_candidates = [] if consistency["status"] == "blocked" else [
            *gate_actions,
            *actions,
        ]
        unique_actions = []
        seen_action_ids = set()
        for action in action_candidates:
            action_id = action.get("id")
            if action_id in seen_action_ids:
                continue
            seen_action_ids.add(action_id)
            unique_actions.append(action)
        action_order = {
            "action.mapping": 0,
            "action.diagnostic": 1,
            "action.text_quality": 2,
            "action.information": 3,
            "action.scope": 4,
        }
        unique_actions.sort(
            key=lambda action: action_order.get(action.get("id"), 99)
        )
        safe_content["actions"] = unique_actions[:6]

        warnings = []
        if not text_trusted:
            warnings.append(
                "评论文本质量未通过门禁：在重新导入干净源数据前，"
                "本报告只可用于定位数据问题，不可下发商品整改。"
            )
        if not mapping_trusted:
            warnings.append(str(product_mapping.get("note") or "商品主数据需核对。"))
        if pending_count:
            warnings.append(str(review_bias.get("note") or source_issues[-1]["detail"]))
        caveats = [*warnings, *safe_content.get("caveats", [])]
        safe_content["caveats"] = list(dict.fromkeys(caveats))
        if consistency["status"] == "blocked":
            decision_readiness = {
                "status": "unusable",
                "label": "不可使用",
                "reason": "报告内部数据不一致，请重新生成报告。",
            }
        elif source_issues:
            decision_readiness = {
                "status": "diagnostic_only",
                "label": "仅供诊断",
                "reason": (
                    f"当前存在{'、'.join(item['label'] for item in source_issues)}，"
                    "不应直接下发商品整改。"
                ),
            }
        else:
            decision_readiness = {
                "status": "actionable",
                "label": "可行动",
                "reason": "数据质量与报告一致性校验均已通过。",
            }

        if consistency["status"] == "blocked":
            gate_status = "blocked"
        elif source_issues:
            gate_status = "warning"
        else:
            gate_status = "passed"
        quality_gate = ReportQualityGate.model_validate(
            {
                "status": gate_status,
                "issues": quality_issues,
                "text_quality": text_quality,
                "product_mapping": product_mapping,
                "consistency": consistency,
                "decision_readiness": decision_readiness,
            }
        ).model_dump()
        return {
            "content": safe_content,
            "evidence": safe_evidence,
            "quality_gate": quality_gate,
        }

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
        report_ids: list[str],
    ) -> dict[str, list[dict[str, Any]]]:
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
        decisions: list[dict[str, Any]] | None = None,
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
