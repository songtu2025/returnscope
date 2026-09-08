from __future__ import annotations

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
from web_backend.dashboard_service import DashboardConflict, DashboardService
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
        "record_count": 3,
        "unit_count": 1,
        "product_name_missing_count": 0,
        "product_unmatched_count": 0,
        "review_changed_unit_count": 0,
        "taxonomy_versions": ["taxonomy-v1"],
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
    assert changed["warnings"][0]["type"] == "quality_review_pending"
    assert changed["filters"] == {"quality_status": ["ready"]}
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
    assert partial["ready"] is True
    assert partial["blockers"] == []
    assert partial["warnings"][0]["type"] == "quality_review_pending"
    assert partial["filters"] == {"quality_status": ["ready"]}
    assert partial["summary"]["record_count"] == 0
    assert partial["summary"]["pending_review_record_count"] == 3


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
    assert second["version"]["summary"]["record_count"] == 2

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
    assert service.summary(dashboard_id, dashboard_version_id)["record_count"] == 3
    assert (
        service.sources(dashboard_id, dashboard_version_id)[0]["result_version_id"]
        == version_id
    )


def test_dashboard_insights_are_derived_from_ready_records(tmp_path: Path) -> None:
    context, version, service = _ready_result(tmp_path)
    _plan, dashboard = _create_dashboard(service, str(version["version_id"]))
    dashboard_id = str(dashboard["id"])
    dashboard_version_id = str(dashboard["version"]["version_id"])
    product_name = str(context.dataset.records.iloc[0]["product_name"])

    insights = service.insights(
        dashboard_id,
        dashboard_version_id,
        problem="FIT_TOO_SMALL_U1",
    )

    assert insights["summary"]["record_count"] == 3
    assert insights["selected_reason"] == {
        "value": "FIT_TOO_SMALL_U1",
        "label": "偏小",
        "label_group": "尺码与适配",
        "record_count": 3,
        "primary_record_count": 3,
        "companion_only_count": 0,
        "primary_rate": 100.0,
        "subjects": ["PRODUCT"],
        "percentage": 100.0,
    }
    assert insights["products"] == [
        {
            "value": product_name,
            "record_count": 3,
            "total_record_count": 3,
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
            "record_count": 3,
            "percentage": 100.0,
        }
    ]
    assert insights["product_reason_matrix"][0]["value"] == product_name
    assert insights["product_reason_matrix"][0]["total_record_count"] == 3
    assert insights["product_reason_matrix"][0]["reason_rates"]["FIT_TOO_SMALL_U1"] == {
        "label": "偏小",
        "record_count": 3,
        "percentage": 100.0,
        "lift": 1.0,
    }
    assert insights["subject_breakdown"][0]["value"] == "PRODUCT"
    assert insights["semantic_profile"]["coverage"] == 100.0
    assert insights["evidence"]["total"] == 3
    assert len(insights["evidence"]["items"]) == 3
    assert insights["evidence"]["items"][0]["problem_labels"] == ["偏小"]
    assert insights["filter_options"]["listings"] == ["L1"]


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
    assert case["record_count"] == 12
    assert case["total_record_count"] == 20
    assert case["issue_rate"] == 60.0
    assert case["overall_rate"] == 30.0
    assert case["lift"] == 2.0
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

    denied = FastAPI()

    def reject_user():
        raise HTTPException(status_code=401, detail="请先登录")

    denied.include_router(create_dashboard_router(service, reject_user))
    assert TestClient(denied).get("/api/analysis-dashboards").status_code == 401


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
    assert groups[0]["record_count"] == 6
