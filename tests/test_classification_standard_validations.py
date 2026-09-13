from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pandas as pd

from return_semantics.pipeline import PipelineRun
from return_semantics.schemas import ProcessingStatus, ValidatedClassification
from web_backend.classification_standard_service import ClassificationStandardService
from web_backend.classification_standard_validation_service import (
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
    assert items[0]["draft"]["semantic_units"][0]["sentiment"] == "POSITIVE"


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


def test_quality_policy_blocks_approval_and_publishing_even_with_saved_approval(
    tmp_path,
):
    import pytest

    from web_backend.classification_standard_service import (
        ClassificationStandardValidationError,
    )
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
    with pytest.raises(ClassificationStandardValidationError):
        standards.publish_draft(draft["id"], draft["revision"], "不能绕过", "user-1")
