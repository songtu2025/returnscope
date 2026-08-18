from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field

from return_semantics.model_client import Sub2APIClient
from web_backend.common import json_text, json_value, new_id
from web_backend.config_service import ConfigService
from web_backend.dashboard_service import DashboardService
from web_backend.database import Database
from web_backend.model_catalog import validate_effort
from web_backend.security import utc_now

PROMPT_VERSION = "ai-return-insight-v3"
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
    caveats: list[str] = Field(min_length=1, max_length=5)


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
        text_quality = None
        if any(row["status"] == "completed" for row in rows):
            text_quality = self.dashboard_service.text_quality(
                dashboard_id,
                dashboard_version_id,
            )
        return [self._serialize(dict(row), text_quality=text_quality) for row in rows]

    def get(self, report_id: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                f"""
                {self._select_sql()}
                WHERE report.id = ?
                """,
                (report_id,),
            ).fetchone()
        if row is None:
            raise InsightReportNotFound("AI 洞察报告不存在")
        report = dict(row)
        text_quality = None
        if report["status"] == "completed":
            text_quality = self.dashboard_service.text_quality(
                str(report["dashboard_id"]),
                str(report["dashboard_version_id"]),
            )
        return self._serialize(report, text_quality=text_quality)

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
            analysis["diagnostics"] = [
                self._compact_diagnostic(
                    self.dashboard_service.insights(
                        str(report["dashboard_id"]),
                        str(report["dashboard_version_id"]),
                        problem=reason_code,
                    )
                )
                for reason_code in self._diagnostic_reason_codes(analysis)
            ]
            evidence = self._build_evidence(analysis)
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
            result = client.generate_json(
                self._messages(evidence),
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
        candidates = [*actionable[:2]]
        if broad_reason:
            candidates.append(broad_reason)
        if not candidates and reasons:
            candidates.append(reasons[0])

        for reason in candidates:
            code = str(reason.get("value") or "")
            if code and code not in selected:
                selected.append(code)
        return [code for code in selected if code][:3]

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
    def _product_mapping_check(
        listings: list[str],
        products: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if len(listings) != 1:
            return {"status": "not_applicable", "examples": []}

        listing = str(listings[0]).strip()
        mismatched = []
        for product in products:
            name = str(product.get("value") or "").strip()
            if "-" not in name:
                continue
            name_prefix = name.split("-", 1)[0]
            if name_prefix.casefold() != listing.casefold():
                mismatched.append(product)
        if not mismatched:
            return {"status": "consistent", "listing": listing, "examples": []}

        examples = [str(item.get("value") or "") for item in mismatched[:3]]
        record_count = sum(
            int(item.get("total_record_count") or 0) for item in mismatched
        )
        return {
            "status": "needs_review",
            "listing": listing,
            "mismatched_product_count": len(mismatched),
            "mismatched_record_count": record_count,
            "examples": examples,
            "note": (
                f"重点商品中有 {len(mismatched)} 个商品主数据名称前缀与 "
                f"Listing {listing} 不一致，商品级行动前需核对主数据映射。"
            ),
        }

    @staticmethod
    def _build_evidence(analysis: dict[str, Any]) -> dict[str, Any]:
        summary = analysis.get("summary", {})
        groups = list(analysis.get("label_group_breakdown", []))[:12]
        reasons = list(analysis.get("reasons", []))[:15]
        subjects = list(analysis.get("subject_breakdown", []))[:10]
        products = list(analysis.get("product_reason_matrix", []))[:8]
        diagnostics = list(analysis.get("diagnostics", []))[:3]
        review_bias = analysis.get("review_bias", {})
        text_quality = analysis.get("text_quality", {})
        listings = list(analysis.get("filter_options", {}).get("listings", []))
        product_names = list(
            analysis.get("filter_options", {}).get("product_names", [])
        )
        product_mapping = InsightReportService._product_mapping_check(
            listings,
            products,
        )
        mapping_trusted = product_mapping.get("status") != "needs_review"
        text_trusted = text_quality.get("status") != "needs_review"
        product_level_trusted = mapping_trusted and text_trusted
        safe_products = products if product_level_trusted else []
        safe_diagnostics = diagnostics
        if not product_level_trusted:
            safe_diagnostics = [
                {
                    **diagnostic,
                    "hotspots": [],
                    "semantic_profile": {
                        **diagnostic.get("semantic_profile", {}),
                        "opinions": (
                            diagnostic.get("semantic_profile", {}).get(
                                "opinions",
                                [],
                            )
                            if text_trusted
                            else []
                        ),
                    },
                    "samples": (
                        []
                        if not text_trusted
                        else [
                            {
                                **sample,
                                "product_name": None,
                                "product_sku": None,
                            }
                            for sample in diagnostic.get("samples", [])
                        ]
                    ),
                }
                for diagnostic in diagnostics
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
        total_record_count = int(
            summary.get("total_record_count") or summary.get("record_count") or 0
        )
        pending_review_count = int(summary.get("pending_review_record_count") or 0)
        coverage_rate = float(
            summary.get("coverage_rate")
            if summary.get("coverage_rate") is not None
            else (100 if total_record_count else 0)
        )
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
                "report_status": (
                    "provisional"
                    if pending_review_count > 0 or not text_trusted
                    else "final"
                ),
            },
            "catalog": catalog,
            "analysis": {
                "summary": summary,
                "label_group_breakdown": groups,
                "reasons": reasons,
                "subject_breakdown": subjects,
                "product_reason_matrix": safe_products,
                "diagnostics": safe_diagnostics,
                "review_bias": review_bias,
                "text_quality": text_quality,
                "samples": samples,
            },
        }
        evidence["blueprint"] = InsightReportService._build_blueprint(evidence)
        return evidence

    @staticmethod
    def _build_blueprint(evidence: dict[str, Any]) -> dict[str, Any]:
        source = evidence["source"]
        analysis = evidence["analysis"]
        reasons = list(analysis.get("reasons", []))
        groups = list(analysis.get("label_group_breakdown", []))
        diagnostics = {
            str(item.get("reason_code")): item
            for item in analysis.get("diagnostics", [])
            if item.get("reason_code")
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
        product_level_trusted = mapping_trusted and text_trusted
        scope_statement = (
            f"报告纳入 {included} / {total} 条记录，覆盖率 {coverage:.1f}%；"
            f"另有 {pending} 条待审核记录未进入本次统计。{bias_note}"
            if pending
            else f"报告纳入 {included} 条记录，当前范围内无待审核记录。"
        )
        actionable_reasons = [
            reason
            for reason in reasons
            if "PRODUCT" in reason.get("subjects", [])
            and str(reason.get("label_group") or "") != "其他原因"
        ][:2]
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

        findings = [
            {
                "id": "finding.structure",
                "kind": "structure",
                "title": (
                    f"{primary_group.get('value')}是当前最值得优先处理的商品问题"
                    if primary_group
                    else "当前问题结构需要先完成业务归类"
                ),
                "conclusion": structure_statement,
                "evidence_ids": [group_evidence_id, *reason_evidence_ids, "scope"],
            }
        ]

        diagnostic_ids = []
        trend_sentences = []
        hotspot_sentences = []
        hotspot_targets = []
        for reason in actionable_reasons:
            code = str(reason.get("value") or "")
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
            hotspot = next(iter(diagnostic.get("hotspots", [])), None)
            hotspot_id = f"diagnostic.{code}.hotspot.1"
            if hotspot and hotspot_id in evidence["catalog"]:
                diagnostic_ids.append(hotspot_id)
                hotspot_targets.append(str(hotspot.get("value") or ""))
                hotspot_sentences.append(
                    f"{reason.get('label')}在{hotspot.get('value')}达到"
                    f"{float(hotspot.get('product_reason_rate') or 0):.1f}%，"
                    f"为整体基线的{float(hotspot.get('lift') or 0):.2f}倍"
                )
        if actionable_reasons:
            diagnostic_conclusion = "；".join(trend_sentences + hotspot_sentences)
            if not diagnostic_conclusion:
                diagnostic_conclusion = "高频商品问题需要按商品和时间维度继续拆解。"
            findings.append(
                {
                    "id": "finding.diagnostic",
                    "kind": "diagnostic",
                    "title": (
                        "偏小与偏大信号正在分化，不能统一调整尺码"
                        if len(actionable_reasons) > 1
                        else f"{actionable_reasons[0].get('label')}集中在部分商品"
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
                    "fallback_rationale": "商品名称前缀与 Listing 不一致，当前不能确认商品级热点对应的真实对象。",
                    "fallback_success_signal": "源 SKU、商品 SKU 与商品名称形成唯一且可追溯的映射。",
                }
            )
        if actionable_reasons and product_level_trusted:
            target = "、".join(hotspot_targets[:2]) or "高频商品与对应尺码"
            actions.append(
                {
                    "id": "action.diagnostic",
                    "priority": "P0",
                    "target": target,
                    "finding_id": "finding.diagnostic",
                    "evidence_ids": [*reason_evidence_ids, *diagnostic_ids],
                    "fallback_action": "分别核对偏小与偏大热点商品的尺码表、实物测量和页面说明。",
                    "fallback_rationale": "两个尺码方向同时存在且商品热点不同，统一调整会掩盖商品差异。",
                    "fallback_success_signal": "目标商品的对应尺码问题占比连续两个完整周期下降，且反向问题不升高。",
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
                    "fallback_action": "按改变主意、找到替代品、下单错误等具体意图拆分宽泛原因。",
                    "fallback_rationale": "宽泛标签混合多种非商品情境，不能直接转化为商品整改。",
                    "fallback_success_signal": "宽泛原因被稳定拆分为可解释子类，且未知或未明确对象占比下降。",
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
        return {
            "title": f"{scope_name} 退货问题{'临时' if provisional else ''}诊断报告",
            "executive_summary": [
                {
                    "id": "summary.1",
                    "title": "首要可行动问题",
                    "statement": structure_statement,
                    "tone": "primary",
                    "evidence_ids": [group_evidence_id, *reason_evidence_ids],
                },
                {
                    "id": "summary.2",
                    "title": "关键诊断",
                    "statement": diagnostic_summary,
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
            "further_questions": [
                "偏小与偏大热点商品是否来自不同尺码段、颜色或生产批次？",
                "商品主数据映射核对后，当前商品热点是否仍然成立？",
                "补充销量分母后，问题优先级是否仍然成立？",
            ],
            "caveats": caveats,
        }

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
    def _apply_live_quality_gate(
        content: dict[str, Any],
        evidence: dict[str, Any],
        text_quality: dict[str, Any],
    ) -> dict[str, Any]:
        source = evidence.setdefault("source", {})
        analysis = evidence.setdefault("analysis", {})
        catalog = evidence.setdefault("catalog", {})
        consistency = InsightReportService._report_consistency(
            content,
            evidence,
            require_information_diagnostics=True,
        )
        product_mapping = source.get("product_mapping", {})
        text_trusted = text_quality.get("status") != "needs_review"
        mapping_trusted = product_mapping.get("status") != "needs_review"
        product_level_trusted = text_trusted and mapping_trusted
        product_names = [
            str(item.get("value") or "")
            for item in analysis.get("product_reason_matrix", [])
            if item.get("value")
        ]

        source["text_quality"] = text_quality
        if not text_trusted:
            source["report_status"] = "provisional"
        analysis["text_quality"] = text_quality
        catalog["text_quality"] = {
            "label": "评论文本质量",
            "value": str(text_quality.get("note") or "未发现明显编码异常"),
            "data": text_quality,
        }

        if not product_level_trusted:
            analysis["product_reason_matrix"] = []
            analysis["diagnostics"] = [
                {
                    **diagnostic,
                    "hotspots": [],
                    "semantic_profile": {
                        **diagnostic.get("semantic_profile", {}),
                        "opinions": (
                            diagnostic.get("semantic_profile", {}).get(
                                "opinions",
                                [],
                            )
                            if text_trusted
                            else []
                        ),
                    },
                    "samples": (
                        []
                        if not text_trusted
                        else [
                            {
                                **sample,
                                "product_name": None,
                                "product_sku": None,
                            }
                            for sample in diagnostic.get("samples", [])
                        ]
                    ),
                }
                for diagnostic in analysis.get("diagnostics", [])
            ]
            analysis["samples"] = (
                []
                if not text_trusted
                else analysis.get(
                    "samples",
                    [],
                )
            )

        blocked_catalog_markers = []
        if not product_level_trusted:
            blocked_catalog_markers.append(".hotspot.")
        if not text_trusted:
            blocked_catalog_markers.extend([".sample.", ".opinion."])
        for evidence_id in list(catalog):
            if any(marker in evidence_id for marker in blocked_catalog_markers):
                catalog.pop(evidence_id, None)

        if not mapping_trusted:
            content["findings"] = [
                finding
                for finding in content.get("findings", [])
                if finding.get("kind") != "diagnostic"
            ]

        summaries = []
        for summary in content.get("executive_summary", []):
            summary_text = f"{summary.get('title', '')} {summary.get('statement', '')}"
            references = summary.get("evidence_ids", [])
            if not product_level_trusted and (
                any(name in summary_text for name in product_names)
                or any(".hotspot." in item for item in references)
            ):
                continue
            if not text_trusted and any(
                marker in item
                for item in references
                for marker in (".sample.", ".opinion.")
            ):
                continue
            summaries.append(summary)

        gate_summaries = []
        if not text_trusted:
            gate_summaries.append(
                {
                    "title": "评论文本质量未通过",
                    "statement": (
                        "当前源数据存在疑似编码异常；修复前，本报告只用于定位数据问题。"
                    ),
                    "tone": "warning",
                    "evidence_ids": ["text_quality", "scope"],
                }
            )
        if not mapping_trusted:
            gate_summaries.append(
                {
                    "title": "商品归因暂不可用",
                    "statement": str(
                        product_mapping.get("note") or "商品主数据映射需要核对。"
                    ),
                    "tone": "warning",
                    "evidence_ids": ["product_mapping", "scope"],
                }
            )
        content["executive_summary"] = [*gate_summaries, *summaries]

        actions = [
            action
            for action in content.get("actions", [])
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
                        "商品名称与 Listing 不一致，"
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
        content["actions"] = [*gate_actions, *actions]

        warnings = []
        if not text_trusted:
            warnings.append(
                "评论文本质量未通过门禁：在重新导入干净源数据前，"
                "本报告只可用于定位数据问题，不可下发商品整改。"
            )
        if not mapping_trusted:
            warnings.append(str(product_mapping.get("note") or "商品主数据需核对。"))
        caveats = list(content.get("caveats", []))
        content["caveats"] = [
            *warnings,
            *[item for item in caveats if item not in warnings],
        ]
        if consistency["status"] == "blocked":
            decision_readiness = {
                "status": "unusable",
                "label": "不可使用",
                "reason": "报告内部数据不一致，请重新生成报告。",
            }
        elif not product_level_trusted or source.get("report_status") == "provisional":
            decision_readiness = {
                "status": "diagnostic_only",
                "label": "仅供诊断",
                "reason": "数据仍有待审核或质量问题，不应直接下发整改。",
            }
        else:
            decision_readiness = {
                "status": "actionable",
                "label": "可行动",
                "reason": "数据质量与报告一致性校验均已通过。",
            }

        if consistency["status"] == "blocked" or not product_level_trusted:
            gate_status = "blocked"
        elif source.get("report_status") == "provisional":
            gate_status = "warning"
        else:
            gate_status = "passed"
        return {
            "status": gate_status,
            "text_quality": text_quality,
            "product_mapping": product_mapping,
            "consistency": consistency,
            "decision_readiness": decision_readiness,
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
    def _serialize(
        value: dict[str, Any],
        *,
        text_quality: dict[str, Any] | None = None,
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
        if value["content"] and value["evidence"] and text_quality is not None:
            value["quality_gate"] = InsightReportService._apply_live_quality_gate(
                value["content"],
                value["evidence"],
                text_quality,
            )
        value.pop("technical_error", None)
        return value
