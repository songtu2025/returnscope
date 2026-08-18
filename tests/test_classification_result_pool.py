from __future__ import annotations

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from return_semantics.capabilities import load_capability_registry
from return_semantics.data import load_return_dataset, load_return_dataset_auto
from return_semantics.pipeline import PipelineRun
from return_semantics.schemas import ProcessingStatus, ValidatedClassification
from return_semantics.task_plan import build_category_execution_plan
from web_backend.agent_runner import AgentRunner
from web_backend.analysis_service import AnalysisService
from web_backend.classification_result_service import (
    ClassificationResultService,
    ResultPublicationConflict,
    ResultPublicationError,
)
from web_backend.common import json_text, json_value
from web_backend.database import Database
from web_backend.routers.classification_results import (
    create_classification_result_router,
)
from web_backend.routers.tasks import create_task_router
from web_backend.settings import PROJECT_ROOT
from web_backend.task_service import (
    TaskResultPublishConflict,
    TaskService,
)


def _seed_result_context(tmp_path: Path) -> SimpleNamespace:
    returns_path = tmp_path / "returns.csv"
    products_path = tmp_path / "products.xlsx"
    pd.DataFrame(
        [
            {
                "return-date": "2026-08-01",
                "order-id": "ORDER-DUP",
                "sku": "SOURCE-MSKU-1",
                "asin": "ASIN-1",
                "fnsku": "FNSKU-1",
                "product-name": "退货文件中的错误产品名",
                "quantity": "1",
                "reason": "APPAREL_TOO_SMALL",
                "customer-comments": "Too small",
                "店铺/站点": "SEEKWAY:US",
            },
            {
                "return-date": "2026-08-02",
                "order-id": "ORDER-DUP",
                "sku": "SOURCE-MSKU-1",
                "asin": "ASIN-1",
                "fnsku": "FNSKU-1",
                "product-name": "另一个错误产品名",
                "quantity": "1",
                "reason": "APPAREL_TOO_SMALL",
                "customer-comments": "Too small",
                "店铺/站点": "SEEKWAY:US",
            },
            {
                "return-date": "2026-08-03",
                "order-id": "ORDER-OTHER",
                "sku": "SOURCE-MSKU-1",
                "asin": "ASIN-1",
                "fnsku": "FNSKU-1",
                "product-name": "仍然错误的产品名",
                "quantity": "1",
                "reason": "APPAREL_TOO_SMALL",
                "customer-comments": "Too small",
                "店铺/站点": "SEEKWAY:US",
            },
        ]
    ).to_csv(returns_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(
        [
            {
                "MSKU": "SOURCE-MSKU-1",
                "店铺/站点": "SEEKWAY:US",
                "产品名称": "产品表权威名称",
                "SKU": "PRODUCT-SKU-1",
                "品类A": "水鞋",
                "品类B": "薄底水鞋",
                "Listing": "L1",
            }
        ]
    ).to_excel(products_path, sheet_name="产品信息汇总表", index=False)

    database = Database(tmp_path / "app.db")
    database.initialize()
    now = "2026-08-12T00:00:00+00:00"
    with database.transaction(immediate=True) as connection:
        connection.execute(
            """
            INSERT INTO users(id, email, display_name, password_hash, created_at)
            VALUES ('user-1', 'one@example.com', '用户一', 'hash', ?)
            """,
            (now,),
        )
        for dataset_id, name, kind in (
            ("dataset-returns", "退货数据", "returns"),
            ("dataset-products", "产品信息", "products"),
        ):
            connection.execute(
                """
                INSERT INTO datasets(
                    id, name, kind, current_version, created_by,
                    created_at, updated_at
                ) VALUES (?, ?, ?, 1, 'user-1', ?, ?)
                """,
                (dataset_id, name, kind, now, now),
            )
        connection.execute(
            """
            INSERT INTO dataset_versions(
                id, dataset_id, version, file_path, original_name,
                content_type, size_bytes, sha256, row_count, column_count,
                schema_json, quality_json, created_by, created_at
            ) VALUES ('version-returns', 'dataset-returns', 1, ?, 'returns.csv',
                      'text/csv', 1, 'returns-sha', 3, 10, '[]', '{}',
                      'user-1', ?)
            """,
            (str(returns_path), now),
        )
        connection.execute(
            """
            INSERT INTO dataset_versions(
                id, dataset_id, version, file_path, original_name,
                content_type, size_bytes, sha256, row_count, column_count,
                schema_json, quality_json, created_by, created_at
            ) VALUES ('version-products', 'dataset-products', 1, ?, 'products.xlsx',
                      'application/xlsx', 1, 'products-sha', 1, 7, '[]', '{}',
                      'user-1', ?)
            """,
            (str(products_path), now),
        )
        connection.execute(
            """
            INSERT INTO api_connections(
                id, name, provider, active_version_id,
                created_by, created_at, updated_at
            ) VALUES ('connection-1', '测试连接', 'responses-compatible',
                      'config-1', 'user-1', ?, ?)
            """,
            (now, now),
        )
        connection.execute(
            """
            INSERT INTO api_config_versions(
                id, connection_id, version, base_url, api_key_ciphertext,
                primary_model, primary_effort, published_at,
                created_by, created_at
            ) VALUES ('config-1', 'connection-1', 1, 'http://localhost', 'secret',
                      'model-primary', 'medium', ?, 'user-1', ?)
            """,
            (now, now),
        )
        connection.execute(
            """
            INSERT INTO tasks(
                id, title, owner_id, dataset_version_id, product_version_id,
                config_version_id, store, listing, status, stage,
                snapshot_json, created_at
            ) VALUES ('task-1', '测试任务', 'user-1', 'version-returns',
                      'version-products', 'config-1', 'SEEKWAY:US', 'L1',
                      'running', '语义分析', '{}', ?)
            """,
            (now,),
        )
        connection.execute(
            """
            INSERT INTO task_segments(
                id, task_id, segment_key, agent_key, agent_family,
                logic_version, taxonomy_version, model_policy_version,
                claims_version, scope_json, status, record_count,
                unique_comments, progress_total, classification_keys_json,
                created_at
            ) VALUES ('segment-1', 'task-1', 'footwear', 'footwear',
                      '鞋履智能体', 'logic-v1', 'taxonomy-v1', 'policy-v1',
                      'no-claims-v1', ?, 'running', 3, 1, 1, '[]', ?)
            """,
            (json_text({"store": "SEEKWAY:US", "listing": "L1"}), now),
        )

    dataset = load_return_dataset(
        returns_path,
        products_path,
        store="SEEKWAY:US",
        listing="L1",
    )
    key = str(dataset.unique_comments.iloc[0]["classification_key"])
    with database.transaction() as connection:
        connection.execute(
            """
            UPDATE task_segments SET classification_keys_json = ?
            WHERE id = 'segment-1'
            """,
            (json_text([key]),),
        )
    registry = load_capability_registry(
        PROJECT_ROOT / "config" / "category_capabilities.json"
    )
    capability = next(
        value for value in registry.capabilities if value.key == "footwear"
    )
    taxonomy = registry.load_taxonomy(capability)
    result = ValidatedClassification.model_validate(
        {
            "classification_key": key,
            "semantic_units": [
                {
                    "subject": "PRODUCT",
                    "label_code": "FIT_TOO_SMALL",
                    "opinion": "尺码偏小",
                    "sentiment": "NEGATIVE",
                    "assertion": "AFFIRMED",
                    "part": "WHOLE_SHOE",
                    "evidence": "Too small",
                    "implicit": False,
                    "claim_relation": "NONE",
                    "claim_id": None,
                }
            ],
            "unknown_semantics": [],
            "problem_label_codes": ["FIT_TOO_SMALL"],
            "positive_label_codes": [],
            "primary_label_codes": ["FIT_TOO_SMALL"],
            "status": ProcessingStatus.AUTO_APPROVED.value,
            "review_reasons": [],
            "model_name": "model-primary",
            "prompt_version": "prompt-v1",
            "taxonomy_version": taxonomy.version,
        }
    )
    return SimpleNamespace(
        database=database,
        dataset=dataset,
        results={key: result},
        taxonomy=taxonomy,
        key=key,
        task_id="task-1",
        segment_id="segment-1",
    )


def _publish(context: SimpleNamespace) -> dict[str, object]:
    return ClassificationResultService(context.database).publish_v1(
        task_id=context.task_id,
        segment_id=context.segment_id,
        dataset=context.dataset,
        results=context.results,
        taxonomy=context.taxonomy,
        segment_status="completed",
        progress_total=1,
        model_calls=1,
        cache_hits=0,
        checkpoint_path="checkpoint.json",
        legacy_result_version=1,
    )


def test_model_service_failures_pause_task_with_live_metrics(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)
    runner = AgentRunner(
        context.database,
        SimpleNamespace(),
        SimpleNamespace(),
        ClassificationResultService(context.database),
    )
    run = PipelineRun(
        classifications={},
        usage={},
        usage_by_model={},
        cache_hits=0,
        cache_hits_by_model={},
        model_calls=0,
        model_calls_by_model={},
        request_metrics={},
        routing={},
        model_failures=5,
    )

    runner._finish_model_service_paused(
        context.task_id,
        context.segment_id,
        "模型服务连续失败 5 次",
        {},
        run,
        tmp_path / "checkpoint.json",
        0,
        0,
        5,
    )

    with context.database.connect() as connection:
        task = connection.execute(
            "SELECT status, stage, pause_requested FROM tasks WHERE id = ?",
            (context.task_id,),
        ).fetchone()
        segment = connection.execute(
            """
            SELECT status, model_calls, cache_hits, model_failures, error
            FROM task_segments WHERE id = ?
            """,
            (context.segment_id,),
        ).fetchone()
    assert dict(task) == {
        "status": "paused",
        "stage": "模型服务异常",
        "pause_requested": 1,
    }
    assert segment["status"] == "paused"
    assert segment["model_calls"] == 0
    assert segment["cache_hits"] == 0
    assert segment["model_failures"] == 5
    assert "自动暂停" in segment["error"]


def _clone_publishable_segment(
    context: SimpleNamespace,
    suffix: str,
) -> SimpleNamespace:
    task_id = f"task-{suffix}"
    segment_id = f"segment-{suffix}"
    now = "2026-08-12T00:01:00+00:00"
    with context.database.transaction(immediate=True) as connection:
        connection.execute(
            """
            INSERT INTO tasks(
                id, title, owner_id, dataset_version_id, product_version_id,
                config_version_id, store, listing, status, stage,
                snapshot_json, created_at
            ) VALUES (?, '测试任务副本', 'user-1', 'version-returns',
                      'version-products', 'config-1', 'SEEKWAY:US', 'L1',
                      'running', '语义分析', '{}', ?)
            """,
            (task_id, now),
        )
        connection.execute(
            """
            INSERT INTO task_segments(
                id, task_id, segment_key, agent_key, agent_family,
                logic_version, taxonomy_version, model_policy_version,
                claims_version, scope_json, status, record_count,
                unique_comments, progress_total, classification_keys_json,
                created_at
            ) VALUES (?, ?, 'footwear', 'footwear', '鞋履智能体',
                      'logic-v1', 'taxonomy-v1', 'policy-v1', 'no-claims-v1',
                      ?, 'running', 3, 1, 1, ?, ?)
            """,
            (
                segment_id,
                task_id,
                json_text({"store": "SEEKWAY:US", "listing": "L1"}),
                json_text([context.key]),
                now,
            ),
        )
    return SimpleNamespace(
        **{
            **context.__dict__,
            "task_id": task_id,
            "segment_id": segment_id,
        }
    )


def test_publish_preserves_product_snapshot_and_duplicate_orders(
    tmp_path: Path,
) -> None:
    context = _seed_result_context(tmp_path)

    version = _publish(context)
    records = ClassificationResultService(context.database).records(
        str(version["version_id"]),
        page_size=200,
    )

    assert version["unit_count"] == 1
    assert version["record_count"] == 3
    assert records["total"] == 3
    assert {item["classification_key"] for item in records["items"]} == {
        context.key
    }
    assert [item["order_id"] for item in records["items"]].count("ORDER-DUP") == 2
    assert {item["product_name"] for item in records["items"]} == {
        "产品表权威名称"
    }
    assert {item["source_sku"] for item in records["items"]} == {
        "SOURCE-MSKU-1"
    }
    assert {item["matched_msku"] for item in records["items"]} == {
        "SOURCE-MSKU-1"
    }
    assert {item["product_sku"] for item in records["items"]} == {
        "PRODUCT-SKU-1"
    }
    assert [item["source_record_id"] for item in records["items"]] == [
        "version-returns:2",
        "version-returns:3",
        "version-returns:4",
    ]


def test_agent_runner_completion_publishes_result_reference(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)
    source = context.results[context.key]
    context.results = {
        context.key: source.model_copy(
            update={
                "status": ProcessingStatus.MANUAL_REVIEW,
                "review_reasons": ["需要人工确认"],
            }
        )
    }
    service = ClassificationResultService(context.database)
    runner = AgentRunner(
        context.database,
        SimpleNamespace(),
        SimpleNamespace(),
        service,
    )

    runner._complete_segment(
        task_id=context.task_id,
        segment_id=context.segment_id,
        status="completed",
        progress_total=1,
        model_calls=1,
        cache_hits=0,
        checkpoint_path=tmp_path / "checkpoint.json",
        result_version=1,
        dataset=context.dataset,
        results=context.results,
        taxonomy=context.taxonomy,
    )

    segment = TaskService(context.database).get(context.task_id)["segments"][0]
    version = service.get(str(segment["result_version_id"]))
    assert segment["status"] == "completed"
    assert segment["result_publish_status"] == "published"
    assert version["record_count"] == 3
    with context.database.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM review_records WHERE batch_id IS NULL"
        ).fetchone()[0] == 0


def test_product_match_uses_unique_store_asin_alias(
    tmp_path: Path,
) -> None:
    returns_path = tmp_path / "exact-match-returns.csv"
    products_path = tmp_path / "exact-match-products.xlsx"
    base = {
        "return-date": "2026-08-01",
        "asin": "SHARED-ASIN",
        "fnsku": "FNSKU",
        "product-name": "退货文件产品名",
        "quantity": "1",
        "reason": "APPAREL_TOO_SMALL",
        "customer-comments": "Too small",
        "店铺/站点": "SEEKWAY:US",
    }
    pd.DataFrame(
        [
            {**base, "order-id": "O-1", "sku": "MATCHED-MSKU"},
            {**base, "order-id": "O-2", "sku": "ALIAS-NOT-ALLOWED"},
        ]
    ).to_csv(returns_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(
        [
            {
                "MSKU": "MATCHED-MSKU",
                "店铺/站点": "SEEKWAY:US",
                "产品名称": "产品表名称",
                "SKU": "PRODUCT-SKU",
                "品类A": "水鞋",
                "品类B": "薄底水鞋",
                "Listing": "L1",
            }
        ]
    ).to_excel(products_path, sheet_name="产品信息汇总表", index=False)

    dataset = load_return_dataset_auto(returns_path, products_path)
    matched = dataset.records.loc[dataset.records["source_sku"].eq("MATCHED-MSKU")]
    aliased = dataset.records.loc[
        dataset.records["source_sku"].eq("ALIAS-NOT-ALLOWED")
    ]

    assert matched.iloc[0]["matched_msku"] == "MATCHED-MSKU"
    assert matched.iloc[0]["product_name"] == "产品表名称"
    assert matched.iloc[0]["product_sku"] == "PRODUCT-SKU"
    assert matched.iloc[0]["product_match_status"] == "matched"
    assert aliased.iloc[0]["matched_msku"] == "MATCHED-MSKU"
    assert aliased.iloc[0]["product_name"] == "产品表名称"
    assert aliased.iloc[0]["product_sku"] == "PRODUCT-SKU"
    assert aliased.iloc[0]["product_match_status"] == "matched"


def test_publish_is_idempotent_and_rejects_hash_conflict(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)
    first = _publish(context)
    second = _publish(context)

    assert first["version_id"] == second["version_id"]
    with context.database.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM classification_result_versions"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM classification_result_records"
        ).fetchone()[0] == 3

    changed = context.results[context.key].model_copy(
        update={"model_name": "different-model"}
    )
    context.results = {context.key: changed}
    with pytest.raises(ResultPublicationConflict):
        _publish(context)
    with context.database.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM classification_result_versions"
        ).fetchone()[0] == 1
        event = connection.execute(
            """
            SELECT event_type FROM task_events
            WHERE event_type = 'result_publish_conflict'
            """
        ).fetchone()
    assert event is not None


def test_publication_failure_rolls_back_all_result_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _seed_result_context(tmp_path)
    service = ClassificationResultService(context.database)

    def fail_insert(*_args: object) -> None:
        raise RuntimeError("写入记录失败")

    monkeypatch.setattr(service, "_insert_records", fail_insert)
    with pytest.raises(ResultPublicationError):
        service.publish_v1(
            task_id=context.task_id,
            segment_id=context.segment_id,
            dataset=context.dataset,
            results=context.results,
            taxonomy=context.taxonomy,
            segment_status="completed",
            progress_total=1,
            model_calls=1,
            cache_hits=0,
            checkpoint_path="checkpoint.json",
            legacy_result_version=1,
        )

    with context.database.connect() as connection:
        for table in (
            "classification_results",
            "classification_result_versions",
            "classification_units",
            "classification_unit_labels",
            "classification_result_records",
        ):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
        segment = connection.execute(
            """
            SELECT status, result_version_id, result_publish_status
            FROM task_segments WHERE id = 'segment-1'
            """
        ).fetchone()
    assert segment["status"] == "running"
    assert segment["result_version_id"] is None
    assert segment["result_publish_status"] == "failed"


def test_cancel_parent_keeps_published_listing_result(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)
    version = _publish(context)
    TaskService(context.database).cancel(
        context.task_id,
        "user-1",
        "不再运行其他 Listing",
        expected_revision=1,
    )

    persisted = ClassificationResultService(context.database).get(
        str(version["version_id"])
    )
    assert persisted["publish_status"] == "published"
    assert persisted["record_count"] == 3


def test_result_api_paginates_filters_drills_down_and_downloads(
    tmp_path: Path,
) -> None:
    context = _seed_result_context(tmp_path)
    version = _publish(context)
    service = ClassificationResultService(context.database)
    app = FastAPI()
    app.include_router(
        create_classification_result_router(
            service,
            lambda: {"id": "another-user"},
        )
    )
    client = TestClient(app)
    version_id = str(version["version_id"])

    listed = client.get("/api/classification-results?page=1&page_size=1")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["version_id"] == version_id

    records = client.get(
        f"/api/classification-results/{version_id}/records",
        params={"order_id": "ORDER-DUP", "page_size": 1},
    )
    assert records.status_code == 200
    assert records.json()["total"] == 2
    assert records.json()["items"][0]["source_row"] == 2

    by_problem = client.get(
        f"/api/classification-results/{version_id}/drilldown",
        params={"group_by": "problem"},
    )
    assert by_problem.status_code == 200
    assert by_problem.json()["items"][0]["value"] == "FIT_TOO_SMALL"
    assert by_problem.json()["items"][0]["record_count"] == 3

    by_product = client.get(
        f"/api/classification-results/{version_id}/drilldown",
        params={
            "group_by": "product_name",
            "product_sku": "PRODUCT-SKU-1",
        },
    )
    assert by_product.status_code == 200
    assert by_product.json()["items"] == [
        {
            "value": "产品表权威名称",
            "record_count": 3,
            "unit_count": 1,
        }
    ]

    summary = client.get(f"/api/classification-results/{version_id}/summary")
    assert summary.status_code == 200
    assert summary.json()["top_problems"][0]["record_count"] == 3

    download = client.get(f"/api/classification-results/{version_id}/download")
    assert download.status_code == 200
    assert download.content.startswith(b"PK")
    assert "PRODUCT-SKU-1" in pd.read_excel(BytesIO(download.content)).to_string()


def test_result_records_filter_product_name_before_pagination(
    tmp_path: Path,
) -> None:
    context = _seed_result_context(tmp_path)
    version = _publish(context)
    version_id = str(version["version_id"])
    with context.database.transaction() as connection:
        connection.execute(
            """
            UPDATE classification_result_records SET product_name = '其他产品'
            WHERE result_version_id = ? AND source_row = 4
            """,
            (version_id,),
        )
    service = ClassificationResultService(context.database)

    filtered = service.records(
        version_id,
        product_name="产品表权威名称",
        listing="L1",
        product_sku="PRODUCT-SKU-1",
        problem="FIT_TOO_SMALL",
        page=1,
        page_size=1,
    )
    assert filtered["total"] == 2
    assert len(filtered["items"]) == 1
    assert filtered["items"][0]["product_name"] == "产品表权威名称"
    assert service.records(version_id, product_name="不存在")["total"] == 0

    app = FastAPI()
    app.include_router(
        create_classification_result_router(
            service,
            lambda: {"id": "another-user"},
        )
    )
    response = TestClient(app).get(
        f"/api/classification-results/{version_id}/records",
        params={
            "product_name": "产品表权威名称",
            "listing": "L1",
            "product_sku": "PRODUCT-SKU-1",
            "problem": "FIT_TOO_SMALL",
            "page": 1,
            "page_size": 1,
        },
    )
    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert len(response.json()["items"]) == 1


def test_retry_result_publish_uses_checkpoint_without_model_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _seed_result_context(tmp_path)
    checkpoint_path = tmp_path / "segment-1-classifications.json"
    AgentRunner._write_checkpoint(checkpoint_path, context.results)
    with context.database.transaction() as connection:
        connection.execute(
            """
            UPDATE task_segments
            SET status = 'completed', progress_current = progress_total,
                result_json_path = ?, result_publish_status = 'failed',
                result_publish_error = '模拟发布失败', completed_at = ?
            WHERE id = ?
            """,
            (
                str(checkpoint_path),
                "2026-08-12T00:02:00+00:00",
                context.segment_id,
            ),
        )
        connection.execute(
            "UPDATE tasks SET status = 'completed' WHERE id = ?",
            (context.task_id,),
        )

    def forbidden_model_call(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("结果发布重试不得调用模型")

    monkeypatch.setattr(
        "web_backend.agent_runner.classify_comments",
        forbidden_model_call,
    )
    runner = AgentRunner(
        context.database,
        SimpleNamespace(data_dir=tmp_path),
        SimpleNamespace(),
    )
    task_service = TaskService(
        context.database,
        result_publisher=runner.retry_result_publish,
    )
    app = FastAPI()
    app.include_router(
        create_task_router(
            task_service=task_service,
            analysis_service=AnalysisService(context.database),
            current_user=lambda: {"id": "user-1"},
        )
    )
    client = TestClient(app)
    endpoint = (
        f"/api/tasks/{context.task_id}/segments/"
        f"{context.segment_id}/retry-result-publish"
    )
    response = client.post(
        endpoint,
        json={"expected_revision": 1, "reason": "恢复结果池发布"},
    )

    assert response.status_code == 200
    task = response.json()
    segment = next(
        item for item in task["segments"] if item["id"] == context.segment_id
    )
    assert task["status"] == "completed"
    assert segment["status"] == "completed"
    assert segment["result_publish_status"] == "published"
    assert segment["result_version_id"]
    assert segment["result_publish_error"] is None
    assert segment["model_calls"] == 0

    with context.database.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM classification_result_versions"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM classification_result_records"
        ).fetchone()[0] == 3
        event = connection.execute(
            """
            SELECT actor_id, data_json FROM task_events
            WHERE task_id = ? AND event_type = 'result_publish_retry'
            """,
            (context.task_id,),
        ).fetchone()
        audit = connection.execute(
            """
            SELECT actor_id, after_json FROM audit_logs
            WHERE entity_id = ? AND action = 'retry_result_publish'
            """,
            (context.task_id,),
        ).fetchone()
    assert event["actor_id"] == "user-1"
    assert json_value(event["data_json"], {})["reason"] == "恢复结果池发布"
    assert audit["actor_id"] == "user-1"
    assert json_value(audit["after_json"], {})["reason"] == "恢复结果池发布"

    stale = client.post(
        endpoint,
        json={"expected_revision": 1, "reason": "另一位用户重复提交"},
    )
    assert stale.status_code == 409
    assert "已被他人修改" in stale.json()["detail"]
    duplicate = client.post(
        endpoint,
        json={"expected_revision": task["revision"], "reason": "重复提交"},
    )
    assert duplicate.status_code == 409
    assert "已经发布" in duplicate.json()["detail"]
    with context.database.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM classification_result_versions"
        ).fetchone()[0] == 1


def test_retry_result_publish_rejects_missing_checkpoint_and_publishing(
    tmp_path: Path,
) -> None:
    context = _seed_result_context(tmp_path)
    called = False

    def publisher(_task_id: str, _segment_id: str) -> dict[str, object]:
        nonlocal called
        called = True
        return {}

    service = TaskService(context.database, result_publisher=publisher)
    with context.database.transaction() as connection:
        connection.execute(
            """
            UPDATE task_segments
            SET status = 'completed', result_publish_status = 'failed',
                result_json_path = NULL
            WHERE id = ?
            """,
            (context.segment_id,),
        )
    with pytest.raises(TaskResultPublishConflict, match="没有可用的分类检查点"):
        service.retry_result_publish(
            context.task_id,
            context.segment_id,
            "user-1",
            1,
            "尝试恢复发布",
        )
    assert called is False

    checkpoint_path = tmp_path / "checkpoint.json"
    AgentRunner._write_checkpoint(checkpoint_path, context.results)
    with context.database.transaction() as connection:
        connection.execute(
            """
            UPDATE task_segments
            SET result_publish_status = 'publishing', result_json_path = ?
            WHERE id = ?
            """,
            (str(checkpoint_path), context.segment_id),
        )
    with pytest.raises(TaskResultPublishConflict, match="正在发布"):
        service.retry_result_publish(
            context.task_id,
            context.segment_id,
            "user-1",
            1,
            "再次尝试",
        )
    assert called is False

    with context.database.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM audit_logs"
        ).fetchone()[0] == 0


def test_result_list_product_names_are_unique_sorted_and_empty(
    tmp_path: Path,
) -> None:
    context = _seed_result_context(tmp_path)
    version = _publish(context)
    service = ClassificationResultService(context.database)
    version_id = str(version["version_id"])

    assert service.list()["items"][0]["product_names"] == ["产品表权威名称"]
    with context.database.transaction() as connection:
        connection.execute(
            """
            UPDATE classification_result_records
            SET product_name = CASE source_row
                WHEN 2 THEN 'Beta'
                WHEN 3 THEN 'Alpha'
                ELSE 'Alpha'
            END
            WHERE result_version_id = ?
            """,
            (version_id,),
        )
    assert service.list()["items"][0]["product_names"] == ["Alpha", "Beta"]

    with context.database.transaction() as connection:
        connection.execute(
            """
            UPDATE classification_result_records SET product_name = NULL
            WHERE result_version_id = ?
            """,
            (version_id,),
        )
    assert service.list()["items"][0]["product_names"] == []


def test_result_list_q_filters_in_database_before_pagination(
    tmp_path: Path,
) -> None:
    context = _seed_result_context(tmp_path)
    first = _publish(context)
    second_context = _clone_publishable_segment(context, "2")
    second = _publish(second_context)
    first_id = str(first["version_id"])
    second_id = str(second["version_id"])
    with context.database.transaction() as connection:
        connection.execute(
            """
            UPDATE classification_result_records SET product_name = 'Alpha Product'
            WHERE result_version_id = ?
            """,
            (first_id,),
        )
        connection.execute(
            """
            UPDATE classification_result_records SET product_name = 'Beta Product'
            WHERE result_version_id = ?
            """,
            (second_id,),
        )
    service = ClassificationResultService(context.database)

    assert service.list(q="Beta", page=1, page_size=1) == {
        "items": [service.get(second_id)],
        "total": 1,
        "page": 1,
        "page_size": 1,
    }
    for query in ("L1", "SOURCE-MSKU", "PRODUCT-SKU"):
        assert service.list(q=query, page_size=1)["total"] == 2
    assert service.list(q="missing-value")["total"] == 0
    combined = service.list(
        q="PRODUCT-SKU",
        store_site="SEEKWAY:US",
        listing="L1",
        quality_status="ready",
        page_size=1,
    )
    assert combined["total"] == 2
    assert len(combined["items"]) == 1
    assert service.list(q="PRODUCT-SKU", store_site="OTHER")["total"] == 0
    assert service.list()["total"] == 2

    app = FastAPI()
    app.include_router(
        create_classification_result_router(
            service,
            lambda: {"id": "another-user"},
        )
    )
    response = TestClient(app).get(
        "/api/classification-results",
        params={"q": "Beta", "page": 1, "page_size": 1},
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["product_names"] == ["Beta Product"]


def test_unknown_category_has_no_segment_and_no_model_target(tmp_path: Path) -> None:
    context = _seed_result_context(tmp_path)
    dataset = context.dataset
    records = dataset.records.copy()
    comments = dataset.unique_comments.copy()
    records["category_a"] = "未配置品类"
    records["category_b"] = "未配置变体"
    comments["category_a"] = "未配置品类"
    comments["category_b"] = "未配置变体"
    unknown_dataset = dataset.__class__(
        records=records,
        unique_comments=comments,
        mskus=dataset.mskus,
        scopes=dataset.scopes,
        primary_store=dataset.primary_store,
        scope_mode=dataset.scope_mode,
    )
    registry = load_capability_registry(
        PROJECT_ROOT / "config" / "category_capabilities.json"
    )

    plan = build_category_execution_plan(
        unknown_dataset,
        registry,
        store="SEEKWAY:US",
        listing="L1",
    )

    assert plan.summary["segments"] == []
    assert plan.summary["blocked_count"] == 1
    assert plan.summary["unknown_category_count"] == 1
    assert plan.summary["excluded_count"] == 1
    assert plan.classification_keys_by_segment(unknown_dataset) == {}


def test_new_unknown_category_task_completes_without_execution_segment(
    tmp_path: Path,
) -> None:
    context = _seed_result_context(tmp_path)
    with context.database.connect() as connection:
        product_row = connection.execute(
            "SELECT file_path FROM dataset_versions WHERE id = 'version-products'"
        ).fetchone()
    products_path = Path(str(product_row["file_path"]))
    pd.DataFrame(
        [
            {
                "MSKU": "SOURCE-MSKU-1",
                "店铺/站点": "SEEKWAY:US",
                "产品名称": "产品表权威名称",
                "SKU": "PRODUCT-SKU-1",
                "品类A": "未配置品类",
                "品类B": "未配置变体",
                "Listing": "L1",
            }
        ]
    ).to_excel(products_path, sheet_name="产品信息汇总表", index=False)
    service = TaskService(context.database)
    preflight = service.preflight(
        "version-returns",
        "version-products",
        "SEEKWAY:US",
        "L1",
        "config-1",
    )

    task = service.create(
        actor_id="user-1",
        title="未知品类任务",
        dataset_version_id="version-returns",
        product_version_id="version-products",
        store="SEEKWAY:US",
        listing="L1",
        config_version_id="config-1",
        plan_hash=str(preflight["plan_hash"]),
        unresolved_policy="block_all",
    )

    assert preflight["segments"] == []
    assert preflight["unknown_category_count"] == 1
    assert task["segments"] == []
    assert task["status"] == "completed"
    assert task["progress_total"] == 0


def test_task_segment_response_keeps_legacy_fields_and_adds_result_reference(
    tmp_path: Path,
) -> None:
    context = _seed_result_context(tmp_path)
    version = _publish(context)

    task = TaskService(context.database).get(context.task_id)
    segment = task["segments"][0]
    assert segment["result_json_path"] == "checkpoint.json"
    assert segment["result_version"] == 1
    assert segment["result_version_id"] == version["version_id"]
    assert segment["result_publish_status"] == "published"
    assert segment["result_quality_status"] == "ready"
    assert segment["result_published_at"]
    assert segment["result_publish_error"] is None
