from __future__ import annotations

import inspect
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pandas as pd

from return_semantics.pipeline import PipelineRun
from return_semantics.schemas import ProcessingStatus, ValidatedClassification
from web_backend import (
    classification_standard_validation_service as validation_service_module,
)
from web_backend.classification_standard_service import ClassificationStandardService
from web_backend.classification_standard_validation_service import (
    ClassificationStandardValidationConflict,
    ClassificationStandardValidationNotFound,
    ClassificationStandardValidationService,
)
from web_backend.database import Database


class FakeRunner:
    def classify_taxonomy_sample(
        self,
        *,
        taxonomy: Any,
        samples: list[dict[str, Any]],
        source: dict[str, Any],
        progress: Any,
    ) -> PipelineRun:
        del source
        taxonomy_codes = {label.code for label in taxonomy.labels}
        is_draft = str(taxonomy.version).startswith("draft-")
        classifications = {}
        for position, sample in enumerate(samples, start=1):
            baseline = sample["baseline"].get("primary_label_codes", [])
            if not is_draft:
                label_codes = (
                    ["EYEWEAR_FIT_PRESSURE"]
                    if "EYEWEAR_FIT_PRESSURE" in taxonomy_codes
                    else [taxonomy.labels[0].code]
                )
            elif position == 1:
                label_codes = ["EYEWEAR_LENS_QUALITY"]
            else:
                label_codes = list(baseline) or [taxonomy.labels[0].code]
            classifications[sample["classification_key"]] = ValidatedClassification(
                classification_key=sample["classification_key"],
                semantic_units=[],
                unknown_semantics=[],
                problem_label_codes=label_codes,
                positive_label_codes=[],
                primary_label_codes=label_codes,
                status=ProcessingStatus.AUTO_APPROVED,
                review_reasons=[],
                model_name="fake-model",
                prompt_version="test",
                taxonomy_version="draft-test",
            )
            progress(position, len(samples))
        return PipelineRun(
            classifications=classifications,
            usage={"input_tokens": 20},
            usage_by_model={"fake-model": {"input_tokens": 20}},
            cache_hits=0,
            cache_hits_by_model={},
            model_calls=len(samples),
            model_calls_by_model={"fake-model": len(samples)},
            request_metrics={},
            routing={},
        )


def _services(
    tmp_path: Path,
) -> tuple[ClassificationStandardService, ClassificationStandardValidationService]:
    database = Database(tmp_path / "app.db")
    database.initialize()
    with database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO users(
                id, email, display_name, password_hash, created_at
            ) VALUES ('user-1', 'user@example.com', '测试用户', 'hash', 'now')
            """
        )
    standards = ClassificationStandardService(database)
    validations = ClassificationStandardValidationService(
        database,
        standards,
        FakeRunner(),
    )
    return standards, validations


def test_validation_service_preserves_method_contract() -> None:
    expected_methods = [
        "__init__|(self, database: 'Database', standard_service: 'ClassificationStandardService', runner: 'AgentRunner') -> 'None'|function",
        "sources|(self, draft_id: 'str') -> 'list[dict[str, Any]]'|function",
        "list_runs|(self, draft_id: 'str') -> 'list[dict[str, Any]]'|function",
        "get|(self, run_id: 'str', include_items: 'bool' = True) -> 'dict[str, Any]'|function",
        "create_run|(self, draft_id: 'str', expected_revision: 'int', source_result_version_id: 'str', sample_size: 'int', actor_id: 'str', review_file: 'tuple[str, bytes] | None' = None, comparison_type: 'str' = 'standard_version') -> 'dict[str, Any]'|function",
        "_validation_source_context|(self, draft: 'dict[str, Any]', source_result_version_id: 'str', sample_size: 'int', review_file: 'tuple[str, bytes] | None') -> 'tuple[dict[str, Any], list[dict[str, Any]], str]'|function",
        "_apply_recognition_context|(self, source: 'dict[str, Any]', draft: 'dict[str, Any]', draft_id: 'str', expected_revision: 'int', comparison_type: 'str') -> 'None'|function",
        "approve|(self, run_id: 'str', expected_revision: 'int', note: 'str', actor_id: 'str') -> 'dict[str, Any]'|function",
        "recover|(self) -> 'None'|function",
        "claim_next|(self) -> 'str | None'|function",
        "run|(self, run_id: 'str') -> 'None'|function",
        "_raw_source_options|(self) -> 'list[dict[str, Any]]'|function",
        "_raw_source_context|(self, source_id: 'str', draft: 'dict[str, Any]', sample_size: 'int') -> 'tuple[dict[str, Any], list[dict[str, Any]]]'|function",
        "_published_config_id|(self) -> 'str'|function",
        "_review_source_context|(self, filename: 'str', content: 'bytes', draft: 'dict[str, Any]', sample_size: 'int') -> 'tuple[dict[str, Any], list[dict[str, Any]]]'|function",
        "_review_sheet_context|(workbook: 'Any') -> 'tuple[Any, list[str], int] | None'|staticmethod",
        "_review_candidates|(sheet: 'Any', headers: 'list[str]', header_row: 'int', variants: 'list[dict[str, Any]]', references: 'dict[str, Any]') -> 'tuple[list[dict[str, Any]], int]'|staticmethod",
        "_validate_review_references|(candidates: 'list[dict[str, Any]]', references: 'dict[str, Any]') -> 'None'|staticmethod",
        "_read_references|(workbook, taxonomy: 'dict') -> 'dict'|staticmethod",
        "_round_robin_samples|(items: 'list[dict[str, Any]]', sample_size: 'int', *, bucket_fields: 'tuple[str, ...]') -> 'list[dict[str, Any]]'|staticmethod",
        "_source_context|(self, result_version_id: 'str', base_version_id: 'str') -> 'dict[str, Any]'|function",
        "_sample|(self, result_version_id: 'str', sample_size: 'int') -> 'list[dict[str, Any]]'|function",
        "_comparison_items|(samples: 'list[dict[str, Any]]', classifications: 'dict[str, Any]') -> 'list[dict[str, Any]]'|staticmethod",
        "_summary|(items: 'list[dict[str, Any]]') -> 'dict[str, Any]'|staticmethod",
        "_serialize|(self, value: 'dict[str, Any]', include_items: 'bool' = False) -> 'dict[str, Any]'|function",
    ]

    actual_methods = []
    for expected in expected_methods:
        name = expected.partition("|")[0]
        descriptor = inspect.getattr_static(
            ClassificationStandardValidationService,
            name,
        )
        actual_methods.append(
            f"{name}|{inspect.signature(getattr(ClassificationStandardValidationService, name))}|{type(descriptor).__name__}"
        )

    assert actual_methods == expected_methods
    assert isinstance(
        inspect.getattr_static(
            ClassificationStandardValidationService,
            "_evaluate_references",
        ),
        staticmethod,
    )
    assert callable(ClassificationStandardValidationService._evaluate_references)


def test_validation_service_preserves_exception_import_contract() -> None:
    from web_backend.routers import classification_standards as router_module

    assert (
        ClassificationStandardValidationNotFound
        is validation_service_module.ClassificationStandardValidationNotFound
        is router_module.ClassificationStandardValidationNotFound
    )
    assert (
        ClassificationStandardValidationConflict
        is validation_service_module.ClassificationStandardValidationConflict
        is router_module.ClassificationStandardValidationConflict
    )
    assert issubclass(ClassificationStandardValidationNotFound, ValueError)
    assert issubclass(ClassificationStandardValidationConflict, ValueError)
    assert (
        ClassificationStandardValidationNotFound.__module__
        == "web_backend.classification_standard_validation_service"
    )
    assert (
        ClassificationStandardValidationConflict.__module__
        == "web_backend.classification_standard_validation_service"
    )


def test_validation_routes_preserve_registration_contract(tmp_path: Path) -> None:
    from fastapi.routing import APIRoute

    from web_backend.routers.classification_standards import (
        create_classification_standard_router,
    )

    standards, validations = _services(tmp_path)

    def current_user() -> dict[str, str]:
        return {"id": "user-1"}

    router = create_classification_standard_router(
        standards,
        validations,
        current_user,
    )
    routes = [
        route
        for route in router.routes
        if isinstance(route, APIRoute) and "validation" in route.path
    ]
    expected_routes = [
        "GET|/api/classification-standard-drafts/{draft_id}/validation-sources|validation_sources|200|sync|draft_id,_user",
        "GET|/api/classification-standard-drafts/{draft_id}/validation-runs|validation_runs|200|sync|draft_id,_user",
        "POST|/api/classification-standard-drafts/{draft_id}/validation-runs|create_validation_run|201|sync|draft_id,payload,user",
        "POST|/api/classification-standard-drafts/{draft_id}/review-validation-runs|create_review_validation_run|201|async|draft_id,user,expected_revision,file,sample_size,comparison_type",
        "GET|/api/classification-standard-validation-runs/{run_id}|validation_run|200|sync|run_id,_user",
        "POST|/api/classification-standard-validation-runs/{run_id}/approve|approve_validation_run|200|sync|run_id,payload,user",
    ]
    actual_routes = [
        "|".join(
            (
                next(iter(route.methods)),
                route.path,
                route.name,
                str(route.status_code or 200),
                "async" if inspect.iscoroutinefunction(route.endpoint) else "sync",
                ",".join(inspect.signature(route.endpoint).parameters),
            )
        )
        for route in routes
    ]

    assert actual_routes == expected_routes
    assert all(len(route.dependant.dependencies) == 1 for route in routes)
    assert all(route.dependant.dependencies[0].call is current_user for route in routes)


def _seed_result(
    service: ClassificationStandardService,
    standard: dict[str, Any],
    category_a: str = "眼镜",
    category_b: str = "儿童眼镜",
    return_path: Path | None = None,
    product_path: Path | None = None,
) -> str:
    baseline = {
        "primary_label_codes": ["EYEWEAR_FIT_PRESSURE"],
        "status": "AUTO_APPROVED",
    }
    with service.database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO api_connections(
                id, name, provider, active_version_id,
                created_by, created_at, updated_at
            ) VALUES ('connection-1', '测试连接', 'openai', 'config-1',
                      'user-1', 'now', 'now')
            """
        )
        connection.execute(
            """
            INSERT INTO api_config_versions(
                id, connection_id, version, base_url, api_key_ciphertext,
                primary_model, primary_effort, cheap_effort,
                secondary_effort, created_by, created_at, published_at
            ) VALUES ('config-1', 'connection-1', 1, 'https://example.com',
                      'secret', 'fake-model', 'medium', 'low', 'high',
                      'user-1', 'now', 'now')
            """
        )
        for dataset_id, kind, version_id in (
            ("returns", "returns", "returns-v1"),
            ("products", "products", "products-v1"),
        ):
            connection.execute(
                """
                INSERT INTO datasets(
                    id, name, kind, current_version,
                    created_by, created_at, updated_at
                ) VALUES (?, ?, ?, 1, 'user-1', 'now', 'now')
                """,
                (dataset_id, dataset_id, kind),
            )
            connection.execute(
                """
                INSERT INTO dataset_versions(
                    id, dataset_id, version, file_path, original_name,
                    content_type, size_bytes, sha256, row_count,
                    column_count, schema_json, quality_json,
                    created_by, created_at
                ) VALUES (?, ?, 1, ?, 'file.xlsx',
                          'application/octet-stream', 1, 'hash', 2, 2,
                          '{}', '{}', 'user-1', 'now')
                """,
                (
                    version_id,
                    dataset_id,
                    str(
                        return_path
                        if kind == "returns" and return_path
                        else product_path
                        if kind == "products" and product_path
                        else "file.xlsx"
                    ),
                ),
            )
        connection.execute(
            """
            INSERT INTO tasks(
                id, title, owner_id, dataset_version_id,
                product_version_id, config_version_id, store, listing,
                status, stage, message, snapshot_json, created_at
            ) VALUES ('task-1', '测试任务', 'user-1', 'returns-v1',
                      'products-v1', 'config-1', 'SEEKWAY:US', 'SK002',
                      'completed', '完成', '', '{}', 'now')
            """
        )
        connection.execute(
            """
            INSERT INTO task_segments(
                id, task_id, segment_key, agent_key, agent_family,
                logic_version, taxonomy_version, model_policy_version,
                standard_version_id, scope_json, status,
                classification_keys_json, created_at
            ) VALUES ('segment-1', 'task-1', 'segment-key', 'eyewear',
                      '眼镜智能体', ?, ?, ?, ?, '{}', 'completed',
                      '["key-1","key-2"]', 'now')
            """,
            (
                standard["logic_version"],
                standard["taxonomy_version"],
                standard["model_policy_version"],
                standard["standard_version_id"],
            ),
        )
        connection.execute(
            """
            INSERT INTO classification_results(
                id, source_task_id, source_segment_id,
                dataset_version_id, product_version_id, store_site,
                listing, agent_key, agent_family, logic_version,
                taxonomy_version, model_policy_version,
                standard_version_id, created_at
            ) VALUES ('result-1', 'task-1', 'segment-1', 'returns-v1',
                      'products-v1', 'SEEKWAY:US', 'SK002', 'eyewear',
                      '眼镜智能体', ?, ?, ?, ?, 'now')
            """,
            (
                standard["logic_version"],
                standard["taxonomy_version"],
                standard["model_policy_version"],
                standard["standard_version_id"],
            ),
        )
        connection.execute(
            """
            INSERT INTO classification_result_versions(
                id, result_id, source_segment_id, version_no,
                content_hash, quality_status, publish_status,
                unit_count, record_count, created_by, created_at, published_at
            ) VALUES ('result-version-1', 'result-1', 'segment-1', 1,
                      'hash', 'ready', 'published', 2, 2,
                      'user-1', 'now', 'now')
            """
        )
        for index in (1, 2):
            connection.execute(
                """
                INSERT INTO classification_units(
                    id, result_version_id, classification_key,
                    comment, classification_json, problem_labels_json,
                    processing_status, quality_status, record_count
                ) VALUES (?, 'result-version-1', ?, ?, ?,
                          '["EYEWEAR_FIT_PRESSURE"]',
                          'AUTO_APPROVED', 'ready', 1)
                """,
                (
                    f"unit-{index}",
                    f"key-{index}",
                    f"comment {index}",
                    json.dumps(baseline),
                ),
            )
            connection.execute(
                """
                INSERT INTO classification_result_records(
                    id, result_version_id, classification_key,
                    source_record_id, source_row, listing,
                    category_a, category_b, comment,
                    product_match_status, quality_status
                ) VALUES (?, 'result-version-1', ?, ?, ?, 'SK002',
                          ?, ?, ?, 'matched', 'ready')
                """,
                (
                    f"record-{index}",
                    f"key-{index}",
                    f"source-{index}",
                    index,
                    category_a,
                    category_b,
                    f"comment {index}",
                ),
            )
    return "result-version-1"


def test_sample_validation_completes_and_becomes_stale_after_edit(
    tmp_path: Path,
) -> None:
    standards, validations = _services(tmp_path)
    standard = next(
        item for item in standards.list() if item["standard_key"] == "eyewear"
    )
    source_version_id = _seed_result(standards, standard)
    draft = standards.create_draft(standard["id"], "user-1")
    content = deepcopy(draft["content"])
    content["labels"][0]["keywords"] = ["pressure", "tight"]
    draft = standards.update_draft(
        draft["id"],
        draft["revision"],
        content,
        "验证标签关键词",
        "user-1",
    )

    sources = validations.sources(draft["id"])
    assert any(source["source_kind"] == "raw_dataset" for source in sources)
    result_source = next(
        source for source in sources if source["result_version_id"] == source_version_id
    )
    assert result_source["available_sample_count"] == 2

    run = validations.create_run(
        draft["id"],
        draft["revision"],
        source_version_id,
        20,
        "user-1",
    )
    assert run["status"] == "queued"
    assert run["sample_size"] == 2
    assert validations.claim_next() == run["id"]
    validations.run(run["id"])

    completed = validations.get(run["id"])
    assert completed["status"] == "completed"
    assert completed["summary"]["changed_count"] == 1
    assert completed["summary"]["error_count"] == 0
    assert completed["publication_ready"] is False
    assert len(completed["items"]) == 2

    approved = validations.approve(
        run["id"],
        draft["revision"],
        "差异符合预期，可以发布",
        "user-1",
    )
    assert approved["publication_ready"] is True
    assert approved["approved_by_name"] == "测试用户"
    assert approved["approval_note"] == "差异符合预期，可以发布"

    changed_content = deepcopy(draft["content"])
    changed_content["product_context"] = "再次修改后的适用范围"
    standards.update_draft(
        draft["id"],
        draft["revision"],
        changed_content,
        "再次修改",
        "user-1",
    )

    stale = validations.get(run["id"])
    assert stale["is_current"] is False
    assert stale["publication_ready"] is False


def test_validation_freezes_actor_model_preference(tmp_path: Path) -> None:
    standards, validations = _services(tmp_path)
    standard = next(
        item for item in standards.list() if item["standard_key"] == "eyewear"
    )
    source_version_id = _seed_result(standards, standard)
    with standards.database.transaction() as connection:
        for model_key in ("preferred-primary", "preferred-secondary"):
            connection.execute(
                """
                INSERT INTO api_models(
                    id, connection_id, model_key, display_name,
                    supported_efforts_json, active, validation_status,
                    validated_at, created_by, created_at, updated_by, updated_at
                ) VALUES (?, 'connection-1', ?, ?, '["low","medium","high"]',
                          1, 'validated', 'now', 'user-1', 'now', 'user-1', 'now')
                """,
                (f"model-{model_key}", model_key, model_key),
            )
        connection.execute(
            """
            INSERT INTO user_model_preferences(
                user_id, connection_id, primary_model, primary_effort,
                secondary_model, secondary_effort, cheap_audit_percent,
                updated_at, updated_by
            ) VALUES ('user-1', 'connection-1', 'preferred-primary', 'high',
                      'preferred-secondary', 'high', 5, 'now', 'user-1')
            """
        )
    draft = standards.create_draft(standard["id"], "user-1")
    content = deepcopy(draft["content"])
    content["product_context"] = "验证用户模型偏好快照"
    draft = standards.update_draft(
        draft["id"],
        draft["revision"],
        content,
        "验证模型偏好",
        "user-1",
    )

    run = validations.create_run(
        draft["id"],
        draft["revision"],
        source_version_id,
        20,
        "user-1",
    )

    assert run["config_version_id"] == "config-1"
    with standards.database.connect() as connection:
        row = connection.execute(
            "SELECT source_json FROM classification_standard_validation_runs "
            "WHERE id = ?",
            (run["id"],),
        ).fetchone()
    source = json.loads(row["source_json"])
    assert source["model_policy"]["actual"] == {
        "primary": {
            "role": "primary",
            "model": "preferred-primary",
            "effort": "high",
        },
        "first_pass": {
            "role": "primary",
            "model": "preferred-primary",
            "effort": "high",
        },
        "review": {
            "role": "secondary",
            "model": "preferred-secondary",
            "effort": "high",
        },
    }


def test_new_standard_uses_matching_categories_from_raw_data(
    tmp_path: Path,
) -> None:
    standards, validations = _services(tmp_path)
    source_standard = next(
        item for item in standards.list() if item["standard_key"] == "eyewear"
    )
    return_path = tmp_path / "returns.csv"
    product_path = tmp_path / "products.xlsx"
    pd.DataFrame(
        [
            {
                "return-date": "2026-08-01",
                "order-id": f"order-{index}",
                "sku": "BP-001",
                "asin": "ASIN-1",
                "fnsku": "FNSKU-1",
                "product-name": "户外背包",
                "quantity": 1,
                "reason": "DAMAGED",
                "customer-comments": f"backpack comment {index}",
                "店铺/站点": "SEEKWAY:US",
            }
            for index in (1, 2)
        ]
    ).to_csv(return_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(
        [
            {
                "MSKU": "BP-001",
                "店铺/站点": "SEEKWAY:US",
                "Listing": "BP001",
                "产品名称": "户外背包",
                "SKU": "BP-001",
                "品类A": "箱包",
                "品类B": "户外背包",
            }
        ]
    ).to_excel(product_path, sheet_name="产品信息汇总表", index=False)
    _seed_result(
        standards,
        source_standard,
        return_path=return_path,
        product_path=product_path,
    )
    draft = standards.create_standard(
        name="户外背包退货分类标准",
        product_context="户外及通勤背包",
        category_a="箱包",
        category_b="户外背包",
        actor_id="user-1",
    )
    content = deepcopy(draft["content"])
    content["instructions"] = ["识别背包结构和佩戴问题"]
    content["labels"] = [
        {
            "code": "BACKPACK_STRUCTURE_DAMAGE",
            "name": "结构损坏",
            "group": "质量与耐用",
            "description": "背包主体、拉链或缝线发生损坏",
            "allowed_sentiments": ["NEGATIVE"],
        }
    ]
    draft = standards.update_draft(
        draft["id"],
        draft["revision"],
        content,
        "建立背包分类标准",
        "user-1",
    )

    sources = validations.sources(draft["id"])
    assert len(sources) == 1
    assert sources[0]["source_kind"] == "raw_dataset"
    assert sources[0]["return_dataset_name"] == "returns"
    assert sources[0]["product_dataset_name"] == "products"

    run = validations.create_run(
        draft["id"],
        draft["revision"],
        sources[0]["result_version_id"],
        20,
        "user-1",
    )
    assert validations.claim_next() == run["id"]
    validations.run(run["id"])

    completed = validations.get(run["id"])
    assert completed["status"] == "completed"
    assert completed["publication_ready"] is False
    assert completed["source"]["available_sample_count"] == 2
    assert completed["source"]["listing"] == "BP001"
    assert {item["category_b"] for item in completed["items"]} == {"户外背包"}

    approved = validations.approve(
        run["id"],
        draft["revision"],
        "新标准样本结果符合预期",
        "user-1",
    )
    assert approved["publication_ready"] is True


def test_existing_standard_can_compare_raw_samples_with_base_and_draft(
    tmp_path: Path,
) -> None:
    standards, validations = _services(tmp_path)
    standard = next(
        item for item in standards.list() if item["standard_key"] == "eyewear"
    )
    return_path = tmp_path / "returns.csv"
    product_path = tmp_path / "products.xlsx"
    pd.DataFrame(
        [
            {
                "return-date": "2026-08-01",
                "order-id": f"order-{index}",
                "sku": "GL-001",
                "asin": "ASIN-1",
                "fnsku": "FNSKU-1",
                "product-name": "儿童眼镜",
                "quantity": 1,
                "reason": "UNWANTED_ITEM",
                "customer-comments": f"eyewear comment {index}",
                "店铺/站点": "SEEKWAY:US",
            }
            for index in (1, 2)
        ]
    ).to_csv(return_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(
        [
            {
                "MSKU": "GL-001",
                "店铺/站点": "SEEKWAY:US",
                "Listing": "GL001",
                "产品名称": "儿童眼镜",
                "SKU": "GL-001",
                "品类A": "眼镜",
                "品类B": "儿童眼镜",
            }
        ]
    ).to_excel(product_path, sheet_name="产品信息汇总表", index=False)
    _seed_result(
        standards,
        standard,
        return_path=return_path,
        product_path=product_path,
    )
    draft = standards.create_draft(standard["id"], "user-1")
    content = deepcopy(draft["content"])
    content["labels"][0]["keywords"] = ["pressure", "tight"]
    draft = standards.update_draft(
        draft["id"],
        draft["revision"],
        content,
        "验证原始样本对照",
        "user-1",
    )

    raw_source = next(
        source
        for source in validations.sources(draft["id"])
        if source["source_kind"] == "raw_dataset"
    )
    run = validations.create_run(
        draft["id"],
        draft["revision"],
        raw_source["result_version_id"],
        20,
        "user-1",
    )
    assert validations.claim_next() == run["id"]
    validations.run(run["id"])

    completed = validations.get(run["id"])
    assert completed["source"]["comparison_mode"] == "baseline_and_draft"
    assert completed["source"]["available_sample_count"] == 2
    assert completed["summary"]["changed_count"] == 1
    assert completed["items"][0]["baseline"]["primary_label_codes"] == [
        "EYEWEAR_FIT_TIGHT_V2_U1"
    ]
    assert completed["items"][0]["draft"]["primary_label_codes"] == [
        "EYEWEAR_LENS_QUALITY"
    ]
    assert completed["publication_ready"] is False


def test_review_upload_keeps_source_context_and_isolated_validation(tmp_path):
    from io import BytesIO

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from openpyxl import Workbook

    from web_backend.routers.classification_standards import (
        create_classification_standard_router,
    )

    standards, validations = _services(tmp_path)
    standard = next(
        item for item in standards.list() if item["standard_key"] == "eyewear"
    )
    _seed_result(standards, standard)
    draft = standards.create_draft(standard["id"], "user-1")
    content = deepcopy(draft["content"])
    content["instructions"].append("保留评论年龄原文")
    draft = standards.update_draft(
        draft["id"], draft["revision"], content, "验证样本入口", "user-1"
    )
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["评论编号", "评论标题", "评论内容", "一级品类", "ASIN"])
    sheet.append(["r1", "Great", "Never fogs", "儿童眼镜", "A1"])
    sheet.append(["r2", "Small", "Too small for my ten-year-old", "儿童眼镜", "A2"])
    sheet.append(["r3", "Shoes", "Drain quickly", "薄底水鞋", "A3"])
    output = BytesIO()
    workbook.save(output)
    app = FastAPI()
    app.include_router(
        create_classification_standard_router(
            standards,
            validations,
            lambda: {"id": "user-1"},
        )
    )
    with TestClient(app) as client:
        response = client.post(
            f"/api/classification-standard-drafts/{draft['id']}/review-validation-runs",
            data={"expected_revision": draft["revision"], "sample_size": 20},
            files={
                "file": (
                    "review.xlsx",
                    output.getvalue(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
    assert response.status_code == 201, response.text
    run = response.json()
    assert run["source"]["analysis_context"] == "review"
    assert run["source"]["skipped_category_count"] == 1
    assert run["sample_size"] == 2
    with standards.database.connect() as connection:
        row = connection.execute(
            "SELECT source_json, sample_json FROM classification_standard_validation_runs WHERE id = ?",
            (run["id"],),
        ).fetchone()
        source = json.loads(row["source_json"])
        samples = json.loads(row["sample_json"])
        assert source["analysis_context"] == "review"
        assert [sample["review_id"] for sample in samples] == ["r1", "r2"]
        assert connection.execute("SELECT COUNT(*) FROM datasets").fetchone()[0] == 2
    assert validations.claim_next() == run["id"]
    validations.run(run["id"])
    completed = validations.get(run["id"])
    assert completed["status"] == "completed"
    assert completed["publication_ready"] is False


def test_review_coverage_and_changes_include_positive_semantics():
    from return_semantics.schemas import SemanticUnit

    unit = SemanticUnit.model_validate(
        {
            "subject": "PRODUCT",
            "label_code": "TOPIC",
            "sentiment": "POSITIVE",
            "part": "LENS",
            "opinion": "Clear",
            "evidence": "Clear",
            "assertion": "AFFIRMED",
            "implicit": False,
        }
    )
    result = ValidatedClassification(
        classification_key="one",
        semantic_units=[unit],
        unknown_semantics=[],
        problem_label_codes=[],
        positive_label_codes=["TOPIC"],
        primary_label_codes=[],
        status=ProcessingStatus.AUTO_APPROVED,
        review_reasons=[],
        model_name="fake",
        prompt_version="test",
        taxonomy_version="test",
    )
    items = ClassificationStandardValidationService._comparison_items(
        [
            {
                "classification_key": "one",
                "comment": "Clear",
                "category_a": "眼镜",
                "category_b": "儿童眼镜",
                "baseline": {},
            },
        ],
        {"one": result},
    )
    summary = ClassificationStandardValidationService._summary(items)
    assert summary["coverage_rate"] == 100
    assert summary["changed_count"] == 1
    assert summary["semantic_changed_count"] == 1
    assert summary["primary_changed_count"] == 0
    assert items[0]["semantic_changed"] is True
    assert items[0]["primary_changed"] is False
    assert items[0]["draft"]["semantic_units"][0]["sentiment"] == "POSITIVE"


def test_validation_changes_separate_primary_policy_from_semantic_units():
    from return_semantics.schemas import SemanticUnit

    unit = SemanticUnit.model_validate(
        {
            "subject": "PRODUCT",
            "label_code": "TOPIC",
            "sentiment": "NEGATIVE",
            "part": "LENS",
            "opinion": "Bad vision",
            "evidence": "Bad vision",
            "assertion": "AFFIRMED",
            "implicit": False,
        }
    )
    result = ValidatedClassification(
        classification_key="one",
        semantic_units=[unit],
        unknown_semantics=[],
        problem_label_codes=["TOPIC"],
        positive_label_codes=[],
        primary_label_codes=[],
        status=ProcessingStatus.AUTO_APPROVED,
        review_reasons=[],
        model_name="fake",
        prompt_version="test",
        taxonomy_version="test",
    )
    items = ClassificationStandardValidationService._comparison_items(
        [
            {
                "classification_key": "one",
                "comment": "Bad vision",
                "category_a": "眼镜",
                "category_b": "儿童眼镜",
                "baseline": {
                    "primary_label_codes": ["TOPIC"],
                    "semantic_units": [unit.model_dump(mode="json")],
                },
            }
        ],
        {"one": result},
    )
    summary = ClassificationStandardValidationService._summary(items)

    assert items[0]["changed"] is True
    assert items[0]["semantic_changed"] is False
    assert items[0]["primary_changed"] is True
    assert summary["changed_count"] == 1
    assert summary["semantic_changed_count"] == 0
    assert summary["primary_changed_count"] == 1


def test_keyword_comparison_uses_same_taxonomy_and_cannot_approve(tmp_path):
    import pytest

    standards, validations = _services(tmp_path)
    standard = next(
        item for item in standards.list() if item["standard_key"] == "eyewear"
    )
    source_id = _seed_result(standards, standard)
    draft = standards.create_draft(standard["id"], "user-1")
    content = deepcopy(draft["content"])
    content["labels"][0]["keywords"].append("comparison")
    draft = standards.update_draft(
        draft["id"], draft["revision"], content, "对照测试", "user-1"
    )
    captured = []
    runner = validations.runner.classify_taxonomy_sample

    def capture(**kwargs):
        captured.append(kwargs["taxonomy"])
        return runner(**kwargs)

    validations.runner.classify_taxonomy_sample = capture
    run = validations.create_run(
        draft["id"],
        draft["revision"],
        source_id,
        20,
        "user-1",
        comparison_type="keyword_ab",
    )
    assert validations.claim_next() == run["id"]
    validations.run(run["id"])
    completed = validations.get(run["id"])
    assert completed["status"] == "completed", completed["error"]
    assert [taxonomy.recognition_profile for taxonomy in captured] == [
        "legacy_v3",
        "keyword_free_v1",
    ]
    assert captured[0].labels == captured[1].labels
    contract = completed["source"]["recognition_contract"]
    assert contract["baseline"]["profile"] == "legacy_v3"
    assert contract["candidate"]["profile"] == "keyword_free_v1"
    assert completed["publication_ready"] is False
    with pytest.raises(ValueError, match="仅用于诊断"):
        validations.approve(run["id"], draft["revision"], "不得代替发布", "user-1")


def test_quality_policy_warns_but_does_not_block_direct_publishing(
    tmp_path,
):
    import pytest

    from web_backend.classification_validation_quality import FACT_QUALITY_POLICY

    standards, validations = _services(tmp_path)
    standard = next(
        item for item in standards.list() if item["standard_key"] == "eyewear"
    )
    source_id = _seed_result(standards, standard)
    draft = standards.create_draft(standard["id"], "user-1")
    content = deepcopy(draft["content"])
    content["product_context"] = "质量门槛测试适用范围"
    draft = standards.update_draft(
        draft["id"], draft["revision"], content, "验证质量门槛", "user-1"
    )
    run = validations.create_run(
        draft["id"], draft["revision"], source_id, 20, "user-1"
    )
    assert validations.claim_next() == run["id"]
    validations.run(run["id"])
    with standards.database.transaction() as connection:
        raw = connection.execute(
            "SELECT source_json FROM classification_standard_validation_runs WHERE id = ?",
            (run["id"],),
        ).fetchone()
        source = json.loads(raw["source_json"])
        source["quality_policy"] = FACT_QUALITY_POLICY
        connection.execute(
            "UPDATE classification_standard_validation_runs "
            "SET source_json = ?, approved_at = 'saved-before-policy' WHERE id = ?",
            (json.dumps(source), run["id"]),
        )
    assert validations.get(run["id"])["publication_ready"] is False
    with pytest.raises(ValueError, match="质量门槛未通过"):
        validations.approve(run["id"], draft["revision"], "不能绕过", "user-1")
    published = standards.publish_draft(
        draft["id"], draft["revision"], "用户决定直接发布", "user-1"
    )
    assert published["version_no"] == 2
