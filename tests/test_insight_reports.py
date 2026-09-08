from __future__ import annotations

import json
from copy import deepcopy
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_classification_result_pool import _publish, _seed_result_context

from return_semantics.model_client import JsonModelCallResult, Sub2APISettings
from web_backend.common import json_text
from web_backend.dashboard_service import DashboardService
from web_backend.insight_report_profiles import resolve_insight_report_profile
from web_backend.insight_report_service import (
    PROMPT_VERSION,
    V5_PROMPT_VERSION,
    InsightReportService,
)
from web_backend.operations_service import WorkbenchService
from web_backend.routers.insight_reports import create_insight_report_router


def _report_payload() -> dict:
    return {
        "findings": [
            {
                "id": "finding.structure",
                "interpretation": "同一评论组在三条记录中重复出现。",
                "implication": "应先检查尺码表和实物测量。",
                "evidence_ids": [f"model.evidence.{index}" for index in range(20)],
            },
            {
                "id": "finding.diagnostic",
                "interpretation": "证据只包含退货记录，没有销量分母。",
                "implication": "整改后需要结合订单数据验证效果。",
            },
        ],
        "actions": [
            {
                "id": "action.diagnostic",
                "action": "复核尺码表与实物测量。",
                "rationale": "先验证最集中的可改善问题。",
                "success_signal": "后续偏小反馈占比下降。",
                "evidence_ids": [f"model.action.{index}" for index in range(20)],
            },
            {
                "id": "action.scope",
                "action": "补充销量分母后监控真实退货率。",
                "rationale": "当前样本不能回答发生率问题。",
                "success_signal": "形成商品级退货率基线。",
            },
        ],
        "further_questions": ["问题是否集中在特定尺码？"],
    }


def _service_context(tmp_path, client_payload=None, client_error=None):
    context = _seed_result_context(tmp_path)
    version = _publish(context)
    dashboard_service = DashboardService(context.database)
    plan = dashboard_service.preflight([str(version["version_id"])], {})
    dashboard = dashboard_service.create(
        name="退货问题看板",
        description="测试报告生成",
        result_version_ids=[str(version["version_id"])],
        filters={},
        plan_hash=plan["plan_hash"],
        reason="测试报告",
        actor_id="user-1",
    )
    now = "2026-08-15T00:00:00+00:00"
    with context.database.transaction(immediate=True) as connection:
        connection.execute(
            """
            INSERT INTO api_models(
                id, connection_id, model_key, display_name,
                supported_efforts_json, active, validation_status,
                created_by, created_at, updated_by, updated_at
            ) VALUES ('model-1', 'connection-1', 'model-primary', '主模型',
                      ?, 1, 'validated', 'user-1', ?, 'user-1', ?)
            """,
            (json_text(["low", "medium", "high"]), now, now),
        )

    settings = Sub2APISettings(
        api_key="test-key",
        model="model-primary",
        base_url="https://example.test/v1",
        retries=0,
    )
    captured = {}

    class FakeClient:
        def __init__(self, runtime_settings):
            captured["settings"] = runtime_settings

        def generate_json(self, messages, model, reasoning_effort):
            captured["messages"] = messages
            captured["model"] = model
            captured["reasoning_effort"] = reasoning_effort
            if client_error:
                raise RuntimeError(client_error)
            payload = client_payload
            if payload is None:
                request = json.loads(messages[1]["content"])
                payload = {
                    "issues": [
                        {
                            "id": issue["id"],
                            "evidence_explanation": (
                                "当前退货样本形成了可追溯的问题信号，"
                                "但仍不能证明真实发生率或因果。"
                            ),
                            "unknown": ["该问题是否在相同条件下重复出现？"],
                            "validation_question": "是否需要进一步验证该问题？",
                            "recommendation_rationale": (
                                "需要结合商品信息与业务分母核对现有解释。"
                            ),
                            "suggested_evidence": ["复核原始评论与商品信息"],
                        }
                        for issue in request["fixed_blueprint"]["issues"]
                    ]
                }
            return JsonModelCallResult(
                payload=payload,
                model_name="model-primary-20260815",
                usage={"input_tokens": 100, "output_tokens": 50},
                metrics={"latency_ms": 300},
            )

    config_service = SimpleNamespace(build_model_settings=lambda _id: settings)
    service = InsightReportService(
        context.database,
        dashboard_service,
        config_service,
        client_factory=FakeClient,
    )
    return context, dashboard, service, captured


def _complete_report(dashboard, service):
    queued = service.create_for_dashboard(
        str(dashboard["id"]),
        str(dashboard["version"]["version_id"]),
        model_id="model-1",
        reasoning_effort="high",
        actor_id="user-1",
    )
    report_id = service.claim_next()
    assert report_id == queued["id"]
    service.run(str(report_id))
    return service.get(str(report_id))


def test_report_generation_is_versioned_and_evidence_backed(tmp_path) -> None:
    _context, dashboard, service, captured = _service_context(tmp_path)
    dashboard_id = str(dashboard["id"])
    dashboard_version_id = str(dashboard["version"]["version_id"])

    queued = service.create_for_dashboard(
        dashboard_id,
        dashboard_version_id,
        model_id="model-1",
        reasoning_effort="high",
        actor_id="user-1",
    )
    assert queued["status"] == "queued"
    assert queued["version_no"] is None
    assert queued["attempt_no"] == 1
    assert queued["kind"] == "generation_job"

    report_id = service.claim_next()
    assert report_id == queued["id"]
    service.run(str(report_id))

    completed = service.get(str(report_id))
    assert completed["status"] == "completed"
    assert completed["version_no"] == 1
    assert completed["kind"] == "report"
    assert completed["prompt_version"] == PROMPT_VERSION
    assert completed["content"]["title"] == "L1 退货问题判断报告"
    assert completed["content"]["report_type"] == "problem_decision"
    issue = completed["content"]["issues"][0]
    assert issue["id"] == "issue.reason.FIT_TOO_SMALL_U1"
    assert issue["rank"] == 1
    assert issue["metrics"]["matched_return_samples"] == 3
    assert issue["metrics"]["return_sample_share"] == 100.0
    assert "退货样本内占比" in issue["known"][0]
    assert issue["evidence_explanation"].startswith("当前退货样本")
    assert "actions" not in completed["content"]
    assert completed["evidence"]["catalog"]["reason.FIT_TOO_SMALL_U1"]["value"]
    blueprint_evidence_ids = completed["evidence"]["blueprint"]["issues"][0][
        "evidence_ids"
    ]
    assert "reason.FIT_TOO_SMALL_U1" in blueprint_evidence_ids
    assert "scope" in blueprint_evidence_ids
    assert (
        issue["evidence_ids"]
        == completed["evidence"]["blueprint"]["issues"][0]["evidence_ids"]
    )
    assert (
        completed["evidence"]["analysis"]["diagnostics"][0]["reason_code"]
        == "FIT_TOO_SMALL_U1"
    )
    assert completed["usage"] == {"input_tokens": 100, "output_tokens": 50}
    assert completed["resolved_model"] == "model-primary-20260815"
    assert captured["model"] == "model-primary"
    assert captured["reasoning_effort"] == "high"
    assert captured["settings"].reasoning_effort == "high"
    assert "不得增加或修改任何数字" in captured["messages"][0]["content"]
    assert "商品开发方案" in captured["messages"][0]["content"]
    assert len(service.list(dashboard_id, dashboard_version_id)) == 1
    workbench = WorkbenchService(_context.database).summary(limit=20)
    output = next(
        item for item in workbench["recent_outputs"] if item["type"] == "insight_report"
    )
    assert output["version_no"] == 1
    assert output["target"]["report_id"] == report_id


def test_v6_keeps_numbers_and_ranking_deterministic(tmp_path) -> None:
    payload = {
        "issues": [
            {
                "id": "issue.reason.FIT_TOO_SMALL",
                "rank": 99,
                "metrics": {"return_sample_share": 12.3},
                "evidence_explanation": "样本占比达到 99%，应立即整改。",
                "unknown": ["是否有 99 个批次都出现问题？"],
                "validation_question": "是否在 7 天内整改？",
                "recommendation_rationale": "该问题增长 80%。",
                "suggested_evidence": ["抽查 50 个样本"],
            }
        ]
    }
    _context, dashboard, service, _captured = _service_context(
        tmp_path,
        client_payload=payload,
    )

    first = _complete_report(dashboard, service)
    second = _complete_report(dashboard, service)
    first_issue = first["content"]["issues"][0]

    assert first_issue["rank"] == 1
    assert first_issue["metrics"]["return_sample_share"] == 100.0
    assert "99" not in first_issue["evidence_explanation"]
    assert all("99" not in item for item in first_issue["unknown"])
    assert "7" not in first_issue["recommendation"]["validation_question"]
    assert "80" not in first_issue["recommendation"]["rationale"]
    assert all(
        "50" not in item
        for item in first_issue["recommendation"]["suggested_evidence"]
    )
    assert first["evidence_hash"] == second["evidence_hash"]


def test_issue_decision_put_is_idempotent_and_audited(tmp_path) -> None:
    context, dashboard, service, _captured = _service_context(tmp_path)
    report = _complete_report(dashboard, service)
    issue_id = report["content"]["issues"][0]["id"]
    app = FastAPI()
    app.include_router(
        create_insight_report_router(service, lambda: {"id": "user-1"})
    )
    client = TestClient(app)

    first = client.put(
        f"/api/ai-insight-reports/{report['id']}/issues/{issue_id}/decision",
        json={"status": "verify"},
    )
    second = client.put(
        f"/api/ai-insight-reports/{report['id']}/issues/{issue_id}/decision",
        json={"status": "verify"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["status"] == "verify"
    refreshed = service.get(report["id"])
    assert refreshed["decisions"][0]["issue_id"] == issue_id
    assert refreshed["decisions"][0]["status"] == "verify"
    with context.database.connect() as connection:
        audit_count = connection.execute(
            """
            SELECT COUNT(*) FROM audit_logs
            WHERE entity_type = 'ai_insight_issue_decision'
              AND entity_id = ?
            """,
            (f"{report['id']}:{issue_id}",),
        ).fetchone()[0]
    assert audit_count == 1


def test_v5_report_is_serialized_without_v6_conversion(tmp_path) -> None:
    context, dashboard, service, _captured = _service_context(tmp_path)
    report = _complete_report(dashboard, service)
    legacy_content = {
        "title": "历史 V5 报告",
        "executive_summary": [],
        "findings": [{"id": "finding.structure", "kind": "structure"}],
        "actions": [{"id": "action.scope", "priority": "P2"}],
        "further_questions": [],
        "caveats": ["历史报告保持原结构。"],
    }
    legacy_evidence = {
        "source": {
            "product_mapping": {"status": "consistent"},
            "pending_review_record_count": 0,
            "report_status": "final",
        },
        "analysis": {"reasons": [], "diagnostics": [], "review_bias": {}},
        "catalog": {"scope": {}},
    }
    with context.database.transaction(immediate=True) as connection:
        connection.execute(
            """
            UPDATE ai_insight_reports
            SET prompt_version = ?, content_json = ?, evidence_json = ?
            WHERE id = ?
            """,
            (
                V5_PROMPT_VERSION,
                json_text(legacy_content),
                json_text(legacy_evidence),
                report["id"],
            ),
        )

    legacy = service.get(report["id"])

    assert legacy["prompt_version"] == V5_PROMPT_VERSION
    assert legacy["content"]["title"] == "历史 V5 报告"
    assert legacy["content"]["actions"][0]["id"] == "action.scope"
    assert "issues" not in legacy["content"]
    assert legacy["quality_gate"]["decision_readiness"]["status"] == "actionable"


def test_report_profile_supports_same_category_multi_listing_and_generic_fallback() -> None:
    same_category = resolve_insight_report_profile(
        [{"agent_key": "gloves"}, {"agent_key": "gloves"}]
    )
    mixed_category = resolve_insight_report_profile(
        [{"agent_key": "gloves"}, {"agent_key": "footwear"}]
    )
    unknown_category = resolve_insight_report_profile(
        [{"agent_key": "unknown"}]
    )

    assert same_category.key == "gloves"
    assert same_category.snapshot()["category_name"] == "手套"
    assert mixed_category.key == "generic"
    assert unknown_category.key == "generic"


def test_v6_blueprint_keeps_same_category_multi_listing_scope_generic() -> None:
    evidence = InsightReportService._build_evidence(
        {
            "summary": {
                "record_count": 20,
                "total_record_count": 20,
                "pending_review_record_count": 0,
                "coverage_rate": 100.0,
            },
            "filter_options": {
                "listings": ["RGA803", "RGA804"],
                "product_names": [],
            },
            "sources": [
                {"agent_key": "gloves", "listing": "RGA803"},
                {"agent_key": "gloves", "listing": "RGA804"},
            ],
            "review_bias": {"status": "not_applicable"},
            "text_quality": {
                "status": "passed",
                "checked_record_count": 20,
                "anomaly_record_count": 0,
            },
        },
        prompt_version=PROMPT_VERSION,
    )

    issue = evidence["blueprint"]["issues"][0]
    assert evidence["source"]["report_profile"]["key"] == "gloves"
    assert evidence["source"]["report_profile"]["category_name"] == "手套"
    assert evidence["blueprint"]["title"] == "2 个 Listing 退货问题判断报告"
    assert issue["scope"]["category"] == "手套"
    assert issue["scope"]["listing"] is None


def test_v6_blueprint_generic_fallback_has_only_common_scope_fields() -> None:
    evidence = InsightReportService._build_evidence(
        {
            "summary": {
                "record_count": 20,
                "total_record_count": 20,
                "pending_review_record_count": 0,
                "coverage_rate": 100.0,
            },
            "filter_options": {
                "listings": ["RGA803", "SHOE001"],
                "product_names": [],
            },
            "sources": [
                {"agent_key": "gloves", "listing": "RGA803"},
                {"agent_key": "footwear", "listing": "SHOE001"},
            ],
            "review_bias": {"status": "not_applicable"},
            "text_quality": {
                "status": "passed",
                "checked_record_count": 20,
                "anomaly_record_count": 0,
            },
        },
        prompt_version=PROMPT_VERSION,
    )

    issue_scope = evidence["blueprint"]["issues"][0]["scope"]
    assert evidence["source"]["report_profile"]["key"] == "generic"
    assert evidence["source"]["report_profile"]["category_name"] == "商品"
    assert evidence["blueprint"]["title"] == "2 个 Listing 退货问题判断报告"
    assert issue_scope == {
        "category": None,
        "listing": None,
        "product": None,
        "sku": None,
    }


def test_failed_report_can_be_requeued(tmp_path) -> None:
    _context, dashboard, service, _captured = _service_context(
        tmp_path,
        client_error="模型暂时不可用",
    )
    report = service.create_for_dashboard(
        str(dashboard["id"]),
        str(dashboard["version"]["version_id"]),
        model_id="model-1",
        reasoning_effort="medium",
        actor_id="user-1",
    )
    report_id = service.claim_next()
    service.run(str(report_id))
    assert service.get(str(report_id))["status"] == "failed"
    assert "不会占用报告版本号" in service.get(str(report_id))["error"]
    assert service.get(str(report_id))["version_no"] is None
    with _context.database.connect() as connection:
        technical_error = connection.execute(
            "SELECT technical_error FROM ai_insight_reports WHERE id = ?",
            (report_id,),
        ).fetchone()["technical_error"]
    assert "模型暂时不可用" in technical_error
    workbench = WorkbenchService(_context.database).summary(limit=20)
    failed_action = next(
        item for item in workbench["actions"] if item["type"] == "report_failed"
    )
    assert failed_action["target"]["report_id"] == report_id
    assert "不会占用报告版本号" in failed_action["reason"]

    retried = service.retry(str(report["id"]), "user-1")
    assert retried["status"] == "queued"
    assert retried["id"] != report["id"]
    assert retried["attempt_no"] == 2
    assert retried["version_no"] is None
    assert service.get(str(report["id"]))["status"] == "failed"
    actions = WorkbenchService(_context.database).summary(limit=20)["actions"]
    assert all(item["object_id"] != report["id"] for item in actions)
    assert any(item["object_id"] == retried["id"] for item in actions)


def test_result_entry_creates_dashboard_and_report(tmp_path) -> None:
    context, _dashboard, service, _captured = _service_context(tmp_path)
    with context.database.connect() as connection:
        version_id = str(
            connection.execute(
                """
                SELECT id FROM classification_result_versions
                ORDER BY created_at LIMIT 1
                """
            ).fetchone()["id"]
        )
    plan = service.dashboard_service.preflight([version_id], {})

    created = service.create_from_results(
        result_version_ids=[version_id],
        filters={},
        plan_hash=plan["plan_hash"],
        model_id="model-1",
        reasoning_effort="high",
        actor_id="user-1",
    )

    assert created["dashboard"]["name"] == "AI 洞察 · L1"
    assert created["report"]["status"] == "queued"
    assert created["report"]["dashboard_id"] == created["dashboard"]["id"]


def test_diagnostic_reasons_follow_report_blueprint() -> None:
    analysis = {
        "reasons": [
            {
                "value": "OTHER_NO_LONGER_NEEDED",
                "label_group": "其他原因",
                "subjects": ["BUYER", "ORDER"],
            },
            {
                "value": "FIT_TOO_SMALL",
                "label_group": "尺码",
                "subjects": ["PRODUCT"],
            },
            {
                "value": "FIT_TOO_LARGE",
                "label_group": "尺码",
                "subjects": ["PRODUCT"],
            },
            {
                "value": "COLOR_MISMATCH",
                "label_group": "外观",
                "subjects": ["PRODUCT"],
            },
        ]
    }

    assert InsightReportService._diagnostic_reason_codes(analysis) == [
        "FIT_TOO_SMALL",
        "FIT_TOO_LARGE",
        "OTHER_NO_LONGER_NEEDED",
    ]


def test_glove_profile_prioritizes_category_problems() -> None:
    analysis = {
        "sources": [{"agent_key": "gloves"}],
        "reasons": [
            {
                "value": "OTHER_EXPECTATION_MISMATCH",
                "label_group": "其他原因",
                "subjects": ["PRODUCT", "BUYER"],
            },
            {
                "value": "GLOVE_WARMTH",
                "label_group": "功能",
                "subjects": ["PRODUCT"],
            },
            {
                "value": "GLOVE_SIZE_LARGE",
                "label_group": "尺码",
                "subjects": ["PRODUCT"],
            },
            {
                "value": "GLOVE_SIZE_SMALL",
                "label_group": "尺码",
                "subjects": ["PRODUCT"],
            },
        ],
    }

    assert InsightReportService._diagnostic_reason_codes(analysis) == [
        "GLOVE_SIZE_SMALL",
        "GLOVE_SIZE_LARGE",
        "GLOVE_WARMTH",
        "OTHER_EXPECTATION_MISMATCH",
    ]


def test_glove_evidence_uses_variant_diagnostic_blueprint() -> None:
    analysis = {
        "summary": {
            "record_count": 100,
            "total_record_count": 100,
            "pending_review_record_count": 0,
            "coverage_rate": 100.0,
        },
        "label_group_breakdown": [
            {"value": "功能", "record_count": 40, "percentage": 40.0}
        ],
        "reasons": [
            {
                "value": "GLOVE_WARMTH",
                "label": "保暖表现",
                "label_group": "功能",
                "record_count": 40,
                "percentage": 40.0,
                "subjects": ["PRODUCT"],
            }
        ],
        "subject_breakdown": [],
        "product_reason_matrix": [
            {
                "value": "RGA803 Winter Gloves",
                "total_record_count": 100,
                "reason_rates": {},
            }
        ],
        "diagnostics": [
            {
                "reason_code": "GLOVE_WARMTH",
                "selected_reason": {
                    "value": "GLOVE_WARMTH",
                    "label": "保暖表现",
                    "record_count": 40,
                    "percentage": 40.0,
                },
                "trend_summary": {"status": "insufficient"},
                "hotspots": [],
                "variants": [
                    {
                        "value": "RGA803-S",
                        "record_count": 24,
                        "total_record_count": 40,
                        "product_reason_rate": 60.0,
                        "overall_reason_rate": 40.0,
                        "lift": 1.5,
                        "reliable": True,
                        "excess_record_count": 8,
                    }
                ],
                "samples": [
                    {
                        "comment": "It doesn�� stay warm",
                        "product_name": "RGA803 Winter Gloves",
                        "product_sku": "RGA803-S",
                    }
                ],
                "semantic_profile": {
                    "opinions": [{"opinion": "not warm", "record_count": 12}]
                },
            }
        ],
        "issue_cases": [
            {
                "id": "issue_case.GLOVE_WARMTH.test",
                "reason_code": "GLOVE_WARMTH",
                "label": "保暖表现",
                "product_name": "RGA803 Winter Gloves",
                "product_sku": "RGA803-S",
                "record_count": 24,
                "total_record_count": 40,
                "issue_rate": 60.0,
                "overall_rate": 40.0,
                "lift": 1.5,
                "trend": [{"period_start": "2026-01-05", "record_count": 8}],
                "semantic_profile": {
                    "opinions": [{"opinion": "not warm", "record_count": 12}]
                },
                "samples": [
                    {
                        "comment": "It doesn�� stay warm",
                        "product_name": "RGA803 Winter Gloves",
                        "product_sku": "RGA803-S",
                    }
                ],
            }
        ],
        "review_bias": {"status": "not_applicable", "note": "无需评估"},
        "text_quality": {"status": "passed", "note": "文本质量通过"},
        "filter_options": {
            "listings": ["RGA803"],
            "product_names": ["RGA803 Winter Gloves"],
        },
        "sources": [
            {
                "agent_key": "gloves",
                "taxonomy_version": "gloves-taxonomy-v2",
            }
        ],
    }

    evidence = InsightReportService._build_evidence(analysis)

    assert evidence["source"]["report_profile"]["key"] == "gloves"
    assert "diagnostic.GLOVE_WARMTH.variant.1" in evidence["catalog"]
    assert "issue_case.GLOVE_WARMTH.test" in evidence["catalog"]
    assert evidence["analysis"]["issue_cases"][0]["product_sku"] == "RGA803-S"
    blueprint = evidence["blueprint"]
    assert "RGA803-S" in blueprint["findings"][1]["title"]
    assert "24 / 40条" in blueprint["findings"][1]["conclusion"]
    assert "整体基线40.0%" in blueprint["findings"][1]["conclusion"]
    assert blueprint["actions"][0]["target"] == "RGA803-S"
    assert "not warm" in blueprint["actions"][0]["fallback_action"]
    assert any("温度" in item for item in blueprint["further_questions"])

    analysis["text_quality"] = {
        "status": "needs_review",
        "note": "发现部分评论编码异常",
    }
    evidence = InsightReportService._build_evidence(analysis)

    diagnostic = evidence["analysis"]["diagnostics"][0]
    issue_case = evidence["analysis"]["issue_cases"][0]
    assert diagnostic["variants"]
    assert diagnostic["samples"] == []
    assert issue_case["samples"] == []
    assert issue_case["semantic_profile"]["opinions"]
    assert diagnostic["semantic_profile"]["opinions"] == [
        {"opinion": "not warm", "record_count": 12}
    ]
    issue = evidence["analysis"]["business_issues"][0]
    assert issue["reason_code"] == "GLOVE_WARMTH"
    assert issue["hotspot_dimension"] == "variant"
    assert issue["contexts"]["samples"] == []
    assert issue["contexts"]["opinions"]
    action_ids = [item["id"] for item in evidence["blueprint"]["actions"]]
    assert action_ids[:2] == ["action.diagnostic", "action.text_quality"]
    content = deepcopy(evidence["blueprint"])
    evaluated = InsightReportService._evaluate_live_quality(
        content,
        evidence,
        analysis["text_quality"],
    )
    evaluated_action_ids = [
        item["id"] for item in evaluated["content"]["actions"]
    ]
    assert "action.diagnostic" in evaluated_action_ids
    assert evaluated["evidence"]["analysis"]["diagnostics"][0]["variants"]
    assert (
        evaluated["quality_gate"]["decision_readiness"]["status"]
        == "diagnostic_only"
    )


def test_consistency_blocks_information_without_diagnostic() -> None:
    content = {
        "findings": [
            {
                "kind": "information",
                "evidence_ids": ["reason.OTHER_NO_LONGER_NEEDED", "scope"],
            }
        ]
    }
    evidence = {
        "analysis": {
            "reasons": [
                {
                    "value": "OTHER_NO_LONGER_NEEDED",
                    "record_count": 60,
                    "percentage": 24.2,
                }
            ],
            "diagnostics": [],
        }
    }

    consistency = InsightReportService._report_consistency(
        content,
        evidence,
        require_information_diagnostics=True,
    )

    assert consistency["status"] == "blocked"
    assert consistency["issues"] == [
        "信息诊断原因 OTHER_NO_LONGER_NEEDED 缺少语义诊断数据"
    ]


def test_untrusted_quality_signals_preserve_all_report_caveats() -> None:
    analysis = {
        "summary": {
            "record_count": 100,
            "total_record_count": 120,
            "pending_review_record_count": 20,
            "coverage_rate": 83.3,
            "product_unmatched_count": 8,
        },
        "label_group_breakdown": [
            {"value": "尺码", "record_count": 60, "percentage": 60.0}
        ],
        "reasons": [
            {
                "value": "FIT_TOO_SMALL",
                "label": "尺码偏小",
                "label_group": "尺码",
                "record_count": 60,
                "percentage": 60.0,
                "subjects": ["PRODUCT"],
            }
        ],
        "subject_breakdown": [],
        "product_reason_matrix": [
            {
                "value": "SK001-701 条纹黑",
                "record_count": 50,
                "total_record_count": 70,
                "product_reason_rate": 71.4,
                "overall_reason_rate": 60.0,
                "lift": 1.19,
                "reliable": True,
            }
        ],
        "diagnostics": [
            {
                "reason_code": "FIT_TOO_SMALL",
                "selected_reason": {
                    "value": "FIT_TOO_SMALL",
                    "label": "尺码偏小",
                    "record_count": 60,
                    "percentage": 60.0,
                },
                "trend_summary": {"status": "insufficient"},
                "hotspots": [
                    {
                        "value": "SK001-701 条纹黑",
                        "record_count": 50,
                        "total_record_count": 70,
                        "product_reason_rate": 71.4,
                        "overall_reason_rate": 60.0,
                        "lift": 1.19,
                    }
                ],
                "samples": [
                    {
                        "comment": "Too small",
                        "product_name": "SK001-701 条纹黑",
                        "product_sku": "SK001-701 Black 40",
                    }
                ],
                "semantic_profile": {
                    "opinions": [{"opinion": "Didn稚 fit", "record_count": 12}]
                },
            }
        ],
        "review_bias": {"status": "not_detected", "note": "未发现集中偏差"},
        "text_quality": {
            "status": "needs_review",
            "anomaly_record_count": 12,
            "anomaly_rate": 10.0,
            "examples": ["Didn稚 fit"],
            "note": "发现疑似编码异常评论。",
        },
        "filter_options": {
            "listings": ["SK002"],
            "product_names": ["SK001-701 条纹黑"],
        },
    }

    evidence = InsightReportService._build_evidence(analysis)

    assert evidence["source"]["product_mapping"]["status"] == "needs_review"
    assert evidence["source"]["report_status"] == "provisional"
    assert evidence["source"]["quality_issue_codes"] == [
        "pending_review",
        "text_quality",
        "product_mapping",
    ]
    assert evidence["analysis"]["product_reason_matrix"] == []
    assert evidence["analysis"]["diagnostics"][0]["hotspots"] == []
    assert evidence["analysis"]["diagnostics"][0]["samples"] == [
        {
            "comment": "Too small",
            "product_name": None,
            "product_sku": None,
        }
    ]
    assert evidence["analysis"]["diagnostics"][0]["semantic_profile"]["opinions"] == []
    issue = evidence["analysis"]["business_issues"][0]
    assert issue["reason_code"] == "FIT_TOO_SMALL"
    assert issue["hotspots"] == []
    assert issue["contexts"]["samples"][0]["product_name"] is None
    actions = evidence["blueprint"]["actions"]
    assert actions[0]["id"] == "action.mapping"
    assert actions[0]["priority"] == "P0"
    assert actions[1]["id"] == "action.text_quality"
    assert actions[1]["priority"] == "P0"
    assert all(item["id"] != "action.diagnostic" for item in actions)

    analysis["review_bias"] = {
        "status": "concentrated",
        "note": "待审核记录集中在部分商品。",
    }
    evidence = InsightReportService._build_evidence(analysis)
    content = InsightReportService._assemble_content(evidence, _report_payload())

    assert len(evidence["blueprint"]["caveats"]) == 6
    assert content.caveats == evidence["blueprint"]["caveats"]

    decision_evidence = InsightReportService._build_evidence(
        analysis,
        prompt_version=PROMPT_VERSION,
    )
    decision_content = InsightReportService._assemble_content_v6(
        decision_evidence,
        {},
    )
    evaluated = InsightReportService._evaluate_live_quality_v6(
        decision_content.model_dump(),
        decision_evidence,
        analysis["text_quality"],
    )

    assert evaluated["quality_gate"]["status"] == "warning"
    assert evaluated["quality_gate"]["decision_readiness"]["status"] == (
        "diagnostic_only"
    )
    assert [
        item["code"] for item in evaluated["quality_gate"]["issues"]
    ] == ["text_quality", "product_mapping", "pending_review"]
    assert all(
        issue["scope"]["product"] is None and issue["scope"]["sku"] is None
        for issue in evaluated["content"]["issues"]
    )
    assert "actions" not in evaluated["content"]


def test_live_quality_gate_sanitizes_existing_report() -> None:
    content = {
        "executive_summary": [
            {
                "title": "关键诊断",
                "statement": "偏小在 SK001-701 达到 38.2%。",
                "evidence_ids": ["diagnostic.FIT_TOO_SMALL.hotspot.1"],
            }
        ],
        "findings": [
            {"id": "finding.structure", "kind": "structure"},
            {"id": "finding.diagnostic", "kind": "diagnostic"},
        ],
        "actions": [
            {"id": "action.diagnostic", "priority": "P0"},
            {"id": "action.information", "priority": "P1"},
        ],
        "caveats": [],
    }
    evidence = {
        "source": {
            "report_status": "final",
            "product_mapping": {
                "status": "needs_review",
                "note": "商品名称与 Listing 不一致。",
            },
        },
        "analysis": {
            "reasons": [
                {
                    "value": "FIT_TOO_SMALL",
                    "label": "尺码偏小",
                    "record_count": 60,
                    "percentage": 60.0,
                }
            ],
            "product_reason_matrix": [{"value": "SK001-701"}],
            "diagnostics": [
                {
                    "reason_code": "FIT_TOO_SMALL",
                    "selected_reason": {
                        "value": "FIT_TOO_SMALL",
                        "label": "尺码偏小",
                        "record_count": 60,
                        "percentage": 60.0,
                    },
                    "hotspots": [{"value": "SK001-701"}],
                    "samples": [
                        {
                            "comment": "Didn稚 fit",
                            "product_name": "SK001-701",
                            "product_sku": "SK001-701-40",
                        }
                    ],
                    "semantic_profile": {
                        "opinions": [{"opinion": "Didn稚 fit", "record_count": 12}]
                    },
                }
            ],
            "issue_cases": [
                {
                    "id": "issue_case.FIT_TOO_SMALL.test",
                    "product_name": "SK001-701",
                    "product_sku": "SK001-701-40",
                    "samples": [{"comment": "Didn稚 fit"}],
                    "semantic_profile": {
                        "opinions": [{"opinion": "Didn稚 fit"}]
                    },
                }
            ],
            "samples": [{"comment": "Didn稚 fit"}],
        },
        "catalog": {
            "scope": {},
            "product_mapping": {},
            "issue_case.FIT_TOO_SMALL.test": {},
        },
    }
    text_quality = {
        "status": "needs_review",
        "anomaly_record_count": 12,
        "note": "发现疑似编码异常评论。",
    }

    original_content = deepcopy(content)
    original_evidence = deepcopy(evidence)
    evaluated = InsightReportService._evaluate_live_quality(
        content,
        evidence,
        text_quality,
    )
    safe_content = evaluated["content"]
    safe_evidence = evaluated["evidence"]
    gate = evaluated["quality_gate"]

    assert content == original_content
    assert evidence == original_evidence
    assert gate["status"] == "warning"
    assert [item["code"] for item in gate["issues"]] == [
        "text_quality",
        "product_mapping",
    ]
    assert gate["consistency"]["status"] == "passed"
    assert gate["decision_readiness"]["status"] == "diagnostic_only"
    assert safe_evidence["source"]["report_status"] == "provisional"
    assert safe_evidence["analysis"]["product_reason_matrix"] == []
    assert safe_evidence["analysis"]["issue_cases"] == []
    assert "issue_case.FIT_TOO_SMALL.test" not in safe_evidence["catalog"]
    diagnostic = safe_evidence["analysis"]["diagnostics"][0]
    assert diagnostic["hotspots"] == []
    assert diagnostic["samples"] == []
    assert diagnostic["semantic_profile"]["opinions"] == []
    assert all(item["kind"] != "diagnostic" for item in safe_content["findings"])
    assert safe_content["executive_summary"][0]["title"] == "当前结论仅供诊断"
    assert len(safe_content["executive_summary"]) <= 4
    assert all(
        "SK001-701" not in item["statement"]
        for item in safe_content["executive_summary"]
    )
    action_ids = [item["id"] for item in safe_content["actions"]]
    assert action_ids[:2] == ["action.mapping", "action.text_quality"]
    assert "action.diagnostic" not in action_ids
    assert safe_content["caveats"][0].startswith("评论文本质量未通过门禁")


def test_live_quality_gate_keeps_summary_within_contract() -> None:
    content = {
        "executive_summary": [
            {
                "title": f"摘要 {index}",
                "statement": f"结论 {index}",
                "evidence_ids": ["scope"],
            }
            for index in range(4)
        ],
        "findings": [],
        "actions": [],
        "caveats": [],
    }
    evidence = {
        "source": {
            "report_status": "provisional",
            "pending_review_record_count": 8,
            "product_mapping": {"status": "passed"},
        },
        "analysis": {
            "review_bias": {
                "status": "not_detected",
                "note": "暂未发现待审核记录在商品维度明显集中。",
            }
        },
        "catalog": {"scope": {}, "review_bias": {}},
    }

    evaluated = InsightReportService._evaluate_live_quality(
        content,
        evidence,
        {"status": "passed", "note": "未发现明显的评论编码异常。"},
    )

    gate = evaluated["quality_gate"]
    summaries = evaluated["content"]["executive_summary"]
    assert gate["status"] == "warning"
    assert gate["decision_readiness"]["status"] == "diagnostic_only"
    assert [item["code"] for item in gate["issues"]] == ["pending_review"]
    assert len(summaries) == 4
    assert summaries[0]["title"] == "当前结论仅供诊断"
