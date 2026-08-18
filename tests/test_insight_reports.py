from __future__ import annotations

from types import SimpleNamespace

from test_classification_result_pool import _publish, _seed_result_context

from return_semantics.model_client import JsonModelCallResult, Sub2APISettings
from web_backend.common import json_text
from web_backend.dashboard_service import DashboardService
from web_backend.insight_report_service import InsightReportService
from web_backend.operations_service import WorkbenchService


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
            return JsonModelCallResult(
                payload=client_payload or _report_payload(),
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
    assert completed["content"]["title"] == "L1 退货问题诊断报告"
    assert completed["content"]["findings"][0]["id"] == "finding.structure"
    assert completed["content"]["findings"][0]["kind"] == "structure"
    assert completed["content"]["findings"][0]["interpretation"].startswith(
        "同一评论组"
    )
    assert completed["evidence"]["catalog"]["reason.FIT_TOO_SMALL"]["value"]
    assert completed["evidence"]["blueprint"]["findings"][0]["evidence_ids"] == [
        "group.1",
        "reason.FIT_TOO_SMALL",
        "scope",
    ]
    assert completed["content"]["findings"][0]["evidence_ids"] == completed[
        "evidence"
    ]["blueprint"]["findings"][0]["evidence_ids"]
    assert completed["content"]["actions"][0]["evidence_ids"] == completed[
        "evidence"
    ]["blueprint"]["actions"][0]["evidence_ids"]
    assert completed["evidence"]["analysis"]["diagnostics"][0][
        "reason_code"
    ] == "FIT_TOO_SMALL"
    assert completed["usage"] == {"input_tokens": 100, "output_tokens": 50}
    assert completed["resolved_model"] == "model-primary-20260815"
    assert captured["model"] == "model-primary"
    assert captured["reasoning_effort"] == "high"
    assert captured["settings"].reasoning_effort == "high"
    assert "不能只改写结论" in captured["messages"][0]["content"]
    assert len(service.list(dashboard_id, dashboard_version_id)) == 1
    workbench = WorkbenchService(_context.database).summary(limit=20)
    output = next(
        item for item in workbench["recent_outputs"]
        if item["type"] == "insight_report"
    )
    assert output["version_no"] == 1
    assert output["target"]["report_id"] == report_id


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
        item for item in workbench["actions"]
        if item["type"] == "report_failed"
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


def test_untrusted_product_mapping_blocks_product_level_actions() -> None:
    analysis = {
        "summary": {
            "record_count": 100,
            "total_record_count": 120,
            "pending_review_record_count": 20,
            "coverage_rate": 83.3,
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
                "selected_reason": {"label": "尺码偏小"},
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
    assert evidence["analysis"]["product_reason_matrix"] == []
    assert evidence["analysis"]["diagnostics"][0]["hotspots"] == []
    assert evidence["analysis"]["diagnostics"][0]["samples"] == []
    assert evidence["analysis"]["diagnostics"][0]["semantic_profile"][
        "opinions"
    ] == []
    actions = evidence["blueprint"]["actions"]
    assert actions[0]["id"] == "action.text_quality"
    assert actions[0]["priority"] == "P0"
    assert actions[1]["id"] == "action.mapping"
    assert actions[1]["priority"] == "P0"
    assert all(item["id"] != "action.diagnostic" for item in actions)


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
                        "opinions": [
                            {"opinion": "Didn稚 fit", "record_count": 12}
                        ]
                    },
                }
            ],
            "samples": [{"comment": "Didn稚 fit"}],
        },
        "catalog": {"scope": {}, "product_mapping": {}},
    }
    text_quality = {
        "status": "needs_review",
        "anomaly_record_count": 12,
        "note": "发现疑似编码异常评论。",
    }

    gate = InsightReportService._apply_live_quality_gate(
        content,
        evidence,
        text_quality,
    )

    assert gate["status"] == "blocked"
    assert gate["consistency"]["status"] == "passed"
    assert gate["decision_readiness"]["status"] == "diagnostic_only"
    assert evidence["source"]["report_status"] == "provisional"
    assert evidence["analysis"]["product_reason_matrix"] == []
    diagnostic = evidence["analysis"]["diagnostics"][0]
    assert diagnostic["hotspots"] == []
    assert diagnostic["samples"] == []
    assert diagnostic["semantic_profile"]["opinions"] == []
    assert all(item["kind"] != "diagnostic" for item in content["findings"])
    assert content["executive_summary"][0]["title"] == "评论文本质量未通过"
    assert all(
        "SK001-701" not in item["statement"]
        for item in content["executive_summary"]
    )
    action_ids = [item["id"] for item in content["actions"]]
    assert action_ids[:2] == ["action.text_quality", "action.mapping"]
    assert "action.diagnostic" not in action_ids
    assert content["caveats"][0].startswith("评论文本质量未通过门禁")
