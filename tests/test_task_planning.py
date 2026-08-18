from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from return_semantics.capabilities import load_capability_registry
from return_semantics.data import (
    RETURN_COLUMNS,
    ReturnDataset,
    load_return_dataset,
    load_return_dataset_auto,
)
from return_semantics.exporter import export_results
from return_semantics.pipeline import (
    ModelServiceUnavailable,
    PipelineCancelled,
    PipelineRun,
)
from return_semantics.schemas import ProcessingStatus, ValidatedClassification
from return_semantics.task_plan import build_category_execution_plan
from web_backend.agent_runner import AgentRunner
from web_backend.analysis_service import AnalysisFilters, AnalysisService
from web_backend.classification_result_service import ResultPublicationError
from web_backend.common import list_audit
from web_backend.database import Database
from web_backend.dataset_service import inspect_file
from web_backend.routers.tasks import create_task_router
from web_backend.settings import PROJECT_ROOT, Settings
from web_backend.task_plan_service import TaskPlanService
from web_backend.task_service import (
    TaskPlanConflict,
    TaskRevisionConflict,
    TaskService,
)
from web_backend.task_state import summarize_task_status
from web_backend.worker import TaskWorker


class NoopRunner:
    def run_segment(self, _task_id: str, _segment_id: str) -> None:
        return

    def finalize_task(self, _task_id: str) -> None:
        return


def _write_inputs(tmp_path: Path) -> tuple[Path, Path]:
    returns_path = tmp_path / "returns.csv"
    rows = [
        {
            "return-date": "2026-08-01",
            "order-id": "ORDER-1",
            "sku": "SKU-1",
            "asin": "ASIN-1",
            "fnsku": "FNSKU-1",
            "product-name": "Water Shoes",
            "quantity": "1",
            "reason": "Too large",
            "customer-comments": "鞋子太大",
        },
        {
            "return-date": "2026-08-02",
            "order-id": "ORDER-2",
            "sku": "SKU-2",
            "asin": "ASIN-2",
            "fnsku": "FNSKU-2",
            "product-name": "Unknown",
            "quantity": "1",
            "reason": "Unknown",
            "customer-comments": "无法判断",
        },
    ]
    pd.DataFrame(rows, columns=RETURN_COLUMNS).to_csv(
        returns_path,
        index=False,
        encoding="utf-8-sig",
    )
    products_path = tmp_path / "products.xlsx"
    products = pd.DataFrame(
        [
            {
                "MSKU": "SKU-1",
                "店铺/站点": "SEEKWAY:US",
                "Listing": "L1",
                "品类A": "水鞋",
                "品类B": "薄底水鞋",
            },
            {
                "MSKU": "SKU-2",
                "店铺/站点": "SEEKWAY:US",
                "Listing": "L1",
                "品类A": "未配置逻辑",
                "品类B": "未配置逻辑",
            },
        ]
    )
    with pd.ExcelWriter(products_path, engine="openpyxl") as writer:
        products.to_excel(writer, sheet_name="产品信息汇总表", index=False)
    return returns_path, products_path


def _database_with_inputs(tmp_path: Path) -> tuple[Database, Path, Path]:
    returns_path, products_path = _write_inputs(tmp_path)
    database = Database(tmp_path / "app.db")
    database.initialize()
    with database.transaction(immediate=True) as connection:
        connection.execute(
            """
            INSERT INTO users(
                id, email, display_name, password_hash, created_at
            ) VALUES ('user-1', 'user@example.com', '用户', 'hash', '2026-01-01')
            """
        )
        for kind, path in (("returns", returns_path), ("products", products_path)):
            connection.execute(
                """
                INSERT INTO datasets(
                    id, name, kind, current_version, created_by,
                    created_at, updated_at
                ) VALUES (?, ?, ?, 1, 'user-1', '2026-01-01', '2026-01-01')
                """,
                (f"dataset-{kind}", kind, kind),
            )
            connection.execute(
                """
                INSERT INTO dataset_versions(
                    id, dataset_id, version, file_path, original_name,
                    content_type, size_bytes, sha256, row_count,
                    column_count, schema_json, quality_json,
                    created_by, created_at
                ) VALUES (?, ?, 1, ?, ?, 'application/octet-stream', 1,
                          ?, 2, 6, '[]', '{}', 'user-1', '2026-01-01')
                """,
                (
                    f"version-{kind}",
                    f"dataset-{kind}",
                    str(path),
                    path.name,
                    f"hash-{kind}",
                ),
            )
        connection.execute(
            """
            INSERT INTO api_connections(
                id, name, provider, active_version_id,
                created_by, created_at, updated_at
            ) VALUES (
                'connection-1', '线路', 'responses-compatible', 'config-1',
                'user-1', '2026-01-01', '2026-01-01'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO api_config_versions(
                id, connection_id, version, base_url, api_key_ciphertext,
                primary_model, primary_effort, cheap_effort,
                secondary_effort, created_by, created_at, published_at
            ) VALUES (
                'config-1', 'connection-1', 1, 'https://example.com', 'key',
                'model', 'medium', 'low', 'high', 'user-1',
                '2026-01-01', '2026-01-01'
            )
            """
        )
    return database, returns_path, products_path


def _create_task(
    database: Database,
    policy: str,
) -> dict[str, object]:
    service = TaskService(database)
    preflight = service.preflight(
        dataset_version_id="version-returns",
        product_version_id="version-products",
        store="SEEKWAY:US",
        listing="L1",
        config_version_id="config-1",
    )
    return service.create(
        actor_id="user-1",
        title="混合品类任务",
        dataset_version_id="version-returns",
        product_version_id="version-products",
        store="SEEKWAY:US",
        listing="L1",
        config_version_id="config-1",
        plan_hash=str(preflight["plan_hash"]),
        unresolved_policy=policy,
    )


def _add_resolved_product_version(
    database: Database,
    products_path: Path,
) -> str:
    return _add_product_version(
        database,
        products_path,
        version=2,
        category_a="眼镜",
        category_b="儿童眼镜",
    )


def _add_product_version(
    database: Database,
    products_path: Path,
    version: int,
    category_a: str,
    category_b: str,
) -> str:
    products = pd.read_excel(
        products_path,
        sheet_name="产品信息汇总表",
    ).fillna("")
    products.loc[products["MSKU"].eq("SKU-2"), ["品类A", "品类B"]] = [
        category_a,
        category_b,
    ]
    resolved_path = products_path.with_name(f"products-v{version}.xlsx")
    version_id = f"version-products-{version}"
    with pd.ExcelWriter(resolved_path, engine="openpyxl") as writer:
        products.to_excel(writer, sheet_name="产品信息汇总表", index=False)
    with database.transaction(immediate=True) as connection:
        connection.execute(
            """
            INSERT INTO dataset_versions(
                id, dataset_id, version, file_path, original_name,
                content_type, size_bytes, sha256, row_count,
                column_count, schema_json, quality_json,
                created_by, created_at
            ) VALUES (?, 'dataset-products', ?, ?, ?,
                      'application/octet-stream', 1, ?,
                      2, 6, '[]', '{}', 'user-1', ?)
            """,
            (
                version_id,
                version,
                str(resolved_path),
                resolved_path.name,
                f"hash-products-{version}",
                f"2026-01-{version:02d}",
            ),
        )
        connection.execute(
            """
            UPDATE datasets SET current_version = ?
            WHERE id = 'dataset-products'
            """,
            (version,),
        )
    return version_id


def _install_fake_runner(
    monkeypatch,
    calls: list[str],
    failing_taxonomy: str | None = None,
) -> None:
    def fake_classify_comments(**kwargs) -> PipelineRun:
        selected = kwargs["unique_comments"]
        taxonomy = kwargs["taxonomy"]
        calls.append(taxonomy.version)
        if taxonomy.version == failing_taxonomy:
            raise RuntimeError("测试片段失败")
        if kwargs["progress"] is not None:
            kwargs["progress"](len(selected), len(selected))
        classifications = {
            str(row.classification_key): ValidatedClassification(
                classification_key=str(row.classification_key),
                semantic_units=[],
                unknown_semantics=[],
                problem_label_codes=[],
                positive_label_codes=[],
                primary_label_codes=[],
                status=ProcessingStatus.AUTO_APPROVED,
                review_reasons=[],
                model_name="fake-model",
                prompt_version="test",
                taxonomy_version=taxonomy.version,
            )
            for row in selected.itertuples(index=False)
        }
        return PipelineRun(
            classifications=classifications,
            usage={"input_tokens": len(selected)},
            usage_by_model={"fake-model": {"input_tokens": len(selected)}},
            cache_hits=0,
            cache_hits_by_model={},
            model_calls=1,
            model_calls_by_model={"fake-model": 1},
            request_metrics={"requests": 1},
            routing={"primary": 1},
        )

    def fake_export_results(output_path: Path, **_kwargs) -> None:
        output_path.touch()

    monkeypatch.setattr(
        "web_backend.agent_runner.classify_comments",
        fake_classify_comments,
    )
    monkeypatch.setattr(
        "web_backend.agent_runner.Sub2APIClient",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(
        "web_backend.agent_runner.export_results",
        fake_export_results,
    )


def _run_task_segments(
    database: Database,
    runner: AgentRunner,
    task_id: str,
    limit: int | None = None,
) -> list[str]:
    worker = TaskWorker(database, runner, concurrency=1)
    segment_ids: list[str] = []
    try:
        while limit is None or len(segment_ids) < limit:
            claimed = worker._claim_next_segment()
            if claimed is None:
                break
            claimed_task_id, segment_id = claimed
            assert claimed_task_id == task_id
            runner.run_segment(claimed_task_id, segment_id)
            segment_ids.append(segment_id)
        worker._finalize_pending_results()
    finally:
        worker.stop()
    return segment_ids


def test_real_seekway_plan_matches_exact_product_snapshot() -> None:
    returns_path = PROJECT_ROOT / "input_data" / "SEEKWAY_US_.csv"
    products_path = PROJECT_ROOT / "input_data" / "产品信息_20231103.xlsx"
    dataset = load_return_dataset(returns_path, products_path, "SEEKWAY:US")
    registry = load_capability_registry(
        PROJECT_ROOT / "config/category_capabilities.json"
    )

    plan = build_category_execution_plan(dataset, registry).summary

    assert plan["unique_comment_count"] == 37_373
    assert plan["executable_count"] == 37_257
    assert plan["executable_record_count"] == 93_586
    assert plan["blocked_count"] == 0
    assert plan["excluded_count"] == 116
    assert plan["excluded_record_count"] == 118
    assert plan["unmatched_product_count"] == 116
    assert plan["missing_category_count"] == 0
    assert plan["unknown_category_count"] == 0


def test_preflight_is_deterministic_and_never_calls_model(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database, _returns_path, _products_path = _database_with_inputs(tmp_path)

    def fail_if_called(**_kwargs) -> None:
        raise AssertionError("预检不得调用模型")

    monkeypatch.setattr(
        "return_semantics.category_pipeline.classify_comments",
        fail_if_called,
    )
    service = TaskService(database)
    first = service.preflight(
        "version-returns",
        "version-products",
        "SEEKWAY:US",
        "L1",
        "config-1",
    )
    second = service.preflight(
        "version-returns",
        "version-products",
        "SEEKWAY:US",
        "L1",
        "config-1",
    )

    assert first["plan_hash"] == second["plan_hash"]
    assert first["record_count"] == 2
    assert first["valid_comment_count"] == 2
    assert first["executable_count"] == 1
    assert first["missing_category_count"] == 0
    assert first["unknown_category_count"] == 1
    assert first["excluded_count"] == 1
    assert first["blocked_count"] == 1
    assert first["unresolved_product_count"] == 1
    assert first["unresolved_products"] == [
        {
            "product_key": "SKU-2",
            "store": "SEEKWAY:US",
            "msku": "SKU-2",
            "product_name": "",
            "current_category_a": "未配置逻辑",
            "current_category_b": "未配置逻辑",
            "suggested_listing": "L1",
            "record_count": 1,
            "comment_count": 1,
            "issue": "unsupported_category",
            "existing_product": True,
            "editable": True,
        }
    ]
    assert any(
        option["category_b"] == "儿童眼镜" for option in first["category_options"]
    )


def test_preflight_normalizes_html_escaped_sku(
    tmp_path: Path,
) -> None:
    database, returns_path, products_path = _database_with_inputs(tmp_path)
    returns = pd.read_csv(returns_path, dtype=str).fillna("")
    returns.loc[returns["order-id"].eq("ORDER-2"), "sku"] = (
        "SK002-1431 Leaf&amp;Feather 40-41"
    )
    returns.to_csv(returns_path, index=False, encoding="utf-8-sig")
    products = pd.read_excel(
        products_path,
        sheet_name="产品信息汇总表",
        dtype=str,
    ).fillna("")
    products["产品名称"] = ""
    products.loc[len(products)] = {
        "MSKU": "SK002-1431 Leaf&Feather 40-41",
        "店铺/站点": "SEEKWAY:US",
        "Listing": "SK002",
        "品类A": "水鞋",
        "品类B": "薄底水鞋",
        "产品名称": "叶子羽毛水鞋",
    }
    with pd.ExcelWriter(products_path, engine="openpyxl") as writer:
        products.to_excel(writer, sheet_name="产品信息汇总表", index=False)

    plan = TaskPlanService(database).preflight(
        "version-returns",
        "version-products",
        "SEEKWAY:US",
        None,
        "config-1",
    )
    assert plan["excluded_count"] == 0
    assert plan["blocked_count"] == 0
    assert plan["executable_count"] == 2
    assert plan["unmatched_product_count"] == 0
    assert plan["unresolved_products"] == []


def test_unknown_products_from_multiple_stores_are_excluded(tmp_path: Path) -> None:
    returns_path = tmp_path / "multi-store-returns.csv"
    products_path = tmp_path / "multi-store-products.xlsx"
    pd.DataFrame(
        [
            {
                "return-date": "2026-08-01",
                "order-id": "US-1",
                "sku": "ITEM-1431 Black New 40",
                "asin": "",
                "fnsku": "",
                "product-name": "US product",
                "quantity": "1",
                "reason": "NOT_AS_DESCRIBED",
                "customer-comments": "Too small",
                "店铺/站点": "SEEKWAY:US",
            },
            {
                "return-date": "2026-08-01",
                "order-id": "CA-1",
                "sku": "ITEM-1431 Red New 40",
                "asin": "",
                "fnsku": "",
                "product-name": "CA product",
                "quantity": "1",
                "reason": "NOT_AS_DESCRIBED",
                "customer-comments": "Too large",
                "店铺/站点": "SEEKWAY:CA",
            },
        ]
    ).to_csv(returns_path, index=False, encoding="utf-8-sig")
    products = pd.DataFrame(
        [
            {
                "MSKU": "ITEM-1431 Black 40",
                "店铺/站点": "SEEKWAY:US",
                "Listing": "US-LISTING",
                "产品名称": "US candidate",
                "品类A": "眼镜",
                "品类B": "儿童眼镜",
            },
            {
                "MSKU": "ITEM-1431 Red 40",
                "店铺/站点": "SEEKWAY:CA",
                "Listing": "CA-LISTING",
                "产品名称": "CA candidate",
                "品类A": "遮阳帽",
                "品类B": "儿童渔夫帽",
            },
        ]
    )
    with pd.ExcelWriter(products_path, engine="openpyxl") as writer:
        products.to_excel(writer, sheet_name="产品信息汇总表", index=False)
    dataset = load_return_dataset_auto(returns_path, products_path)
    registry = load_capability_registry(
        PROJECT_ROOT / "config" / "category_capabilities.json"
    )
    execution_plan = build_category_execution_plan(dataset, registry)

    unresolved = TaskPlanService(Database(tmp_path / "unused.db"))._unresolved_products(
        dataset,
        execution_plan,
        products_path,
        "AUTO",
        None,
    )

    assert execution_plan.summary["excluded_count"] == 2
    assert execution_plan.summary["blocked_count"] == 0
    assert execution_plan.summary["unmatched_product_count"] == 2
    assert {item["issue"] for item in unresolved} == {"product_not_found"}
    assert {item["product_key"] for item in unresolved} == {
        "SEEKWAY:US/ITEM-1431 Black New 40",
        "SEEKWAY:CA/ITEM-1431 Red New 40",
    }


def test_stale_plan_is_rejected_and_segments_are_persisted(tmp_path: Path) -> None:
    database, _returns_path, products_path = _database_with_inputs(tmp_path)
    service = TaskService(database)
    preflight = service.preflight(
        "version-returns",
        "version-products",
        "SEEKWAY:US",
        "L1",
        "config-1",
    )
    task = _create_task(database, "run_ready")

    assert task["snapshot"]["execution_plan"]["plan_hash"] == preflight["plan_hash"]
    assert task["snapshot"]["execution_plan"]["unresolved_policy"] == "run_ready"
    assert task["snapshot"]["returns"] == {
        "dataset_id": "dataset-returns",
        "version_id": "version-returns",
        "version": 1,
        "name": "returns",
        "sha256": "hash-returns",
    }
    assert task["snapshot"]["products"] == {
        "dataset_id": "dataset-products",
        "version_id": "version-products",
        "version": 1,
        "name": "products",
        "sha256": "hash-products",
    }
    assert set(task["snapshot"]["config"]) == {
        "version_id",
        "version",
        "connection_id",
        "connection",
        "strategy_source",
        "primary_model",
        "primary_effort",
        "cheap_model",
        "cheap_effort",
        "cheap_audit_percent",
        "secondary_model",
        "secondary_effort",
    }
    assert task["snapshot"]["config"]["strategy_source"] == "connection"
    assert set(task["snapshot"]["execution_plan"]) == {
        "registry_version",
        "plan_hash",
        "unresolved_policy",
        "segment_order",
        "summary",
    }
    assert [
        (segment["agent_key"], segment["status"]) for segment in task["segments"]
    ] == [("footwear", "queued")]

    products = pd.read_excel(products_path, sheet_name="产品信息汇总表").fillna("")
    products.loc[products["MSKU"].eq("SKU-2"), ["品类A", "品类B"]] = [
        "眼镜",
        "儿童眼镜",
    ]
    with pd.ExcelWriter(products_path, engine="openpyxl") as writer:
        products.to_excel(writer, sheet_name="产品信息汇总表", index=False)
    with pytest.raises(TaskPlanConflict):
        service.create(
            actor_id="user-1",
            title="过期计划",
            dataset_version_id="version-returns",
            product_version_id="version-products",
            store="SEEKWAY:US",
            listing="L1",
            config_version_id="config-1",
            plan_hash=str(preflight["plan_hash"]),
            unresolved_policy="run_ready",
        )

    with database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO tasks(
                id, title, owner_id, dataset_version_id,
                product_version_id, config_version_id, store,
                status, stage, snapshot_json, created_at
            ) VALUES (
                'old-task', '旧任务', 'user-1', 'version-returns',
                'version-products', 'config-1', 'SEEKWAY:US',
                'completed', '完成', '{}', '2026-01-01'
            )
            """
        )
    assert service.get("old-task")["segments"] == []


def test_task_creation_persists_requested_segment_order(tmp_path: Path) -> None:
    database, _returns_path, products_path = _database_with_inputs(tmp_path)
    product_version_id = _add_resolved_product_version(database, products_path)
    service = TaskService(database)
    preflight = service.preflight(
        "version-returns",
        product_version_id,
        "SEEKWAY:US",
        "L1",
        "config-1",
    )
    requested_order = [
        str(segment["segment_key"]) for segment in reversed(preflight["segments"])
    ]

    task = service.create(
        actor_id="user-1",
        title="自定义片段顺序",
        dataset_version_id="version-returns",
        product_version_id=product_version_id,
        store="SEEKWAY:US",
        listing="L1",
        config_version_id="config-1",
        plan_hash=str(preflight["plan_hash"]),
        unresolved_policy="run_ready",
        segment_order=requested_order,
    )

    assert [segment["segment_key"] for segment in task["segments"]] == requested_order
    assert [segment["execution_order"] for segment in task["segments"]] == [1, 2]
    assert task["snapshot"]["execution_plan"]["segment_order"] == requested_order


def test_running_task_reorders_waiting_segments_before_next_claim(
    tmp_path: Path,
) -> None:
    database, _returns_path, _products_path = _database_with_inputs(tmp_path)
    with database.transaction(immediate=True) as connection:
        connection.execute(
            """
            INSERT INTO tasks(
                id, title, owner_id, dataset_version_id, product_version_id,
                config_version_id, store, status, stage, message,
                snapshot_json, created_at
            ) VALUES (
                'task-order', '顺序任务', 'user-1', 'version-returns',
                'version-products', 'config-1', 'SEEKWAY:US', 'running',
                '语义分析', '正在执行', '{}', '2026-01-01'
            )
            """
        )
        for position, segment_key in enumerate(
            ("segment-a", "segment-b", "segment-c"), start=1
        ):
            connection.execute(
                """
                INSERT INTO task_segments(
                    id, task_id, segment_key, agent_key, agent_family,
                    taxonomy_version, scope_json, status, record_count,
                    unique_comments, progress_total, variants_json,
                    classification_keys_json, execution_order, created_at
                ) VALUES (?, 'task-order', ?, ?, '鞋履智能体', 'taxonomy-v1',
                          '{}', 'queued', 1, 1, 1, '[]', '[]', ?, '2026-01-01')
                """,
                (f"id-{segment_key}", segment_key, segment_key, position),
            )

    worker = TaskWorker(database, NoopRunner(), concurrency=1)
    try:
        first = worker._claim_next_segment()
        assert first == ("task-order", "id-segment-a")

        service = TaskService(database)
        reordered = service.reorder_segments(
            task_id="task-order",
            actor_id="user-1",
            expected_revision=2,
            segment_keys=["segment-c", "segment-b"],
        )
        assert [segment["segment_key"] for segment in reordered["segments"]] == [
            "segment-a",
            "segment-c",
            "segment-b",
        ]
        assert service.events("task-order")[-1]["event_type"] == ("segments_reordered")
        assert list_audit(database, "task", "task-order")[0]["action"] == (
            "reorder_segments"
        )

        with database.transaction(immediate=True) as connection:
            connection.execute(
                "UPDATE task_segments SET status = 'completed' WHERE id = ?",
                (first[1],),
            )
        second = worker._claim_next_segment()
        assert second == ("task-order", "id-segment-c")
    finally:
        worker.stop()


class _FailingConfigService:
    def build_model_settings(self, _config_version_id: str):
        raise AssertionError("模型配置不可用")


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "runtime",
        database_path=tmp_path / "app.db",
        session_days=14,
        task_workers=1,
        bootstrap_email="admin@example.com",
        bootstrap_name="管理员",
        bootstrap_password="test-password-123",
        encryption_key="",
        secure_cookies=False,
    )


def test_block_all_stops_when_unknown_category_exists(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database, _returns_path, _products_path = _database_with_inputs(tmp_path)
    task = _create_task(database, "block_all")
    assert task["status"] == "blocked"
    assert [
        (segment["agent_key"], segment["status"]) for segment in task["segments"]
    ] == [("footwear", "not_started")]

    calls: list[str] = []
    _install_fake_runner(monkeypatch, calls)
    settings = _settings(tmp_path)
    settings.ensure_directories()
    runner = AgentRunner(database, settings, _FakeConfigService())
    assert _run_task_segments(database, runner, str(task["id"])) == []

    result = TaskService(database).get(str(task["id"]))
    assert result["status"] == "blocked"
    assert calls == []
    assert {segment["agent_key"] for segment in result["segments"]} == {"footwear"}


def test_parent_result_failure_keeps_completed_listing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database, _returns_path, _products_path = _database_with_inputs(tmp_path)
    task = _create_task(database, "run_ready")
    completed = next(
        segment for segment in task["segments"] if segment["agent_key"] == "footwear"
    )
    with database.transaction(immediate=True) as connection:
        connection.execute(
            "UPDATE task_segments SET status = 'completed' WHERE id = ?",
            (completed["id"],),
        )
        connection.execute(
            "UPDATE tasks SET status = 'completed' WHERE id = ?",
            (task["id"],),
        )
    runner = AgentRunner(database, _settings(tmp_path), _FailingConfigService())

    def fail_merge(*_args) -> None:
        raise ValueError("模拟批量结果生成失败")

    monkeypatch.setattr(runner, "_build_parent_result", fail_merge)
    runner.finalize_task(str(task["id"]))

    result = TaskService(database).get(str(task["id"]))
    completed_after = next(
        segment for segment in result["segments"] if segment["id"] == completed["id"]
    )
    assert completed_after["status"] == "completed"
    assert result["status"] == "partial"
    assert result["stage"] == "结果汇总异常"


class _FakeConfigService:
    def build_model_settings(self, _config_version_id: str):
        return SimpleNamespace(secondary_model=None, requests_per_minute=60)


def test_product_upload_quality_reports_category_readiness(
    tmp_path: Path,
) -> None:
    product_path = tmp_path / "products.xlsx"
    pd.DataFrame(
        {
            "MSKU": ["SKU-1", "SKU-2"],
            "店铺/站点": ["SEEKWAY:US", "SEEKWAY:US"],
            "Listing": ["L1", "L1"],
            "品类A": ["鞋类", ""],
            "品类B": ["运动鞋", ""],
        }
    ).to_excel(product_path, sheet_name="产品信息汇总表", index=False)

    _rows, _columns, _schema, quality = inspect_file(product_path, "products")

    assert quality["category_ready_rows"] == 1
    assert quality["missing_category_rows"] == 1
    assert quality["category_ready_rate"] == 50.0


def test_product_upload_quality_reports_identity_conflicts(tmp_path: Path) -> None:
    product_path = tmp_path / "products.xlsx"
    pd.DataFrame(
        {
            "MSKU": ["SK002-BLACK-40", "SK002-BLUE-41"],
            "店铺/站点": ["SEEKWAY:US", "SEEKWAY:US"],
            "Listing": ["SK002", "SK002"],
            "产品名称": ["SK001-701 条纹黑", "SK002-703 条纹蓝"],
            "SKU": ["SK001-701 Black 40", "SK002-703 Blue 41"],
            "品类A": ["鞋类", "鞋类"],
            "品类B": ["水鞋", "水鞋"],
        }
    ).to_excel(product_path, sheet_name="产品信息汇总表", index=False)

    _rows, _columns, _schema, quality = inspect_file(product_path, "products")

    assert quality["product_identity_conflict_rows"] == 1
    assert quality["product_identity_conflict_rate"] == 50.0
    assert quality["product_identity_conflict_examples"] == [
        {
            "listing": "SK002",
            "product_name": "SK001-701 条纹黑",
            "product_sku": "SK001-701 Black 40",
        }
    ]


def test_return_upload_quality_reports_text_encoding_anomalies(
    tmp_path: Path,
) -> None:
    returns_path = tmp_path / "returns.csv"
    pd.DataFrame(
        [
            {
                "return-date": "2026-01-01",
                "order-id": "1",
                "sku": "SK002-BLACK-40",
                "asin": "",
                "fnsku": "",
                "product-name": "Water shoes",
                "quantity": "1",
                "reason": "TOO_SMALL",
                "customer-comments": "Didn稚 fit",
            }
        ]
    ).to_csv(returns_path, index=False, encoding="utf-8-sig")

    _rows, _columns, _schema, quality = inspect_file(returns_path, "returns")

    assert quality["text_encoding_anomaly_rows"] == 1
    assert quality["text_encoding_anomaly_rate"] == 100.0
    assert quality["text_encoding_anomaly_examples"] == ["Didn稚 fit"]


def test_missing_category_is_excluded_without_model_call(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database, _returns_path, products_path = _database_with_inputs(tmp_path)
    products = pd.read_excel(
        products_path,
        sheet_name="产品信息汇总表",
        dtype=str,
    ).fillna("")
    products.loc[products["MSKU"].eq("SKU-2"), ["品类A", "品类B"]] = ["", ""]
    with pd.ExcelWriter(products_path, engine="openpyxl") as writer:
        products.to_excel(writer, sheet_name="产品信息汇总表", index=False)

    preflight = TaskService(database).preflight(
        "version-returns",
        "version-products",
        "SEEKWAY:US",
        "L1",
        "config-1",
    )
    assert preflight["excluded_count"] == 1
    assert preflight["blocked_count"] == 0
    assert preflight["category_completion_required"] is True
    assert preflight["missing_category_product_count"] == 1
    assert preflight["missing_category_comment_count"] == 1
    assert preflight["unresolved_product_count"] == 1
    assert preflight["unresolved_products"][0]["issue"] == "missing_category"
    assert [segment["agent_key"] for segment in preflight["segments"]] == ["footwear"]

    with pytest.raises(ValueError, match="品类"):
        _create_task(database, "block_all")


def test_all_missing_categories_complete_without_model_call(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database, _returns_path, products_path = _database_with_inputs(tmp_path)
    products = pd.read_excel(
        products_path,
        sheet_name="产品信息汇总表",
        dtype=str,
    ).fillna("")
    products[["品类A", "品类B"]] = ""
    with pd.ExcelWriter(products_path, engine="openpyxl") as writer:
        products.to_excel(writer, sheet_name="产品信息汇总表", index=False)

    preflight = TaskService(database).preflight(
        "version-returns",
        "version-products",
        "SEEKWAY:US",
        "L1",
        "config-1",
    )
    assert preflight["excluded_count"] == 2
    assert preflight["blocked_count"] == 0
    assert preflight["segments"] == []
    assert preflight["category_completion_required"] is True
    assert preflight["missing_category_product_count"] == 2
    assert preflight["missing_category_comment_count"] == 2

    with pytest.raises(ValueError, match="品类"):
        _create_task(database, "block_all")


def test_run_ready_completes_ready_segment_with_unknown_excluded(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database, _returns_path, _products_path = _database_with_inputs(tmp_path)
    task = _create_task(database, "run_ready")

    def fake_classify_comments(**kwargs) -> PipelineRun:
        selected = kwargs["unique_comments"]
        taxonomy = kwargs["taxonomy"]
        if kwargs["progress"] is not None:
            kwargs["progress"](len(selected), len(selected))
        classifications = {
            str(row.classification_key): ValidatedClassification(
                classification_key=str(row.classification_key),
                semantic_units=[],
                unknown_semantics=[],
                problem_label_codes=[],
                positive_label_codes=[],
                primary_label_codes=[],
                status=ProcessingStatus.AUTO_APPROVED,
                review_reasons=[],
                model_name="fake-model",
                prompt_version="test",
                taxonomy_version=taxonomy.version,
            )
            for row in selected.itertuples(index=False)
        }
        return PipelineRun(
            classifications=classifications,
            usage={"input_tokens": 1},
            usage_by_model={"fake-model": {"input_tokens": 1}},
            cache_hits=0,
            cache_hits_by_model={},
            model_calls=1,
            model_calls_by_model={"fake-model": 1},
            request_metrics={"requests": 1},
            routing={"primary": 1},
        )

    def fake_export_results(output_path: Path, **_kwargs) -> None:
        output_path.touch()

    monkeypatch.setattr(
        "web_backend.agent_runner.classify_comments",
        fake_classify_comments,
    )
    monkeypatch.setattr(
        "web_backend.agent_runner.Sub2APIClient", lambda *_a, **_k: object()
    )
    monkeypatch.setattr("web_backend.agent_runner.export_results", fake_export_results)
    settings = _settings(tmp_path)
    settings.ensure_directories()
    runner = AgentRunner(database, settings, _FakeConfigService())

    _run_task_segments(database, runner, str(task["id"]))

    result = TaskService(database).get(str(task["id"]))
    assert result["status"] == "completed"
    segments = {segment["agent_key"]: segment for segment in result["segments"]}
    assert set(segments) == {"footwear"}
    assert segments["footwear"]["status"] == "completed"
    assert segments["footwear"]["progress_current"] == 1
    assert segments["footwear"]["model_calls"] == 1
    assert segments["footwear"]["cache_hits"] == 0
    assert segments["footwear"]["completed_at"] is not None


def test_run_segment_resumes_from_saved_checkpoint(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database, _returns_path, _products_path = _database_with_inputs(tmp_path)
    task = _create_task(database, "run_ready")
    settings = _settings(tmp_path)
    settings.ensure_directories()
    runner = AgentRunner(database, settings, _FakeConfigService())
    resumed_calls: list[str] = []
    _install_fake_runner(monkeypatch, resumed_calls)

    def interrupt_after_checkpoint(**kwargs) -> PipelineRun:
        selected = kwargs["unique_comments"]
        taxonomy = kwargs["taxonomy"]
        classifications = {
            str(row.classification_key): ValidatedClassification(
                classification_key=str(row.classification_key),
                semantic_units=[],
                unknown_semantics=[],
                problem_label_codes=[],
                positive_label_codes=[],
                primary_label_codes=[],
                status=ProcessingStatus.AUTO_APPROVED,
                review_reasons=[],
                model_name="fake-model",
                prompt_version="test",
                taxonomy_version=taxonomy.version,
            )
            for row in selected.itertuples(index=False)
        }
        run = PipelineRun(
            classifications=classifications,
            usage={"input_tokens": len(selected)},
            usage_by_model={"fake-model": {"input_tokens": len(selected)}},
            cache_hits=0,
            cache_hits_by_model={},
            model_calls=1,
            model_calls_by_model={"fake-model": 1},
            request_metrics={"requests": 1},
            routing={"primary": 1},
        )
        kwargs["checkpoint"](run)
        raise PipelineCancelled("测试中断")

    monkeypatch.setattr(
        "web_backend.agent_runner.classify_comments",
        interrupt_after_checkpoint,
    )
    _run_task_segments(database, runner, str(task["id"]), limit=1)

    interrupted = TaskService(database).get(str(task["id"]))
    interrupted_segment = interrupted["segments"][0]
    assert interrupted["status"] == "queued"
    assert interrupted_segment["status"] == "retry_pending"
    assert interrupted_segment["progress_current"] == 1
    assert Path(str(interrupted_segment["result_json_path"])).exists()

    _install_fake_runner(monkeypatch, resumed_calls)
    _run_task_segments(database, runner, str(task["id"]))

    completed = TaskService(database).get(str(task["id"]))
    completed_segment = completed["segments"][0]
    assert completed["status"] == "completed"
    assert completed_segment["status"] == "completed"
    assert completed_segment["model_calls"] == 1
    assert resumed_calls == []


def test_run_segment_pauses_batch_when_model_service_degrades(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database, _returns_path, _products_path = _database_with_inputs(tmp_path)
    task = _create_task(database, "run_ready")
    settings = _settings(tmp_path)
    settings.ensure_directories()
    runner = AgentRunner(database, settings, _FakeConfigService())
    calls: list[str] = []
    _install_fake_runner(monkeypatch, calls)

    def fail_model_service(**kwargs) -> PipelineRun:
        run = PipelineRun(
            classifications={},
            usage={},
            usage_by_model={},
            cache_hits=0,
            cache_hits_by_model={},
            model_calls=5,
            model_calls_by_model={"fake-model": 5},
            request_metrics={"requests": 5},
            routing={"primary": 5},
            model_failures=5,
        )
        kwargs["on_model_degraded"](run, 5, "模型服务连续失败")
        raise ModelServiceUnavailable("模型服务连续失败", 5)

    monkeypatch.setattr(
        "web_backend.agent_runner.classify_comments",
        fail_model_service,
    )
    _run_task_segments(database, runner, str(task["id"]), limit=1)

    paused = TaskService(database).get(str(task["id"]))
    paused_segment = paused["segments"][0]
    assert paused["status"] == "paused"
    assert paused["stage"] == "模型服务异常"
    assert paused["pause_requested"] is True
    assert paused_segment["status"] == "paused"
    assert paused_segment["model_failures"] == 5
    assert any(
        event["event_type"] == "model_service_paused"
        for event in TaskService(database).events(str(task["id"]))
    )


def test_run_segment_restores_checkpoint_when_result_publish_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database, _returns_path, _products_path = _database_with_inputs(tmp_path)
    task = _create_task(database, "run_ready")
    settings = _settings(tmp_path)
    settings.ensure_directories()
    runner = AgentRunner(database, settings, _FakeConfigService())
    calls: list[str] = []
    _install_fake_runner(monkeypatch, calls)

    def fail_result_publish(**kwargs) -> None:
        Path(str(kwargs["checkpoint_path"])).unlink()
        raise ResultPublicationError("模拟结果发布失败")

    monkeypatch.setattr(
        runner.result_service,
        "publish_v1",
        fail_result_publish,
    )
    _run_task_segments(database, runner, str(task["id"]))

    result = TaskService(database).get(str(task["id"]))
    segment = result["segments"][0]
    checkpoint_path = Path(str(segment["result_json_path"]))
    checkpoint = runner._load_checkpoint(checkpoint_path)
    assert segment["status"] == "completed"
    assert segment["result_publish_status"] == "failed"
    assert segment["result_publish_error"] == "模拟结果发布失败"
    assert segment["model_calls"] == 1
    assert checkpoint_path.exists()
    assert len(checkpoint) == segment["progress_total"]
    assert any(
        event["event_type"] == "segment_classified_publish_failed"
        for event in TaskService(database).events(str(task["id"]))
    )


def test_plan_hash_changes_with_model_configuration() -> None:
    unique_comments = pd.DataFrame(
        [
            {
                "classification_key": "key",
                "category_a": "水鞋",
                "category_b": "薄底水鞋",
            }
        ]
    )
    records = unique_comments[["classification_key"]].assign(has_text_evidence=True)
    dataset = ReturnDataset(records, unique_comments, frozenset())
    registry = load_capability_registry(
        PROJECT_ROOT / "config/category_capabilities.json"
    )
    plan = build_category_execution_plan(dataset, registry)

    first = plan.with_hash({"config": {"primary_model": "model-a"}})
    second = plan.with_hash({"config": {"primary_model": "model-b"}})

    assert first["plan_hash"] != second["plan_hash"]


def test_blocked_task_replans_after_product_category_is_completed(
    tmp_path: Path,
) -> None:
    database, _returns_path, products_path = _database_with_inputs(tmp_path)
    task = _create_task(database, "block_all")
    blocked = TaskService(database).get(str(task["id"]))
    new_product_version = _add_resolved_product_version(database, products_path)
    service = TaskService(database)

    preflight = service.replan_preflight(
        str(task["id"]),
        new_product_version,
    )
    replanned = service.replan(
        task_id=str(task["id"]),
        actor_id="user-1",
        product_version_id=new_product_version,
        expected_revision=int(blocked["revision"]),
        plan_hash=str(preflight["plan_hash"]),
        unresolved_policy="run_ready",
        reason="已经补充 SKU-2 的儿童眼镜品类",
    )

    assert preflight["blocked_count"] == 0
    assert replanned["status"] == "queued"
    assert replanned["product_version_id"] == new_product_version
    assert replanned["snapshot"]["returns"] == blocked["snapshot"]["returns"]
    assert replanned["snapshot"]["config"] == blocked["snapshot"]["config"]
    assert replanned["snapshot"]["products"] == {
        "dataset_id": "dataset-products",
        "version_id": new_product_version,
        "version": 2,
        "name": "products",
        "sha256": "hash-products-2",
    }
    assert (
        replanned["snapshot"]["execution_plan"]["plan_hash"] == preflight["plan_hash"]
    )
    assert replanned["snapshot"]["execution_plan"]["unresolved_policy"] == ("run_ready")
    assert {segment["agent_key"] for segment in replanned["segments"]} == {
        "footwear",
        "eyewear",
    }
    assert (
        replanned["snapshot"]["execution_plan_history"][0]["plan"]
        == blocked["snapshot"]["execution_plan"]
    )
    assert replanned["snapshot"]["execution_plan_history"][0]["reason"] == (
        "已经补充 SKU-2 的儿童眼镜品类"
    )
    event = service.events(str(task["id"]))[-1]
    assert event["event_type"] == "replanned"
    assert event["data"]["reason"] == "已经补充 SKU-2 的儿童眼镜品类"
    audit = list_audit(database, "task", str(task["id"]))[0]
    assert audit["action"] == "replan"
    assert audit["after"]["reason"] == "已经补充 SKU-2 的儿童眼镜品类"


def test_replan_rejects_stale_revision_and_hash(tmp_path: Path) -> None:
    database, _returns_path, products_path = _database_with_inputs(tmp_path)
    task = _create_task(database, "block_all")
    blocked = TaskService(database).get(str(task["id"]))
    new_product_version = _add_resolved_product_version(database, products_path)
    service = TaskService(database)
    preflight = service.replan_preflight(str(task["id"]), new_product_version)

    with pytest.raises(TaskRevisionConflict):
        service.replan(
            task_id=str(task["id"]),
            actor_id="user-1",
            product_version_id=new_product_version,
            expected_revision=int(blocked["revision"]) - 1,
            plan_hash=str(preflight["plan_hash"]),
            unresolved_policy="run_ready",
            reason="使用了过期页面",
        )
    with pytest.raises(TaskPlanConflict):
        service.replan(
            task_id=str(task["id"]),
            actor_id="user-1",
            product_version_id=new_product_version,
            expected_revision=int(blocked["revision"]),
            plan_hash="0" * 64,
            unresolved_policy="run_ready",
            reason="使用了过期计划",
        )


def test_replan_runs_only_failed_segment_and_keeps_completed_result(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database, _returns_path, products_path = _database_with_inputs(tmp_path)
    product_version = _add_resolved_product_version(database, products_path)
    service = TaskService(database)
    initial_plan = service.preflight(
        "version-returns",
        product_version,
        "SEEKWAY:US",
        "L1",
        "config-1",
    )
    segment_order = [
        str(segment["segment_key"])
        for agent_key in ("footwear", "eyewear")
        for segment in initial_plan["segments"]
        if segment["agent_key"] == agent_key
    ]
    task = service.create(
        actor_id="user-1",
        title="片段失败后重新规划",
        dataset_version_id="version-returns",
        product_version_id=product_version,
        store="SEEKWAY:US",
        listing="L1",
        config_version_id="config-1",
        plan_hash=str(initial_plan["plan_hash"]),
        unresolved_policy="run_ready",
        segment_order=segment_order,
    )
    first_calls: list[str] = []
    _install_fake_runner(
        monkeypatch,
        first_calls,
        failing_taxonomy="eyewear-2026-08-10-v1",
    )
    settings = _settings(tmp_path)
    settings.ensure_directories()
    runner = AgentRunner(database, settings, _FakeConfigService())
    _run_task_segments(database, runner, str(task["id"]))
    partial = service.get(str(task["id"]))
    assert partial["status"] == "partial"
    assert first_calls == [
        "water-shoes-2026-08-05-v1",
        "eyewear-2026-08-10-v1",
    ]
    partial_segments = {
        segment["agent_key"]: segment for segment in partial["segments"]
    }
    assert partial_segments["footwear"]["status"] == "completed"
    assert partial_segments["eyewear"]["status"] == "failed"

    preflight = service.replan_preflight(str(task["id"]), product_version)
    replanned = service.replan(
        task_id=str(task["id"]),
        actor_id="user-1",
        product_version_id=product_version,
        expected_revision=int(partial["revision"]),
        plan_hash=str(preflight["plan_hash"]),
        unresolved_policy="run_ready",
        reason="眼镜片段失败后重新规划",
    )
    second_calls: list[str] = []
    _install_fake_runner(monkeypatch, second_calls)
    _run_task_segments(database, runner, str(replanned["id"]))

    completed = service.get(str(task["id"]))
    assert completed["status"] == "completed"
    assert second_calls == ["eyewear-2026-08-10-v1"]
    segments = {segment["agent_key"]: segment for segment in completed["segments"]}
    assert segments["footwear"]["model_calls"] == 1
    assert segments["eyewear"]["model_calls"] == 1


def test_failed_segment_can_retry_without_repeating_completed_segment(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database, _returns_path, products_path = _database_with_inputs(tmp_path)
    new_product_version = _add_resolved_product_version(database, products_path)
    service = TaskService(database)
    preflight = service.preflight(
        "version-returns",
        new_product_version,
        "SEEKWAY:US",
        "L1",
        "config-1",
    )
    task = service.create(
        actor_id="user-1",
        title="失败片段重试",
        dataset_version_id="version-returns",
        product_version_id=new_product_version,
        store="SEEKWAY:US",
        listing="L1",
        config_version_id="config-1",
        plan_hash=str(preflight["plan_hash"]),
        unresolved_policy="run_ready",
    )
    first_calls: list[str] = []
    _install_fake_runner(
        monkeypatch,
        first_calls,
        failing_taxonomy="water-shoes-2026-08-05-v1",
    )
    settings = _settings(tmp_path)
    settings.ensure_directories()
    runner = AgentRunner(database, settings, _FakeConfigService())
    _run_task_segments(database, runner, str(task["id"]))
    partial = service.get(str(task["id"]))
    segments = {segment["agent_key"]: segment for segment in partial["segments"]}
    assert partial["status"] == "partial"
    assert segments["eyewear"]["status"] == "completed"
    assert segments["footwear"]["status"] == "failed"

    retried = service.retry_segment(
        task_id=str(task["id"]),
        segment_key=str(segments["footwear"]["segment_key"]),
        actor_id="user-1",
        expected_revision=int(partial["revision"]),
        reason="模型临时错误已经恢复",
    )
    retry_calls: list[str] = []
    _install_fake_runner(monkeypatch, retry_calls)
    _run_task_segments(database, runner, str(retried["id"]))

    completed = service.get(str(task["id"]))
    assert completed["status"] == "completed"
    assert retry_calls == ["water-shoes-2026-08-05-v1"]
    event = next(
        value
        for value in service.events(str(task["id"]))
        if value["event_type"] == "segment_retry"
    )
    assert event["event_type"] == "segment_retry"
    assert event["data"]["reason"] == "模型临时错误已经恢复"
    audit = list_audit(database, "task", str(task["id"]))[0]
    assert audit["action"] == "segment_retry"


def test_replan_rebuilds_failed_segment_when_its_scope_changes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database, _returns_path, products_path = _database_with_inputs(tmp_path)
    all_footwear_version = _add_product_version(
        database,
        products_path,
        version=2,
        category_a="水鞋",
        category_b="薄底水鞋",
    )
    service = TaskService(database)
    preflight = service.preflight(
        "version-returns",
        all_footwear_version,
        "SEEKWAY:US",
        "L1",
        "config-1",
    )
    task = service.create(
        actor_id="user-1",
        title="失败片段范围变化",
        dataset_version_id="version-returns",
        product_version_id=all_footwear_version,
        store="SEEKWAY:US",
        listing="L1",
        config_version_id="config-1",
        plan_hash=str(preflight["plan_hash"]),
        unresolved_policy="run_ready",
    )
    failed_calls: list[str] = []
    _install_fake_runner(
        monkeypatch,
        failed_calls,
        failing_taxonomy="water-shoes-2026-08-05-v1",
    )
    settings = _settings(tmp_path)
    settings.ensure_directories()
    runner = AgentRunner(database, settings, _FakeConfigService())
    _run_task_segments(database, runner, str(task["id"]))
    failed_task = service.get(str(task["id"]))
    assert failed_task["status"] == "blocked"
    failed_segment = failed_task["segments"][0]
    assert failed_segment["status"] == "failed"
    with database.connect() as connection:
        old_failed_keys = set(
            json.loads(
                connection.execute(
                    """
                    SELECT classification_keys_json FROM task_segments
                    WHERE id = ?
                    """,
                    (failed_segment["id"],),
                ).fetchone()["classification_keys_json"]
            )
        )
    assert len(old_failed_keys) == 2

    split_version = _add_product_version(
        database,
        products_path,
        version=3,
        category_a="眼镜",
        category_b="儿童眼镜",
    )
    replan_preflight = service.replan_preflight(
        str(task["id"]),
        split_version,
    )
    replanned = service.replan(
        task_id=str(task["id"]),
        actor_id="user-1",
        product_version_id=split_version,
        expected_revision=int(failed_task["revision"]),
        plan_hash=str(replan_preflight["plan_hash"]),
        unresolved_policy="run_ready",
        reason="将 SKU-2 从鞋履调整为儿童眼镜",
    )
    prepared = service.plan_service.prepare(
        dataset_version_id="version-returns",
        product_version_id=split_version,
        store="SEEKWAY:US",
        listing="L1",
        config_version_id="config-1",
    )
    expected_keys = prepared.execution_plan.classification_keys_by_segment(
        prepared.dataset
    )
    with database.connect() as connection:
        rows = connection.execute(
            """
            SELECT id, agent_key, status, classification_keys_json
            FROM task_segments WHERE task_id = ?
            """,
            (task["id"],),
        ).fetchall()
    actual_keys = {
        str(row["agent_key"]): set(json.loads(row["classification_keys_json"]))
        for row in rows
    }
    assert failed_segment["id"] not in {str(row["id"]) for row in rows}
    assert actual_keys == {
        agent_key: set(keys) for agent_key, keys in expected_keys.items()
    }
    assert actual_keys["footwear"] < old_failed_keys
    assert {str(row["status"]) for row in rows} == {"queued"}

    retry_calls: list[str] = []
    _install_fake_runner(monkeypatch, retry_calls)
    _run_task_segments(database, runner, str(replanned["id"]))

    completed = service.get(str(task["id"]))
    assert completed["status"] == "completed"
    assert set(retry_calls) == {
        "eyewear-2026-08-10-v1",
        "water-shoes-2026-08-05-v1",
    }
    checkpoint = json.loads(
        Path(str(completed["results_json_path"])).read_text(encoding="utf-8")
    )
    expected_result_keys = set().union(*actual_keys.values())
    assert set(checkpoint) == expected_result_keys
    assert len(checkpoint) == 2


def test_excluded_unknown_has_no_segment_and_completed_cannot_retry(
    tmp_path: Path,
) -> None:
    database, _returns_path, _products_path = _database_with_inputs(tmp_path)
    task = _create_task(database, "run_ready")
    service = TaskService(database)
    assert {segment["agent_key"] for segment in task["segments"]} == {"footwear"}
    with pytest.raises(ValueError, match="片段不存在"):
        service.retry_segment(
            task_id=str(task["id"]),
            segment_key="unknown",
            actor_id="user-1",
            expected_revision=int(task["revision"]),
            reason="尝试重试未创建的未知品类片段",
        )
    footwear = next(
        segment for segment in task["segments"] if segment["agent_key"] == "footwear"
    )
    with database.transaction(immediate=True) as connection:
        connection.execute(
            "UPDATE tasks SET status = 'partial' WHERE id = ?",
            (task["id"],),
        )
        connection.execute(
            "UPDATE task_segments SET status = 'completed' WHERE id = ?",
            (footwear["id"],),
        )
    with pytest.raises(ValueError, match="不允许重试"):
        service.retry_segment(
            task_id=str(task["id"]),
            segment_key=str(footwear["segment_key"]),
            actor_id="user-1",
            expected_revision=int(task["revision"]),
            reason="尝试重复运行已完成片段",
        )


def test_worker_recovers_only_running_segments(tmp_path: Path) -> None:
    database, _returns_path, products_path = _database_with_inputs(tmp_path)
    new_product_version = _add_resolved_product_version(database, products_path)
    service = TaskService(database)
    preflight = service.preflight(
        "version-returns",
        new_product_version,
        "SEEKWAY:US",
        "L1",
        "config-1",
    )
    task = service.create(
        actor_id="user-1",
        title="重启恢复",
        dataset_version_id="version-returns",
        product_version_id=new_product_version,
        store="SEEKWAY:US",
        listing="L1",
        config_version_id="config-1",
        plan_hash=str(preflight["plan_hash"]),
        unresolved_policy="run_ready",
    )
    segments = {segment["agent_key"]: segment for segment in task["segments"]}
    with database.transaction(immediate=True) as connection:
        connection.execute(
            "UPDATE tasks SET status = 'running' WHERE id = ?",
            (task["id"],),
        )
        connection.execute(
            "UPDATE task_segments SET status = 'completed' WHERE id = ?",
            (segments["eyewear"]["id"],),
        )
        connection.execute(
            "UPDATE task_segments SET status = 'running' WHERE id = ?",
            (segments["footwear"]["id"],),
        )
    worker = TaskWorker(database, NoopRunner(), concurrency=1)

    worker._recover_interrupted_tasks()

    recovered = service.get(str(task["id"]))
    recovered_segments = {
        segment["agent_key"]: segment["status"] for segment in recovered["segments"]
    }
    assert recovered["status"] == "queued"
    assert recovered_segments == {
        "eyewear": "completed",
        "footwear": "retry_pending",
    }
    worker.stop()


def test_cancelled_task_delivers_completed_listing_and_resumes_remaining(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database, _returns_path, products_path = _database_with_inputs(tmp_path)
    product_version = _add_resolved_product_version(database, products_path)
    service = TaskService(database)
    preflight = service.preflight(
        "version-returns",
        product_version,
        "SEEKWAY:US",
        "L1",
        "config-1",
    )
    segment_order = [
        str(segment["segment_key"])
        for agent_key in ("footwear", "eyewear")
        for segment in preflight["segments"]
        if segment["agent_key"] == agent_key
    ]
    task = service.create(
        actor_id="user-1",
        title="取消后继续",
        dataset_version_id="version-returns",
        product_version_id=product_version,
        store="SEEKWAY:US",
        listing="L1",
        config_version_id="config-1",
        plan_hash=str(preflight["plan_hash"]),
        unresolved_policy="run_ready",
        segment_order=segment_order,
    )
    settings = _settings(tmp_path)
    settings.ensure_directories()
    runner = AgentRunner(database, settings, _FakeConfigService())
    first_calls: list[str] = []
    _install_fake_runner(monkeypatch, first_calls)
    claimed = _run_task_segments(database, runner, str(task["id"]), limit=1)
    assert len(claimed) == 1
    assert first_calls == ["water-shoes-2026-08-05-v1"]

    after_first = service.get(str(task["id"]))
    service.cancel(
        task_id=str(task["id"]),
        actor_id="user-1",
        note="用户取消任务",
        expected_revision=int(after_first["revision"]),
    )
    _run_task_segments(database, runner, str(task["id"]))

    cancelled = service.get(str(task["id"]))
    cancelled_segments = {
        segment["agent_key"]: segment for segment in cancelled["segments"]
    }
    assert cancelled["status"] == "cancelled"
    assert cancelled["stage"] == "已取消"
    assert cancelled["metrics"]["partial_result"] is True
    assert Path(str(cancelled["result_file_path"])).exists()
    assert cancelled_segments["footwear"]["status"] == "completed"
    assert cancelled_segments["eyewear"]["status"] == "cancelled"
    assert cancelled["metrics"]["delivered_records"] == 1
    with pytest.raises(TaskRevisionConflict, match="已被他人修改"):
        service.resume(
            task_id=str(task["id"]),
            actor_id="user-1",
            expected_revision=int(cancelled["revision"]) - 1,
            note="使用过期页面继续",
        )

    resumed = service.resume(
        task_id=str(task["id"]),
        actor_id="user-1",
        expected_revision=int(cancelled["revision"]),
        note="继续剩余 Listing",
    )
    resumed_segments = {
        segment["agent_key"]: segment for segment in resumed["segments"]
    }
    assert resumed["id"] == task["id"]
    assert resumed["status"] == "queued"
    assert resumed_segments["footwear"]["status"] == "completed"
    assert resumed_segments["eyewear"]["status"] == "retry_pending"

    resume_calls: list[str] = []
    _install_fake_runner(monkeypatch, resume_calls)
    _run_task_segments(database, runner, str(task["id"]))

    completed = service.get(str(task["id"]))
    assert completed["status"] == "completed"
    assert resume_calls == ["eyewear-2026-08-10-v1"]
    assert any(
        event["event_type"] == "resumed" and event["data"]["note"] == "继续剩余 Listing"
        for event in service.events(str(task["id"]))
    )
    assert any(
        item["action"] == "resume"
        for item in list_audit(database, "task", str(task["id"]))
    )


def test_analysis_reads_a_completed_listing_before_parent_finishes(
    tmp_path: Path,
) -> None:
    database, returns_path, products_path = _database_with_inputs(tmp_path)
    task = _create_task(database, "run_ready")
    with database.connect() as connection:
        segment = connection.execute(
            """
            SELECT * FROM task_segments
            WHERE task_id = ? AND agent_key = 'footwear'
            """,
            (task["id"],),
        ).fetchone()
    assert segment is not None

    dataset = load_return_dataset(
        returns_path,
        products_path,
        store="SEEKWAY:US",
        listing="L1",
    )
    key = str(json.loads(segment["classification_keys_json"])[0])
    result = ValidatedClassification(
        classification_key=key,
        semantic_units=[],
        unknown_semantics=[],
        problem_label_codes=[],
        positive_label_codes=[],
        primary_label_codes=[],
        status=ProcessingStatus.AUTO_APPROVED,
        review_reasons=[],
        model_name="fake-model",
        prompt_version="test",
        taxonomy_version=str(segment["taxonomy_version"]),
    )
    registry = load_capability_registry(
        PROJECT_ROOT / "config" / "category_capabilities.json"
    )
    capability = next(item for item in registry.capabilities if item.key == "footwear")
    output_path = tmp_path / "listing-l1-analysis.xlsx"
    export_results(
        output_path=output_path,
        dataset=AgentRunner._subset_dataset(dataset, {key}),
        results={key: result},
        taxonomy=registry.load_taxonomy(capability),
    )
    with database.transaction(immediate=True) as connection:
        connection.execute(
            "UPDATE tasks SET status = 'running', result_file_path = NULL WHERE id = ?",
            (task["id"],),
        )
        connection.execute(
            """
            UPDATE task_segments
            SET status = 'completed', result_file_path = ?, result_version = 1,
                completed_at = '2026-08-12', scope_json = ?
            WHERE id = ?
            """,
            (
                str(output_path),
                json.dumps({"store": "SEEKWAY:US", "listing": "L1"}),
                segment["id"],
            ),
        )

    analysis = AnalysisService(database).get(
        str(task["id"]),
        AnalysisFilters(listing="L1"),
    )
    assert analysis["scope"]["total_records"] == 1
    assert analysis["task"]["listing"] == "L1"
    assert analysis["task"]["delivery_scope"] == "segment"
    assert analysis["quality_gate"]["status"] == "unusable"
    assert analysis["quality_gate"]["labeled_records"] == 0
    with pytest.raises(ValueError, match="尚未生成"):
        AnalysisService(database).get(
            str(task["id"]),
            AnalysisFilters(listing="L2"),
        )


def test_manual_review_without_semantics_is_a_segment_quality_error() -> None:
    result = ValidatedClassification(
        classification_key="key-1",
        semantic_units=[],
        unknown_semantics=[],
        problem_label_codes=[],
        positive_label_codes=[],
        primary_label_codes=[],
        status=ProcessingStatus.MANUAL_REVIEW,
        review_reasons=["证据不在原评论中"],
        model_name="fake-model",
        prompt_version="test",
        taxonomy_version="taxonomy-v1",
    )

    assert AgentRunner._results_have_quality_errors({"key-1": result}) is True
    approved = result.model_copy(
        update={"status": ProcessingStatus.AUTO_APPROVED, "review_reasons": []}
    )
    assert AgentRunner._results_have_quality_errors({"key-1": approved}) is False


def test_cancelled_queued_task_marks_waiting_segments_not_started(
    tmp_path: Path,
) -> None:
    database, _returns_path, _products_path = _database_with_inputs(tmp_path)
    service = TaskService(database)
    task = _create_task(database, "run_ready")

    cancelled = service.cancel(
        task_id=str(task["id"]),
        actor_id="user-1",
        note="调整执行安排",
        expected_revision=int(task["revision"]),
    )

    assert cancelled["status"] == "cancelled"
    assert all(segment["status"] != "queued" for segment in cancelled["segments"])
    assert any(segment["status"] == "cancelled" for segment in cancelled["segments"])


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        (["completed", "completed"], "completed"),
        (["completed", "blocked"], "partial"),
        (["completed_with_errors"], "partial"),
        (["blocked", "failed", "not_started"], "blocked"),
        (["completed", "retry_pending"], "queued"),
    ],
)
def test_parent_status_is_summarized_from_segments(
    statuses: list[str],
    expected: str,
) -> None:
    assert summarize_task_status(statuses) == expected


def test_listing_controls_and_parallelism_are_audited(tmp_path: Path) -> None:
    database, _returns_path, _products_path = _database_with_inputs(tmp_path)
    service = TaskService(database)
    task = _create_task(database, "run_ready")
    segment = next(value for value in task["segments"] if value["status"] == "queued")

    changed = service.set_parallelism(
        task_id=str(task["id"]),
        actor_id="user-1",
        expected_revision=int(task["revision"]),
        max_parallel_segments=1,
    )
    assert changed["max_parallel_segments"] == 1

    paused = service.segment_action(
        task_id=str(task["id"]),
        segment_key=str(segment["segment_key"]),
        action="pause",
        actor_id="user-1",
        expected_revision=int(changed["revision"]),
    )
    paused_segment = next(
        value
        for value in paused["segments"]
        if value["segment_key"] == segment["segment_key"]
    )
    assert paused_segment["status"] == "paused"
    assert paused_segment["wait_reason"] == "已由用户暂停"

    resumed = service.segment_action(
        task_id=str(task["id"]),
        segment_key=str(segment["segment_key"]),
        action="resume",
        actor_id="user-1",
        expected_revision=int(paused["revision"]),
    )
    resumed_segment = next(
        value
        for value in resumed["segments"]
        if value["segment_key"] == segment["segment_key"]
    )
    assert resumed_segment["status"] == "queued"
    assert resumed_segment["wait_reason"].startswith("我的队列第")

    cancelled = service.segment_action(
        task_id=str(task["id"]),
        segment_key=str(segment["segment_key"]),
        action="cancel",
        actor_id="user-1",
        expected_revision=int(resumed["revision"]),
        note="该 Listing 不再需要分析",
    )
    cancelled_segment = next(
        value
        for value in cancelled["segments"]
        if value["segment_key"] == segment["segment_key"]
    )
    assert cancelled_segment["status"] == "cancelled"
    actions = {item["action"] for item in list_audit(database, "task", str(task["id"]))}
    assert {
        "parallelism_changed",
        "segment_pause",
        "segment_resume",
        "segment_cancel",
    }.issubset(actions)


def test_resuming_listing_releases_batch_pause_gate(tmp_path: Path) -> None:
    database, _returns_path, _products_path = _database_with_inputs(tmp_path)
    service = TaskService(database)
    task = _create_task(database, "run_ready")
    ready_segments = [
        value for value in task["segments"] if value["status"] == "queued"
    ]
    selected = ready_segments[0]
    with database.transaction(immediate=True) as connection:
        connection.execute(
            "UPDATE task_segments SET status = 'paused' WHERE task_id = ?",
            (task["id"],),
        )
        connection.execute(
            """
            UPDATE tasks
            SET status = 'paused', stage = '已暂停', pause_requested = 1,
                revision = revision + 1
            WHERE id = ?
            """,
            (task["id"],),
        )
    paused = service.get(str(task["id"]))

    resumed = service.segment_action(
        task_id=str(task["id"]),
        segment_key=str(selected["segment_key"]),
        action="resume",
        actor_id="user-1",
        expected_revision=int(paused["revision"]),
    )

    assert resumed["pause_requested"] == 0
    statuses = {value["segment_key"]: value["status"] for value in resumed["segments"]}
    assert statuses[selected["segment_key"]] == "queued"
    assert all(
        status in {"queued", "paused", "blocked"} for status in statuses.values()
    )
    worker = TaskWorker(database, NoopRunner(), concurrency=1)
    claimed = worker._claim_next_segment()
    worker.stop()
    assert claimed == (task["id"], selected["id"])


def test_running_listing_pause_recovers_as_paused(tmp_path: Path) -> None:
    database, _returns_path, _products_path = _database_with_inputs(tmp_path)
    service = TaskService(database)
    task = _create_task(database, "run_ready")
    segment = next(value for value in task["segments"] if value["status"] == "queued")
    with database.transaction(immediate=True) as connection:
        connection.execute(
            "UPDATE tasks SET status = 'running' WHERE id = ?",
            (task["id"],),
        )
        connection.execute(
            "UPDATE task_segments SET status = 'running' WHERE id = ?",
            (segment["id"],),
        )
    running_task = service.get(str(task["id"]))

    requested = service.segment_action(
        task_id=str(task["id"]),
        segment_key=str(segment["segment_key"]),
        action="pause",
        actor_id="user-1",
        expected_revision=int(running_task["revision"]),
    )
    requested_segment = next(
        value
        for value in requested["segments"]
        if value["segment_key"] == segment["segment_key"]
    )
    assert requested_segment["status"] == "running"
    assert requested_segment["display_status"] == "pause_pending"

    worker = TaskWorker(database, NoopRunner(), concurrency=1)
    worker._recover_interrupted_tasks()
    recovered = service.get(str(task["id"]))
    recovered_segment = next(
        value
        for value in recovered["segments"]
        if value["segment_key"] == segment["segment_key"]
    )
    assert recovered_segment["status"] == "paused"
    worker.stop()


def test_restart_finishes_pending_batch_cancel(tmp_path: Path) -> None:
    database, _returns_path, _products_path = _database_with_inputs(tmp_path)
    service = TaskService(database)
    task = _create_task(database, "run_ready")
    with database.transaction(immediate=True) as connection:
        connection.execute(
            "UPDATE tasks SET cancel_requested = 1 WHERE id = ?",
            (task["id"],),
        )

    worker = TaskWorker(database, NoopRunner(), concurrency=1)
    worker._recover_interrupted_tasks()

    recovered = service.get(str(task["id"]))
    assert recovered["status"] == "cancelled"
    assert all(segment["status"] == "cancelled" for segment in recovered["segments"])
    assert worker._claim_next_segment() is None
    worker.stop()


def test_replan_api_maps_stale_revision_and_hash_to_409() -> None:
    class ConflictService:
        def replan(self, **kwargs):
            if kwargs["expected_revision"] == 1:
                raise TaskRevisionConflict("任务已被他人修改")
            raise TaskPlanConflict("执行计划已变化")

    app = FastAPI()
    app.include_router(
        create_task_router(
            task_service=ConflictService(),
            analysis_service=object(),
            current_user=lambda: {"id": "user-1"},
        )
    )
    payload = {
        "product_version_id": "products-v2",
        "expected_revision": 1,
        "plan_hash": "a" * 64,
        "unresolved_policy": "run_ready",
        "reason": "补充商品品类",
    }
    with TestClient(app) as client:
        revision_response = client.post(
            "/api/tasks/task-1/replan",
            json=payload,
        )
        payload["expected_revision"] = 2
        hash_response = client.post(
            "/api/tasks/task-1/replan",
            json=payload,
        )

    assert revision_response.status_code == 409
    assert hash_response.status_code == 409
