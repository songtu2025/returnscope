from __future__ import annotations

import builtins
from typing import Any, Callable

from return_semantics.model_client import Sub2APIClient
from web_backend import (
    insight_report_content,
    insight_report_contracts,
    insight_report_decision_blueprint,
    insight_report_diagnostics,
    insight_report_legacy_blueprint,
    insight_report_quality,
    insight_report_quality_v6,
)
from web_backend.common import json_value
from web_backend.config_service import ConfigService
from web_backend.dashboard_service import DashboardService
from web_backend.database import Database
from web_backend.insight_reports.creation import _InsightReportCreation
from web_backend.insight_reports.execution import _InsightReportExecution
from web_backend.insight_reports.lifecycle_contracts import (
    InsightReportConflict as InsightReportConflict,
)
from web_backend.insight_reports.lifecycle_contracts import (
    InsightReportNotFound as InsightReportNotFound,
)
from web_backend.insight_reports.lifecycle_contracts import (
    _ReportCreationTarget,
)

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


class InsightReportService(_InsightReportCreation, _InsightReportExecution):
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
            target=_ReportCreationTarget(
                dashboard_id=str(dashboard["id"]),
                dashboard_version_id=str(dashboard["version"]["version_id"]),
            ),
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
            target=_ReportCreationTarget(
                dashboard_id=dashboard_id,
                dashboard_version_id=dashboard_version_id,
            ),
            model=model,
            reasoning_effort=reasoning_effort,
            actor_id=actor_id,
        )

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

    _trend_summary = staticmethod(insight_report_diagnostics._trend_summary)

    _rank_hotspots = staticmethod(insight_report_diagnostics._rank_hotspots)

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

    _build_decision_blueprint = staticmethod(
        insight_report_decision_blueprint._build_decision_blueprint
    )

    _build_blueprint = staticmethod(insight_report_legacy_blueprint._build_blueprint)

    _items_by_id = staticmethod(insight_report_content._items_by_id)

    _text = staticmethod(insight_report_content._text)

    _narrative_text = staticmethod(insight_report_content._narrative_text)

    _evaluate_live_quality_v6 = staticmethod(
        insight_report_quality_v6._evaluate_live_quality_v6
    )

    _evaluate_live_quality = staticmethod(insight_report_quality._evaluate_live_quality)
