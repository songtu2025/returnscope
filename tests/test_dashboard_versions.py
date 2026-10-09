from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from test_classification_result_pool import (
    _clone_publishable_segment,
    _publish,
    _seed_result_context,
)

from return_semantics.schemas import ProcessingStatus
from web_backend import dashboard_insights
from web_backend.classification_standard_service import ClassificationStandardService
from web_backend.classification_unit_semantics import refresh_unit_semantics
from web_backend.common import json_text
from web_backend.dashboard_insights import InsightOptions
from web_backend.dashboard_plan import summarize_sources
from web_backend.dashboard_service import DashboardConflict, DashboardService
from web_backend.dashboard_support import version_context
from web_backend.routers.dashboards import create_dashboard_router


def _ready_result(tmp_path: Path):
    context = _seed_result_context(tmp_path)
    version = _publish(context)
    return context, version, DashboardService(context.database)


def _create_dashboard(
    service: DashboardService,
    version_id: str,
    filters: dict | None = None,
):
    plan = service.preflight([version_id], filters or {})
    dashboard = service.create(
        name="退货问题看板",
        description="确定性聚合",
        result_version_ids=[version_id],
        filters=filters or {},
        plan_hash=plan["plan_hash"],
        reason="创建首版看板",
        actor_id="user-1",
    )
    return plan, dashboard


def test_preflight_hash_is_stable_and_blocks_invalid_sources(tmp_path: Path) -> None:
    context, version, service = _ready_result(tmp_path)
    version_id = str(version["version_id"])

    first = service.preflight(
        [version_id, version_id],
        {"order_id": ["ORDER-OTHER", "ORDER-DUP", "ORDER-DUP"]},
    )
    second = service.preflight(
        [version_id],
        {"order_id": ["ORDER-DUP", "ORDER-OTHER"]},
    )
    assert first["ready"] is True
    assert first["plan_hash"] == second["plan_hash"]
    assert first["filters"] == {"order_id": ["ORDER-DUP", "ORDER-OTHER"]}
    assert first["summary"] == {
        "source_count": 1,
        "store_count": 1,
        "listing_count": 1,
        "record_count": 2,
        "unit_count": 1,
        "comment_count": 2,
        "total_comment_count": 2,
        "pending_review_comment_count": 0,
        "comment_statuses": [
            {"status": "POSITIVE", "comment_count": 0},
            {"status": "NEGATIVE", "comment_count": 2},
            {"status": "MIXED", "comment_count": 0},
            {"status": "CONFLICT", "comment_count": 0},
            {"status": "NO_CONFIRMED", "comment_count": 0},
        ],
        "product_name_missing_count": 0,
        "product_unmatched_count": 0,
        "review_changed_unit_count": 0,
        "taxonomy_versions": ["taxonomy-v1"],
        "counting_basis": "feedback_group",
    }
    with pytest.raises(ValueError, match="不支持的筛选字段"):
        service.preflight([version_id], {"category_a": "鞋履"})

    with context.database.transaction() as connection:
        connection.execute(
            """
            UPDATE classification_result_versions
            SET quality_status = 'review_required'
            WHERE id = ?
            """,
            (version_id,),
        )
    changed = service.preflight([version_id], {})
    assert changed["ready"] is True
    assert changed["blockers"] == []
    assert changed["warnings"] == []
    assert changed["filters"] == {}
    assert (
        changed["plan_hash"]
        != service.preflight(
            [version_id],
            {"order_id": ["ORDER-DUP", "ORDER-OTHER"]},
        )["plan_hash"]
    )
    with pytest.raises(DashboardConflict, match="计划已变化"):
        service.create(
            name="过期计划",
            description="",
            result_version_ids=[version_id],
            filters={"order_id": ["ORDER-DUP", "ORDER-OTHER"]},
            plan_hash=first["plan_hash"],
            reason="验证过期哈希",
            actor_id="user-1",
        )
    with context.database.connect() as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM analysis_dashboards").fetchone()[0]
            == 0
        )


def test_changed_review_record_count_is_shared_by_plan_and_version(
    tmp_path: Path,
) -> None:
    context, version, service = _ready_result(tmp_path)
    version_id = str(version["version_id"])
    now = "2026-08-12T00:10:00+00:00"
    with context.database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO review_batches(
                id, base_result_version_id, result_id, status, revision,
                created_by, created_at, updated_at, published_version_id,
                published_at
            ) VALUES ('batch-1', ?, ?, 'published', 1, 'user-1', ?, ?, ?, ?)
            """,
            (version_id, version["result_id"], now, now, version_id, now),
        )
        for review_id, key in (
            ("review-1", context.key),
            ("review-2", "other-key"),
        ):
            connection.execute(
                """
                INSERT INTO review_records(
                    id, task_id, batch_id, base_result_version_id,
                    classification_key, comment, workflow_status,
                    classification_json, updated_by, updated_at
                ) VALUES (?, 'task-1', 'batch-1', ?, ?, '测试评论',
                          'resolved', '{}', 'user-1', ?)
                """,
                (review_id, version_id, key, now),
            )
        changes = (
            (
                "revision-1",
                "review-1",
                1,
                {"semantic_units": []},
                {"semantic_units": [1]},
            ),
            (
                "revision-2",
                "review-1",
                2,
                {"primary_label_codes": []},
                {"primary_label_codes": ["A"]},
            ),
            ("revision-3", "review-2", 1, {"note": "前"}, {"note": "后"}),
        )
        for revision_id, review_id, revision, before, after in changes:
            connection.execute(
                """
                INSERT INTO review_revisions(
                    id, review_record_id, revision, before_json, after_json,
                    note, actor_id, created_at
                ) VALUES (?, ?, ?, ?, ?, '', 'user-1', ?)
                """,
                (
                    revision_id,
                    review_id,
                    revision,
                    json_text(before),
                    json_text(after),
                    now,
                ),
            )

    plan, dashboard = _create_dashboard(service, version_id)
    assert plan["summary"]["review_changed_unit_count"] == 1
    with context.database.connect() as connection:
        current = version_context(
            context.database,
            connection,
            str(dashboard["id"]),
            str(dashboard["version"]["version_id"]),
        )
    assert current["sources"][0]["review_changed_unit_count"] == 1


def test_plan_and_existing_version_use_the_same_source_fields(
    tmp_path: Path,
) -> None:
    context, version, service = _ready_result(tmp_path)
    plan, dashboard = _create_dashboard(service, str(version["version_id"]))

    with context.database.connect() as connection:
        current = version_context(
            context.database,
            connection,
            str(dashboard["id"]),
            str(dashboard["version"]["version_id"]),
        )

    assert current["sources"] == plan["sources"]


def test_preflight_blocks_duplicate_listing_and_review_required(
    tmp_path: Path,
) -> None:
    context = _seed_result_context(tmp_path)
    first = _publish(context)
    second_context = _clone_publishable_segment(context, "duplicate-listing")
    second = _publish(second_context)
    service = DashboardService(context.database)

    conflict = service.preflight(
        [str(first["version_id"]), str(second["version_id"])],
        {},
    )
    assert conflict["ready"] is False
    assert conflict["conflicts"] == [
        {
            "type": "duplicate_store_listing",
            "store_site": "SEEKWAY:US",
            "listing": "L1",
            "result_version_ids": sorted(
                [str(first["version_id"]), str(second["version_id"])]
            ),
        }
    ]

    review_context = _clone_publishable_segment(context, "review-required")
    source = review_context.results[review_context.key]
    review_context.results = {
        review_context.key: source.model_copy(
            update={
                "status": ProcessingStatus.MANUAL_REVIEW,
                "review_reasons": ["需要人工复核"],
            }
        )
    }
    review_version = _publish(review_context)
    partial = service.preflight([str(review_version["version_id"])], {})
    assert partial["ready"] is False
    assert partial["blockers"] == [
        {"type": "empty_scope", "message": "所选统计范围没有记录，请调整范围"}
    ]
    assert partial["warnings"][0]["type"] == "quality_scope_limited"
    assert partial["filters"] == {"quality_status": ["ready"]}
    assert partial["summary"]["record_count"] == 0
    assert partial["summary"]["pending_review_record_count"] == 2
    assert partial["summary"]["comment_count"] == 0
    assert partial["summary"]["total_comment_count"] == 2
    assert partial["summary"]["pending_review_comment_count"] == 2


@pytest.mark.parametrize("status", ["review_required", "unusable", "excluded"])
def test_explicit_record_scope_can_create_and_matches_insight_data(
    tmp_path: Path,
    status: str,
) -> None:
    context, version, service = _ready_result(tmp_path)
    source_id = str(version["version_id"])
    with context.database.transaction() as connection:
        connection.execute(
            "UPDATE classification_result_versions SET quality_status = 'unusable' "
            "WHERE id = ?",
            (source_id,),
        )
        connection.execute(
            "UPDATE classification_result_records SET quality_status = ? "
            "WHERE result_version_id = ? AND order_id = 'ORDER-OTHER'",
            (status, source_id),
        )
    default_plan, default_dashboard = _create_dashboard(service, source_id)
    assert default_plan["ready"] is True
    assert default_plan["filters"] == {"quality_status": ["ready"]}
    assert default_plan["summary"]["record_count"] == 1
    filters = {"quality_status": ["ready", status]}
    plan, dashboard = _create_dashboard(service, source_id, filters)
    dashboard_id = str(dashboard["id"])
    version_id = str(dashboard["version"]["version_id"])
    assert plan["ready"] is True
    assert plan["plan_hash"] != default_plan["plan_hash"]
    assert dashboard["version"]["filters"] == plan["filters"]
    assert plan["summary"]["record_count"] == 2
    records = service.records(dashboard_id, version_id)
    assert records["total"] == 3
    assert {record["quality_status"] for record in records["items"]} == {
        "ready",
        status,
    }
    for report_mode in (False, True):
        insights = service.insights(dashboard_id, version_id, report_mode=report_mode)
        assert insights["summary"]["record_count"] == 2
        assert insights["total_record_count"] == 2
        assert insights["reasons"][0]["record_count"] == 2
    old = service.get(str(default_dashboard["id"]))
    assert old["version"]["summary"]["record_count"] == 1
    assert old["version"]["filters"] == {"quality_status": ["ready"]}


def test_api_allows_unusable_records_without_fabricating_classifications(
    tmp_path: Path,
) -> None:
    context = _seed_result_context(tmp_path)
    result = context.results[context.key]
    context.results = {
        context.key: result.model_copy(
            update={
                "status": ProcessingStatus.MODEL_ERROR,
                "semantic_units": [],
                "problem_label_codes": [],
                "primary_label_codes": [],
                "review_reasons": ["合成系统异常"],
            }
        )
    }
    source_id = str(_publish(context)["version_id"])
    service = DashboardService(context.database)
    app = FastAPI()
    app.include_router(create_dashboard_router(service, lambda: {"id": "user-1"}))
    client = TestClient(app)
    common = {"result_version_ids": [source_id], "filters": {}}
    default_plan = client.post("/api/dashboard-plans/preflight", json=common).json()
    assert default_plan["ready"] is False
    assert default_plan["blockers"][0]["type"] == "empty_scope"
    request = {
        **common,
        "name": "自主选择范围",
        "description": "",
        "reason": "接口验收",
        "plan_hash": default_plan["plan_hash"],
    }
    blocked = client.post("/api/analysis-dashboards", json=request)
    assert blocked.status_code == 409
    assert "存在阻断" in blocked.json()["detail"]
    filters = {"quality_status": ["unusable"]}
    plan = client.post(
        "/api/dashboard-plans/preflight", json={**common, "filters": filters}
    ).json()
    assert plan["ready"] is True
    stale = client.post(
        "/api/analysis-dashboards", json={**request, "filters": filters}
    )
    assert stale.status_code == 409
    created = client.post(
        "/api/analysis-dashboards",
        json={
            **request,
            "filters": filters,
            "plan_hash": plan["plan_hash"],
        },
    )
    assert created.status_code == 201
    dashboard = created.json()
    version_id = str(dashboard["version"]["version_id"])
    insights = service.insights(str(dashboard["id"]), version_id, report_mode=True)
    assert insights["total_record_count"] == 2
    assert insights["reasons"] == []
    assert insights["summary"]["label_coverage"] == 0
    assert service.records(str(dashboard["id"]), version_id)["total"] == 3


def test_create_and_new_version_are_atomic_and_keep_old_version(
    tmp_path: Path,
) -> None:
    context, version, service = _ready_result(tmp_path)
    version_id = str(version["version_id"])
    first_plan, dashboard = _create_dashboard(service, version_id)
    dashboard_id = str(dashboard["id"])
    first_version = dashboard["version"]
    assert dashboard["revision"] == 1
    assert first_version["created_by_name"]
    assert first_version["plan_hash"] == first_plan["plan_hash"]

    second_plan = service.preflight(
        [version_id],
        {"order_id": "ORDER-DUP"},
    )
    second = service.create_version(
        dashboard_id,
        expected_revision=1,
        result_version_ids=[version_id],
        filters={"order_id": "ORDER-DUP"},
        plan_hash=second_plan["plan_hash"],
        reason="只查看重复订单",
        actor_id="user-1",
    )
    assert second["revision"] == 2
    assert second["version"]["version"] == 2
    assert second["version"]["summary"]["record_count"] == 1

    old = service.get(dashboard_id, str(first_version["version_id"]))
    assert old["version"]["version"] == 1
    assert old["version"]["filters"] == {}
    assert old["version"]["plan_hash"] == first_plan["plan_hash"]
    with pytest.raises(DashboardConflict, match="其他用户更新"):
        service.create_version(
            dashboard_id,
            expected_revision=1,
            result_version_ids=[version_id],
            filters={},
            plan_hash=first_plan["plan_hash"],
            reason="过期并发修改",
            actor_id="user-1",
        )
    assert [item["version"] for item in service.versions(dashboard_id)] == [2, 1]
    with context.database.connect() as connection:
        audits = connection.execute(
            """
            SELECT action FROM audit_logs
            WHERE entity_type = 'analysis_dashboard' AND entity_id = ?
            ORDER BY created_at
            """,
            (dashboard_id,),
        ).fetchall()
    assert [row["action"] for row in audits] == ["create", "create_version"]


def test_existing_dashboard_version_keeps_source_record_basis(tmp_path: Path) -> None:
    context, version, service = _ready_result(tmp_path)
    source_id = str(version["version_id"])
    _plan, dashboard = _create_dashboard(service, source_id)
    dashboard_id = str(dashboard["id"])
    old_id = str(dashboard["version"]["version_id"])
    with context.database.transaction() as connection:
        old_context = version_context(
            context.database, connection, dashboard_id, old_id
        )
        legacy_summary = summarize_sources(
            context.database,
            connection,
            old_context["source_ids"],
            old_context["filters"],
            old_context["sources"],
        )
        connection.execute(
            "UPDATE dashboard_dataset_versions SET summary_json = ? WHERE id = ?",
            (json_text(legacy_summary), old_context["dataset_version_id"]),
        )

    next_plan = service.preflight([source_id], {})
    updated = service.create_version(
        dashboard_id,
        expected_revision=1,
        result_version_ids=[source_id],
        filters={},
        plan_hash=next_plan["plan_hash"],
        reason="采用反馈组口径",
        actor_id="user-1",
    )
    new_id = str(updated["version"]["version_id"])
    for selected_id in (old_id, new_id):
        stored_version = service.get(dashboard_id, selected_id)["version"]
        assert service.summary(dashboard_id, selected_id) == {
            "dashboard_id": dashboard_id,
            "version_id": selected_id,
            "dataset_version_id": stored_version["dataset_version_id"],
            **stored_version["summary"],
        }
    assert service.get(dashboard_id, old_id)["version"]["summary"]["record_count"] == 3
    assert service.summary(dashboard_id, old_id)["record_count"] == 3
    assert service.review_bias(dashboard_id, old_id)["total_record_count"] == 3
    assert service.insights(dashboard_id, old_id)["total_record_count"] == 3
    assert (
        service.drilldown(dashboard_id, old_id, "listing")["items"][0]["record_count"]
        == 3
    )
    assert (
        service.get(dashboard_id, new_id)["version"]["summary"]["counting_basis"]
        == "feedback_group"
    )
    assert service.summary(dashboard_id, new_id)["record_count"] == 2
    assert service.review_bias(dashboard_id, new_id)["total_record_count"] == 2
    assert service.insights(dashboard_id, new_id)["total_record_count"] == 2
    assert (
        service.drilldown(dashboard_id, new_id, "listing")["items"][0]["record_count"]
        == 2
    )
    assert service.records(dashboard_id, new_id)["total"] == 3


def test_insights_reuse_saved_version_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, version, service = _ready_result(tmp_path)
    _plan, dashboard = _create_dashboard(service, str(version["version_id"]))
    dashboard_id = str(dashboard["id"])
    version_id = str(dashboard["version"]["version_id"])

    def reject_summary_recalculation(*args, **kwargs):
        raise AssertionError("洞察请求不应重新计算已保存的来源摘要")

    monkeypatch.setattr(
        dashboard_insights,
        "summarize_sources",
        reject_summary_recalculation,
        raising=False,
    )
    assert service.insights(dashboard_id, version_id)["summary"] == {
        **dashboard["version"]["summary"],
        "label_coverage": 100.0,
    }


def test_dashboard_keeps_distinct_mskus_and_source_evidence(tmp_path: Path) -> None:
    context, version, service = _ready_result(tmp_path)
    source_id = str(version["version_id"])
    with context.database.transaction() as connection:
        updated = connection.execute(
            """
            UPDATE classification_result_records
            SET source_sku = 'SOURCE-MSKU-2',
                matched_msku = 'SOURCE-MSKU-2',
                product_sku = 'PRODUCT-SKU-2',
                comment = 'Different evidence'
            WHERE result_version_id = ? AND order_id = 'ORDER-DUP'
              AND source_row = 3
            """,
            (source_id,),
        )
        assert updated.rowcount == 1
        independent_count = connection.execute(
            """
            SELECT COUNT(DISTINCT order_id || ':' || source_sku)
            FROM classification_result_records
            WHERE result_version_id = ?
            """,
            (source_id,),
        ).fetchone()[0]
    assert independent_count == 3

    plan, dashboard = _create_dashboard(service, source_id)
    dashboard_id = str(dashboard["id"])
    version_id = str(dashboard["version"]["version_id"])
    assert plan["summary"]["record_count"] == independent_count
    assert service.insights(dashboard_id, version_id)["total_record_count"] == 3
    by_order = service.drilldown(dashboard_id, version_id, "order_id")
    duplicate_order = next(
        item for item in by_order["items"] if item["value"] == "ORDER-DUP"
    )
    assert duplicate_order["record_count"] == 2
    records = service.records(dashboard_id, version_id, order_id="ORDER-DUP")
    assert records["total"] == 2
    assert {item["source_sku"] for item in records["items"]} == {
        "SOURCE-MSKU-1",
        "SOURCE-MSKU-2",
    }
    assert "Different evidence" in {item["comment"] for item in records["items"]}


def test_create_rolls_back_all_dashboard_rows_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, version, service = _ready_result(tmp_path)
    version_id = str(version["version_id"])
    plan = service.preflight([version_id], {})

    def fail_audit(*_args: object, **_kwargs: object) -> None:
        raise sqlite3.OperationalError("故障注入")

    monkeypatch.setattr(service, "_insert_audit", fail_audit)
    with pytest.raises(sqlite3.OperationalError, match="故障注入"):
        service.create(
            name="事务回滚",
            description="",
            result_version_ids=[version_id],
            filters={},
            plan_hash=plan["plan_hash"],
            reason="验证事务",
            actor_id="user-1",
        )
    with context.database.connect() as connection:
        for table in (
            "analysis_dashboards",
            "dashboard_dataset_versions",
            "dashboard_dataset_sources",
            "dashboard_versions",
        ):
            assert (
                connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
            )


def test_dashboard_drilldown_and_records_follow_business_hierarchy(
    tmp_path: Path,
) -> None:
    context, version, service = _ready_result(tmp_path)
    version_id = str(version["version_id"])
    _plan, dashboard = _create_dashboard(service, version_id)
    dashboard_id = str(dashboard["id"])
    dashboard_version_id = str(dashboard["version"]["version_id"])
    product_name = str(context.dataset.records.iloc[0]["product_name"])

    levels = (
        ("problem", {}, "FIT_TOO_SMALL_U1"),
        ("listing", {"problem": "FIT_TOO_SMALL_U1"}, "L1"),
        (
            "product_name",
            {"problem": "FIT_TOO_SMALL_U1", "listing": "L1"},
            product_name,
        ),
        (
            "product_sku",
            {"problem": "FIT_TOO_SMALL_U1", "product_name": product_name},
            "PRODUCT-SKU-1",
        ),
        (
            "order_id",
            {"problem": "FIT_TOO_SMALL_U1", "product_sku": "PRODUCT-SKU-1"},
            "ORDER-DUP",
        ),
    )
    for group_by, filters, expected in levels:
        grouped = service.drilldown(
            dashboard_id,
            dashboard_version_id,
            group_by,
            **filters,
        )
        assert expected in {item["value"] for item in grouped["items"]}

    records = service.records(
        dashboard_id,
        dashboard_version_id,
        problem="FIT_TOO_SMALL_U1",
        order_id="ORDER-DUP",
    )
    assert records["total"] == 2
    assert {item["product_name"] for item in records["items"]} == {product_name}
    assert {item["product_sku"] for item in records["items"]} == {"PRODUCT-SKU-1"}
    assert all(item["classification"] for item in records["items"])
    assert all(item["evidence"] == ["Too small"] for item in records["items"])
    assert service.summary(dashboard_id, dashboard_version_id)["record_count"] == 2
    assert (
        service.sources(dashboard_id, dashboard_version_id)[0]["result_version_id"]
        == version_id
    )


def test_legacy_comment_status_matches_dashboard_and_record_views(
    tmp_path: Path,
) -> None:
    context, version, service = _ready_result(tmp_path)
    version_id = str(version["version_id"])
    standards = ClassificationStandardService(context.database)
    standards.ensure_bootstrapped()
    standard = next(
        item for item in standards.list() if item["standard_key"] == "footwear"
    )
    legacy = {
        "semantic_units": [
            {
                "fact_id": "F1",
                "label_code": "FIT_GOOD_U1",
                "sentiment": "POSITIVE",
            },
            {
                "fact_id": "F2",
                "label_code": "FIT_TOO_SMALL_U1",
                "sentiment": "NEGATIVE",
            },
        ]
    }
    with context.database.transaction() as connection:
        connection.execute(
            "UPDATE classification_results SET standard_version_id = ? WHERE id = ?",
            (standard["standard_version_id"], version["result_id"]),
        )
        connection.execute(
            "UPDATE classification_units SET classification_json = ? "
            "WHERE result_version_id = ?",
            (json_text(legacy), version_id),
        )
        refresh_unit_semantics(connection, version_id)

    plan, dashboard = _create_dashboard(service, version_id)
    dashboard_id = str(dashboard["id"])
    dashboard_version_id = str(dashboard["version"]["version_id"])
    expected_statuses = [
        {"status": "POSITIVE", "comment_count": 0},
        {"status": "NEGATIVE", "comment_count": 0},
        {"status": "MIXED", "comment_count": 0},
        {"status": "CONFLICT", "comment_count": 2},
        {"status": "NO_CONFIRMED", "comment_count": 0},
    ]
    summaries = (
        plan["summary"],
        service.summary(dashboard_id, dashboard_version_id),
        service.insights(dashboard_id, dashboard_version_id)["summary"],
    )
    for summary in summaries:
        assert summary["comment_statuses"] == expected_statuses
        assert summary["comment_count"] == 2
        assert summary["total_comment_count"] == 2
    records = service.records(dashboard_id, dashboard_version_id)["items"]
    assert records
    assert {record["comment_summary_status"] for record in records} == {"CONFLICT"}
    assert {
        conclusion["status"]
        for record in records
        for conclusion in record["comment_conclusions"]
    } == {"CONFLICT"}


def test_dashboard_insights_are_derived_from_ready_records(tmp_path: Path) -> None:
    context, version, service = _ready_result(tmp_path)
    with context.database.transaction() as connection:
        connection.execute(
            "UPDATE tasks SET snapshot_json = ? WHERE id = 'task-1'",
            ('{"analysis_context":"user_feedback"}',),
        )
    plan, dashboard = _create_dashboard(service, str(version["version_id"]))
    dashboard_id = str(dashboard["id"])
    dashboard_version_id = str(dashboard["version"]["version_id"])
    product_name = str(context.dataset.records.iloc[0]["product_name"])

    insights = service.insights(
        dashboard_id,
        dashboard_version_id,
        problem="FIT_TOO_SMALL_U1",
    )

    assert plan["sources"][0]["analysis_context"] == "user_feedback"
    assert (
        service.sources(dashboard_id, dashboard_version_id)[0]["analysis_context"]
        == "user_feedback"
    )
    assert insights["analysis_context"] == "user_feedback"
    assert insights["counting_basis"] == "feedback_group"
    assert insights["summary"]["record_count"] == 2
    assert insights["summary"]["comment_count"] == 2
    assert insights["summary"]["total_comment_count"] == 2
    assert insights["summary"]["pending_review_comment_count"] == 0
    assert insights["summary"]["comment_statuses"] == [
        {"status": "POSITIVE", "comment_count": 0},
        {"status": "NEGATIVE", "comment_count": 2},
        {"status": "MIXED", "comment_count": 0},
        {"status": "CONFLICT", "comment_count": 0},
        {"status": "NO_CONFIRMED", "comment_count": 0},
    ]
    assert insights["selected_reason"] == {
        "value": "FIT_TOO_SMALL_U1",
        "label": "偏小",
        "label_group": "尺码与适配",
        "record_count": 2,
        "primary_record_count": 2,
        "companion_only_count": 0,
        "primary_rate": 100.0,
        "subjects": ["PRODUCT"],
        "percentage": 100.0,
    }
    assert insights["products"] == [
        {
            "value": product_name,
            "record_count": 2,
            "total_record_count": 2,
            "reason_share": 100.0,
            "product_reason_rate": 100.0,
            "overall_reason_rate": 100.0,
            "lift": 1.0,
            "reliable": False,
        }
    ]
    assert insights["label_coverage"] == 100.0
    assert insights["label_group_breakdown"] == [
        {
            "value": "尺码与适配",
            "record_count": 2,
            "percentage": 100.0,
        }
    ]
    assert insights["product_reason_matrix"][0]["value"] == product_name
    assert insights["product_reason_matrix"][0]["total_record_count"] == 2
    assert insights["product_reason_matrix"][0]["reason_rates"]["FIT_TOO_SMALL_U1"] == {
        "label": "偏小",
        "record_count": 2,
        "percentage": 100.0,
        "lift": 1.0,
    }
    assert insights["subject_breakdown"][0]["value"] == "PRODUCT"
    assert insights["semantic_profile"]["coverage"] == 100.0
    assert insights["evidence"]["total"] == 2
    assert len(insights["evidence"]["items"]) == 2
    assert insights["evidence"]["items"][0]["problem_labels"] == ["偏小"]
    assert insights["filter_options"]["listings"] == ["L1"]

    empty_insights = service.insights(
        dashboard_id,
        dashboard_version_id,
        product_name="不存在的产品",
    )
    assert empty_insights["summary"]["record_count"] == 2
    assert empty_insights["summary"]["comment_count"] == 0
    assert empty_insights["summary"]["total_comment_count"] == 0
    assert empty_insights["summary"]["pending_review_comment_count"] == 0


def test_dashboard_insights_reuse_unchanged_feedback_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, version, service = _ready_result(tmp_path)
    _, dashboard = _create_dashboard(service, str(version["version_id"]))
    dashboard_id = str(dashboard["id"])
    version_id = str(dashboard["version"]["version_id"])
    statements: list[str] = []
    original_connect = context.database.connect

    def traced_connect():
        connection = original_connect()
        connection.set_trace_callback(statements.append)
        return connection

    monkeypatch.setattr(context.database, "connect", traced_connect)
    insights = service.insights(dashboard_id, version_id)
    assert insights["total_record_count"] == insights["summary"]["record_count"]
    assert (
        sum("INSERT INTO dashboard_feedback_options" in sql for sql in statements) == 1
    )
    assert not any("INSERT INTO dashboard_feedback_main" in sql for sql in statements)
    assert (
        sum(
            "SELECT r.result_version_id, u.classification_json" in sql
            for sql in statements
        )
        == 0
    )

    statements.clear()
    filtered = service.insights(dashboard_id, version_id, product_name="不存在的产品")
    assert filtered["total_record_count"] == 0
    assert any("INSERT INTO dashboard_feedback_main" in sql for sql in statements)

    statements.clear()
    detail = service.insights(
        dashboard_id, version_id, product_name="不存在的产品", part="reason"
    )
    assert detail["evidence"]["total"] == 0
    assert not any("INSERT INTO dashboard_feedback_main" in sql for sql in statements)
    assert (
        sum("INSERT INTO dashboard_feedback_options" in sql for sql in statements) == 1
    )


def test_dashboard_insights_parts_match_full_result(tmp_path: Path) -> None:
    context, version, service = _ready_result(tmp_path)
    with context.database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO classification_unit_labels
                (result_version_id, classification_key, label_kind,
                 label_code, label_name, label_group)
            VALUES (?, ?, 'problem', 'TEST_BASELINE', '材料廉价', '质量')
            """,
            (version["version_id"], context.key),
        )
    _, dashboard = _create_dashboard(service, str(version["version_id"]))
    dashboard_id = str(dashboard["id"])
    version_id = str(dashboard["version"]["version_id"])
    full = service.insights(dashboard_id, version_id)
    assert full["co_reasons"][0]["baseline_record_count"] == 2
    assert [(row["period_start"], row["period_end"]) for row in full["trend"]] == [
        ("2026-07-27", "2026-08-02"),
        ("2026-08-03", "2026-08-09"),
    ]
    overview = service.insights(dashboard_id, version_id, part="overview")
    assert overview == {
        key: value
        for key, value in full.items()
        if key
        not in {
            "trend",
            "products",
            "variants",
            "co_reasons",
            "semantic_profile",
            "evidence",
        }
    }
    for selected in full["reasons"][:2]:
        selected_full = service.insights(
            dashboard_id, version_id, problem=selected["value"]
        )
        detail = service.insights(
            dashboard_id, version_id, problem=selected["value"], part="reason"
        )
        for key in (
            "trend",
            "products",
            "variants",
            "co_reasons",
            "semantic_profile",
            "evidence",
        ):
            assert detail[key] == selected_full[key]
        baseline_counts = {
            item["value"]: item["record_count"] for item in full["reasons"]
        }
        for companion in detail["co_reasons"]:
            assert (
                companion["baseline_record_count"]
                == baseline_counts[companion["value"]]
            )
            assert companion["lift"] == round(
                (companion["record_count"] / selected["record_count"])
                / (companion["baseline_record_count"] / full["total_record_count"]),
                2,
            )
        assert detail["selected_reason"]["value"] == selected["value"]
        assert "summary" not in detail
    if full["reasons"]:
        group = full["reasons"][0]["label_group"]
        grouped = service.insights(dashboard_id, version_id, label_group=group)
        grouped_detail = service.insights(
            dashboard_id,
            version_id,
            label_group=group,
            problem=grouped["selected_reason"]["value"],
            part="reason",
        )
        assert grouped_detail["co_reasons"] == grouped["co_reasons"]
        assert grouped_detail["co_reasons"][0]["baseline_record_count"] == 2
        assert grouped_detail["products"] == grouped["products"]


def test_filtered_insights_keep_full_options_and_scoped_evidence(
    tmp_path: Path,
) -> None:
    context, version, service = _ready_result(tmp_path)
    with context.database.transaction(immediate=True) as connection:
        connection.execute(
            """
            UPDATE classification_result_records
            SET product_name = '第二产品'
            WHERE order_id = 'ORDER-OTHER'
            """
        )
    _, dashboard = _create_dashboard(service, str(version["version_id"]))
    insights = service.insights(
        str(dashboard["id"]),
        str(dashboard["version"]["version_id"]),
        problem="FIT_TOO_SMALL_U1",
        product_name="第二产品",
        date_from="2026-08-03",
        date_to="2026-08-03",
    )
    detail = service.insights(
        str(dashboard["id"]),
        str(dashboard["version"]["version_id"]),
        problem="FIT_TOO_SMALL_U1",
        product_name="第二产品",
        date_from="2026-08-03",
        date_to="2026-08-03",
        part="reason",
    )

    assert insights["summary"]["record_count"] == 2
    assert insights["total_record_count"] == 1
    assert set(insights["filter_options"]["product_names"]) == {
        "产品表权威名称",
        "第二产品",
    }
    assert insights["products"][0]["value"] == "第二产品"
    assert insights["products"][0]["record_count"] == 1
    assert insights["evidence"]["total"] == 1
    assert [item["order_id"] for item in insights["evidence"]["items"]] == [
        "ORDER-OTHER"
    ]
    assert detail["selected_reason"]["value"] == insights["selected_reason"]["value"]
    assert (
        detail["selected_reason"]["record_count"]
        == insights["selected_reason"]["record_count"]
    )
    for key in (
        "trend",
        "products",
        "variants",
        "co_reasons",
        "semantic_profile",
        "evidence",
    ):
        assert detail[key] == insights[key]


def test_reason_evidence_pages_match_insight_count_and_filters(tmp_path: Path) -> None:
    context, version, service = _ready_result(tmp_path)
    result_version_id = str(version["version_id"])
    with context.database.transaction() as connection:
        template = dict(
            connection.execute(
                "SELECT * FROM classification_result_records "
                "WHERE result_version_id = ? ORDER BY source_row LIMIT 1",
                (result_version_id,),
            ).fetchone()
        )
        for index in range(11):
            connection.execute(
                """
                INSERT INTO classification_result_records(
                    id, result_version_id, classification_key,
                    source_record_id, source_row, return_date, order_id,
                    store_site, listing, product_name, source_sku,
                    matched_msku, product_sku, asin, fnsku, category_a,
                    category_b, reason, comment, product_match_status,
                    quality_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          ?, ?, ?, ?, ?)
                """,
                (
                    f"evidence-record-{index}",
                    result_version_id,
                    template["classification_key"],
                    f"evidence-source-{index}",
                    100 + index,
                    "2026-08-03",
                    f"EVIDENCE-ORDER-{index}",
                    template["store_site"],
                    template["listing"],
                    template["product_name"],
                    template["source_sku"],
                    template["matched_msku"],
                    template["product_sku"],
                    template["asin"],
                    template["fnsku"],
                    template["category_a"],
                    template["category_b"],
                    template["reason"],
                    f"证据 {index}",
                    template["product_match_status"],
                    "ready",
                ),
            )

    _, dashboard = _create_dashboard(service, result_version_id)
    dashboard_id = str(dashboard["id"])
    dashboard_version_id = str(dashboard["version"]["version_id"])
    filters = {
        "problem": "FIT_TOO_SMALL_U1",
        "product_name": template["product_name"],
        "date_from": "2026-08-03",
        "date_to": "2026-08-03",
    }
    filters["label_group"] = service.insights(
        dashboard_id, dashboard_version_id, **filters
    )["selected_reason"]["label_group"]
    insights = service.insights(dashboard_id, dashboard_version_id, **filters)
    first = service.evidence_page(
        dashboard_id, dashboard_version_id, InsightOptions(**filters)
    )
    second = service.evidence_page(
        dashboard_id, dashboard_version_id, InsightOptions(**filters), page=2
    )

    assert first["total"] == second["total"] == insights["evidence"]["total"]
    assert first["total"] >= 11
    assert first["items"] == insights["evidence"]["items"]
    assert len(first["items"]) == 10
    assert len(second["items"]) == first["total"] - 10
    assert not {item["id"] for item in first["items"]} & {
        item["id"] for item in second["items"]
    }
    assert all(item["return_date"] == "2026-08-03" for item in second["items"])


@pytest.mark.parametrize("product_labeled", [True, False])
def test_subject_scope_counts_only_matching_reason_units(
    tmp_path: Path, product_labeled: bool
) -> None:
    context, version, service = _ready_result(tmp_path)
    version_id = str(version["version_id"])
    with context.database.transaction(immediate=True) as connection:
        row = connection.execute(
            "SELECT id, result_version_id, classification_key, classification_json "
            "FROM classification_units WHERE result_version_id = ? LIMIT 1",
            (version_id,),
        ).fetchone()
        classification = json.loads(row["classification_json"])
        semantic = classification["semantic_units"][0]
        connection.execute(
            """
            INSERT INTO classification_units(
                id, result_version_id, classification_key, reason, comment,
                classification_json, problem_labels_json, system_rerun_required,
                processing_status, quality_status, record_count, model_name,
                prompt_version, taxonomy_version
            )
            SELECT ?, result_version_id, ?, reason, comment, classification_json,
                   problem_labels_json, system_rerun_required, processing_status,
                   quality_status, 1, model_name, prompt_version, taxonomy_version
            FROM classification_units WHERE id = ?
            """,
            ("product-only-unit", "PRODUCT_ONLY", row["id"]),
        )
        connection.execute(
            """
            INSERT INTO classification_unit_labels(
                result_version_id, classification_key, label_kind,
                label_code, label_name, label_group
            )
            SELECT result_version_id, ?, label_kind, label_code, label_name, label_group
            FROM classification_unit_labels
            WHERE result_version_id = ? AND classification_key = ?
            """,
            ("PRODUCT_ONLY", row["result_version_id"], row["classification_key"]),
        )
        connection.execute(
            """
            UPDATE classification_result_records
            SET classification_key = 'PRODUCT_ONLY'
            WHERE id = (
                SELECT id FROM classification_result_records
                WHERE result_version_id = ?
                ORDER BY source_row DESC LIMIT 1
            )
            """,
            (version_id,),
        )
        if not product_labeled:
            connection.execute(
                "DELETE FROM classification_unit_labels "
                "WHERE result_version_id = ? AND classification_key = 'PRODUCT_ONLY'",
                (version_id,),
            )
            connection.execute(
                "UPDATE classification_units SET classification_json = ?, "
                "problem_labels_json = '[]' WHERE id = 'product-only-unit'",
                (json_text({**classification, "semantic_units": []}),),
            )
        classification["semantic_units"].append(
            {
                **semantic,
                "subject": "UNKNOWN",
                "label_code": "QUALITY_GENERAL",
                "opinion": "对象未明确的质量反馈",
            }
        )
        connection.execute(
            "UPDATE classification_units SET classification_json = ? WHERE id = ?",
            (json_text(classification), row["id"]),
        )
        connection.execute(
            """
            INSERT INTO classification_unit_labels(
                result_version_id, classification_key, label_kind,
                label_code, label_name, label_group
            ) VALUES (?, ?, 'problem', 'QUALITY_GENERAL', '整体质量', '质量')
            """,
            (row["result_version_id"], row["classification_key"]),
        )
        refresh_unit_semantics(connection, version_id)
    _, dashboard = _create_dashboard(service, version_id)
    dashboard_id = str(dashboard["id"])
    dashboard_version_id = str(dashboard["version"]["version_id"])

    unknown = service.insights(dashboard_id, dashboard_version_id, subject="UNKNOWN")
    base = service.insights(dashboard_id, dashboard_version_id, part="overview")
    assert base["summary"]["label_coverage"] == (100.0 if product_labeled else 50.0)
    assert unknown["summary"] == base["summary"]
    assert unknown["label_coverage"] == 100.0
    narrowed = service.insights(
        dashboard_id,
        dashboard_version_id,
        subject="UNKNOWN",
        listing="L1",
        product_name="产品表权威名称",
        product_sku="PRODUCT-SKU-1",
        date_from="2026-08-01",
        date_to="2026-08-02",
        part="overview",
    )
    assert narrowed["summary"]["label_coverage"] == 100.0
    assert narrowed["summary"]["comment_count"] == 1
    assert (
        service.insights(
            dashboard_id,
            dashboard_version_id,
            subject="UNKNOWN",
            label_group="质量",
            problem="QUALITY_GENERAL",
            part="overview",
        )["summary"]
        == base["summary"]
    )
    assert unknown["total_record_count"] == 1
    assert (
        unknown["subject_breakdown"]
        == service.insights(dashboard_id, dashboard_version_id, part="overview")[
            "subject_breakdown"
        ]
    )
    assert [
        (reason["value"], reason["record_count"]) for reason in unknown["reasons"]
    ] == [("QUALITY_GENERAL", 1)]
    assert unknown["selected_reason"]["record_count"] == 1
    assert unknown["semantic_profile"]["record_count"] == 1
    assert unknown["evidence"]["total"] == 1
    assert (
        service.evidence_page(
            dashboard_id,
            dashboard_version_id,
            InsightOptions(problem="QUALITY_GENERAL", subject="UNKNOWN"),
        )["total"]
        == 1
    )
    assert (
        service.insights(
            dashboard_id,
            dashboard_version_id,
            subject="UNKNOWN",
            label_group="尺码与适配",
            part="overview",
        )["reasons"]
        == []
    )
    with pytest.raises(ValueError, match="问题对象不合法"):
        service.insights(
            dashboard_id, dashboard_version_id, subject="INVALID", part="overview"
        )


@pytest.mark.parametrize("subject", ["", "PRODUCT"])
def test_dashboard_insights_count_each_semantic_part_once_per_record(
    tmp_path: Path,
    subject: str,
) -> None:
    context, version, service = _ready_result(tmp_path)
    _, dashboard = _create_dashboard(service, str(version["version_id"]))
    with context.database.transaction(immediate=True) as connection:
        row = connection.execute(
            "SELECT id, classification_json FROM classification_units LIMIT 1"
        ).fetchone()
        classification = json.loads(row["classification_json"])
        semantic = classification["semantic_units"][0]
        classification["semantic_units"] = [
            {**semantic, "part": "WHOLE_SHOE", "opinion": "tight", "evidence": "a"},
            {**semantic, "part": "TOE_BOX", "opinion": "tight", "evidence": "b"},
            {**semantic, "part": "TOE_BOX", "opinion": "narrow", "evidence": "c"},
        ]
        connection.execute(
            "UPDATE classification_units SET classification_json = ? WHERE id = ?",
            (json_text(classification), row["id"]),
        )

        refresh_unit_semantics(connection, str(version["version_id"]))
    insights = service.insights(
        str(dashboard["id"]),
        str(dashboard["version"]["version_id"]),
        problem="FIT_TOO_SMALL_U1",
        subject=subject,
    )
    assert insights["subject_breakdown"] == [
        {
            "value": "PRODUCT",
            "label": "商品相关",
            "record_count": 2,
            "semantic_unit_count": 6,
            "percentage": 100.0,
        }
    ]
    assert insights["selected_reason"]["subjects"] == ["PRODUCT"]
    semantic_profile = insights["semantic_profile"]
    assert semantic_profile["record_count"] == 2
    assert {
        (item["value"], item["record_count"]) for item in semantic_profile["parts"]
    } == {
        ("TOE_BOX", 2),
        ("WHOLE_SHOE", 2),
    }
    assert {
        (item["opinion"], item["part"], item["record_count"], item["evidence"])
        for item in semantic_profile["opinions"]
    } == {
        ("narrow", "TOE_BOX", 2, "c"),
        ("tight", "TOE_BOX", 2, "b"),
        ("tight", "WHOLE_SHOE", 2, "a"),
    }


def test_issue_cases_keep_variant_context_and_rank_representative_samples(
    tmp_path: Path,
) -> None:
    context, version, service = _ready_result(tmp_path)
    result_version_id = str(version["version_id"])
    product_name = str(context.dataset.records.iloc[0]["product_name"])
    with context.database.transaction() as connection:
        template = dict(
            connection.execute(
                """
                SELECT * FROM classification_result_records
                WHERE result_version_id = ?
                ORDER BY source_row
                LIMIT 1
                """,
                (result_version_id,),
            ).fetchone()
        )

        def insert_record(
            index: int,
            *,
            classification_key: str,
            product_sku: str,
            comment: str,
            return_date: str,
        ) -> None:
            connection.execute(
                """
                INSERT INTO classification_result_records(
                    id, result_version_id, classification_key,
                    source_record_id, source_row, return_date, order_id,
                    store_site, listing, product_name, source_sku,
                    matched_msku, product_sku, asin, fnsku, category_a,
                    category_b, reason, comment, product_match_status,
                    quality_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          ?, ?, ?, ?, ?)
                """,
                (
                    f"case-record-{index}",
                    result_version_id,
                    classification_key,
                    f"case-source-{index}",
                    1000 + index,
                    return_date,
                    f"CASE-ORDER-{index}",
                    template["store_site"],
                    template["listing"],
                    product_name,
                    template["source_sku"],
                    template["matched_msku"],
                    product_sku,
                    template["asin"],
                    template["fnsku"],
                    template["category_a"],
                    template["category_b"],
                    template["reason"],
                    comment,
                    template["product_match_status"],
                    "ready",
                ),
            )

        for index in range(1, 9):
            insert_record(
                index,
                classification_key=str(context.key),
                product_sku="PRODUCT-SKU-1",
                comment="Frequently reported size issue",
                return_date="2026-07-01",
            )
        insert_record(
            9,
            classification_key=str(context.key),
            product_sku="PRODUCT-SKU-1",
            comment="Latest isolated size issue",
            return_date="2026-09-01",
        )
        for index in range(10, 18):
            insert_record(
                index,
                classification_key="non-issue-key",
                product_sku="PRODUCT-SKU-1",
                comment="No size issue",
                return_date="2026-07-01",
            )
        for index in range(18, 38):
            insert_record(
                index,
                classification_key="non-issue-key",
                product_sku="PRODUCT-SKU-2",
                comment="No size issue",
                return_date="2026-07-01",
            )
        connection.execute(
            """
            UPDATE classification_result_versions
            SET record_count = 40
            WHERE id = ?
            """,
            (result_version_id,),
        )
        connection.execute(
            """
            UPDATE classification_units
            SET record_count = 12
            WHERE result_version_id = ? AND classification_key = ?
            """,
            (result_version_id, str(context.key)),
        )

    _plan, dashboard = _create_dashboard(service, result_version_id)
    cases = service.issue_cases(
        str(dashboard["id"]),
        str(dashboard["version"]["version_id"]),
        ["FIT_TOO_SMALL_U1"],
    )

    assert len(cases) == 1
    case = cases[0]
    assert case["product_name"] == product_name
    assert case["product_sku"] == "PRODUCT-SKU-1"
    assert case["record_count"] == 11
    assert case["total_record_count"] == 19
    assert case["issue_rate"] == 57.9
    assert case["overall_rate"] == 28.2
    assert case["lift"] == 2.05
    assert case["excess_record_count"] == 6
    assert case["semantic_profile"]["coverage"] == 100.0
    assert case["semantic_profile"]["specified_part_coverage"] == 100.0
    assert case["semantic_profile"]["parts"][0]["value"] == "WHOLE_SHOE"
    assert case["samples"][0]["comment"] == "Frequently reported size issue"
    assert case["samples"][0]["record_count"] == 8
    assert case["samples"][1]["comment"] != "Latest isolated size issue"
    assert case["trend"]
    assert (
        service.issue_cases(
            str(dashboard["id"]),
            str(dashboard["version"]["version_id"]),
            ["FIT_TOO_SMALL_U1"],
        )[0]["id"]
        == case["id"]
    )


def test_dashboard_insights_reject_reverse_date_range(tmp_path: Path) -> None:
    _context, version, service = _ready_result(tmp_path)
    _plan, dashboard = _create_dashboard(service, str(version["version_id"]))

    with pytest.raises(ValueError, match="开始日期不能晚于结束日期"):
        service.insights(
            str(dashboard["id"]),
            str(dashboard["version"]["version_id"]),
            date_from="2026-08-02",
            date_to="2026-08-01",
        )


def test_dashboard_record_queries_have_constant_query_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, version, service = _ready_result(tmp_path)
    _plan, dashboard = _create_dashboard(service, str(version["version_id"]))
    dashboard_id = str(dashboard["id"])
    version_id = str(dashboard["version"]["version_id"])
    statements: list[str] = []
    original_connect = context.database.connect

    def traced_connect():
        connection = original_connect()
        connection.set_trace_callback(statements.append)
        return connection

    monkeypatch.setattr(context.database, "connect", traced_connect)
    service.records(dashboard_id, version_id, page_size=200)
    selects = [
        statement
        for statement in statements
        if statement.lstrip().upper().startswith("SELECT")
    ]
    assert len(selects) <= 4


def test_current_version_constraint_rejects_missing_and_cross_dashboard(
    tmp_path: Path,
) -> None:
    context, version, service = _ready_result(tmp_path)
    version_id = str(version["version_id"])
    plan, first = _create_dashboard(service, version_id)
    _second_plan, second = _create_dashboard(service, version_id)

    with context.database.connect() as connection:
        with pytest.raises(sqlite3.IntegrityError, match="current_version_id"):
            connection.execute(
                """
                INSERT INTO analysis_dashboards(
                    id, name, description, status, revision,
                    current_version_id, created_by, created_at, updated_at
                ) VALUES ('invalid-dashboard', '无效', '', 'active', 1,
                          'missing-version', 'user-1', ?, ?)
                """,
                ("2026-08-12T02:00:00+00:00", "2026-08-12T02:00:00+00:00"),
            )
        with pytest.raises(sqlite3.IntegrityError, match="current_version_id"):
            connection.execute(
                """
                UPDATE analysis_dashboards SET current_version_id = ?
                WHERE id = ?
                """,
                (second["version"]["version_id"], first["id"]),
            )

    updated = service.create_version(
        str(first["id"]),
        expected_revision=1,
        result_version_ids=[version_id],
        filters={},
        plan_hash=plan["plan_hash"],
        reason="验证正常换版",
        actor_id="user-1",
    )
    assert updated["revision"] == 2
    context.database.initialize()
    context.database.initialize()
    with context.database.transaction() as connection:
        connection.execute(
            "DELETE FROM analysis_dashboards WHERE id = ?",
            (first["id"],),
        )
    with context.database.connect() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM dashboard_versions WHERE dashboard_id = ?",
                (first["id"],),
            ).fetchone()[0]
            == 0
        )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_product_dataset_lineage_changes_hash_and_stays_traceable(
    tmp_path: Path,
) -> None:
    context, version, service = _ready_result(tmp_path)
    result_version_id = str(version["version_id"])
    original = service.preflight([result_version_id], {})
    original_source = original["sources"][0]
    assert original_source["dataset_version_id"] == "version-returns"
    assert original_source["product_version_id"] == "version-products"
    assert original_source["dataset_version"] == 1
    assert original_source["product_version"] == 1

    with context.database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO dataset_versions(
                id, dataset_id, version, file_path, original_name,
                content_type, size_bytes, sha256, row_count, column_count,
                schema_json, quality_json, change_note, created_by, created_at
            )
            SELECT 'version-products-2', dataset_id, 2, file_path, original_name,
                   content_type, size_bytes, 'products-sha-v2', row_count,
                   column_count, schema_json, quality_json, '产品信息升级',
                   created_by, '2026-08-12T02:10:00+00:00'
            FROM dataset_versions WHERE id = 'version-products'
            """
        )
        connection.execute(
            """
            UPDATE classification_results SET product_version_id = ?
            WHERE id = ?
            """,
            ("version-products-2", original_source["result_id"]),
        )

    changed = service.preflight([result_version_id], {})
    assert changed["plan_hash"] != original["plan_hash"]
    changed_source = changed["sources"][0]
    assert changed_source["product_version_id"] == "version-products-2"
    assert changed_source["product_version"] == 2
    assert changed_source["product_dataset_name"]

    dashboard = service.create(
        name="产品版本血缘",
        description="",
        result_version_ids=[result_version_id],
        filters={},
        plan_hash=changed["plan_hash"],
        reason="验证产品信息版本",
        actor_id="user-1",
    )
    dashboard_id = str(dashboard["id"])
    dashboard_version_id = str(dashboard["version"]["version_id"])
    snapshot = dashboard["version"]["source_snapshot"][0]
    source = service.sources(dashboard_id, dashboard_version_id)[0]
    history_source = service.versions(dashboard_id)[0]["source_snapshot"][0]
    for item in (snapshot, source, history_source):
        assert item["dataset_version_id"] == "version-returns"
        assert item["dataset_version"] == 1
        assert item["product_version_id"] == "version-products-2"
        assert item["product_version"] == 2
        assert item["dataset_name"]
        assert item["product_dataset_name"]

    product_name = str(context.dataset.records.iloc[0]["product_name"])
    records = service.records(dashboard_id, dashboard_version_id, page_size=200)
    assert {item["product_name"] for item in records["items"]} == {product_name}


def test_dashboard_schema_upgrade_and_router_contract(tmp_path: Path) -> None:
    context, version, service = _ready_result(tmp_path)
    with context.database.connect() as connection:
        connection.executescript(
            """
            DROP TABLE ai_insight_report_versions;
            DROP TABLE ai_insight_reports;
            DROP TABLE dashboard_versions;
            DROP TABLE dashboard_dataset_sources;
            DROP TABLE dashboard_dataset_versions;
            DROP TABLE analysis_dashboards;
            """
        )
    context.database.initialize()
    context.database.initialize()
    with context.database.connect() as connection:
        tables = {
            row["name"]
            for row in connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'table' AND name LIKE '%dashboard%'
                """
            ).fetchall()
        }
        assert tables == {
            "analysis_dashboards",
            "dashboard_dataset_versions",
            "dashboard_dataset_sources",
            "dashboard_versions",
        }
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM classification_result_versions"
            ).fetchone()[0]
            == 1
        )

    app = FastAPI()
    app.include_router(create_dashboard_router(service, lambda: {"id": "user-1"}))
    client = TestClient(app)
    preflight = client.post(
        "/api/dashboard-plans/preflight",
        json={"result_version_ids": [version["version_id"]], "filters": {}},
    )
    assert preflight.status_code == 200
    created = client.post(
        "/api/analysis-dashboards",
        json={
            "name": "接口看板",
            "description": "",
            "result_version_ids": [version["version_id"]],
            "filters": {},
            "plan_hash": preflight.json()["plan_hash"],
            "reason": "接口验收",
        },
    )
    assert created.status_code == 201
    assert client.get("/api/analysis-dashboards").json()["total"] == 1
    dashboard = created.json()
    result = client.get(
        f"/api/analysis-dashboards/{dashboard['id']}/versions/"
        f"{dashboard['version']['version_id']}/records"
    )
    assert result.status_code == 200
    assert result.json()["total"] == 3
    evidence_path = (
        f"/api/analysis-dashboards/{dashboard['id']}/versions/"
        f"{dashboard['version']['version_id']}/evidence"
    )
    evidence = client.get(evidence_path, params={"problem": "FIT_TOO_SMALL_U1"})
    assert evidence.status_code == 200
    assert evidence.json()["page_size"] == 10
    assert evidence.json()["total"] == 2
    insight_path = evidence_path.replace("/evidence", "/insights")
    scoped = client.get(insight_path, params={"subject": "PRODUCT", "part": "overview"})
    assert scoped.status_code == 200
    assert scoped.json()["reasons"][0]["record_count"] == 2
    assert (
        client.get(
            evidence_path,
            params={"problem": "FIT_TOO_SMALL_U1", "subject": "UNKNOWN"},
        ).json()["total"]
        == 0
    )
    assert (
        client.get(
            insight_path, params={"subject": "INVALID", "part": "overview"}
        ).status_code
        == 400
    )

    denied = FastAPI()

    def reject_user():
        raise HTTPException(status_code=401, detail="请先登录")

    denied.include_router(create_dashboard_router(service, reject_user))
    assert TestClient(denied).get("/api/analysis-dashboards").status_code == 401
    assert TestClient(denied).get(evidence_path).status_code == 401


def test_cross_version_group_mapping_deduplicates_records(tmp_path):
    context, first, service = _ready_result(tmp_path)
    second = _publish(_clone_publishable_segment(context, "unified"))
    ids = [str(first["version_id"]), str(second["version_id"])]
    with context.database.transaction() as connection:
        for version_id, taxonomy_version, listing in (
            (ids[0], "water-shoes-2026-09-06-v3", "L1"),
            (ids[1], "footwear-unified-2026-09-06-v1", "L2"),
        ):
            connection.execute(
                "UPDATE classification_results SET taxonomy_version = ?, listing = ? WHERE id = (SELECT result_id FROM classification_result_versions WHERE id = ?)",
                (taxonomy_version, listing, version_id),
            )
        connection.execute(
            "UPDATE classification_unit_labels SET label_group = '尺码与适配', label_code = 'FIT_TOO_SMALL_U1' WHERE result_version_id = ?",
            (ids[1],),
        )
        connection.execute(
            "INSERT INTO classification_unit_labels(result_version_id, classification_key, label_kind, label_code, label_name, label_group) VALUES (?, ?, 'problem', 'FIT_TOO_TIGHT_NARROW', '偏窄', '尺码与合脚')",
            (ids[0], context.key),
        )
    plan = service.preflight(ids, {})
    dashboard = service.create(
        name="跨版本验证",
        description="",
        result_version_ids=ids,
        filters={},
        plan_hash=plan["plan_hash"],
        reason="验证分组计数",
        actor_id="user-1",
    )
    result = service.insights(
        str(dashboard["id"]), str(dashboard["version"]["version_id"])
    )
    assert result["group_alignment"] == "unified-v1"
    groups = result["label_group_breakdown"]
    assert len(groups) == 1
    assert groups[0]["value"] == "尺码与适配"
    assert groups[0]["record_count"] == 4
    companion = next(
        reason
        for reason in result["reasons"]
        if reason["value"] == "FIT_TOO_TIGHT_NARROW"
    )
    assert companion["record_count"] == 2
    assert companion["primary_record_count"] == 0
    assert companion["companion_only_count"] == 2
