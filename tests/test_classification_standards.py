from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from return_semantics.prompt import recognition_fingerprint
from return_semantics.schemas import TaxonomyConfig
from web_backend.classification_standard_service import (
    CLASSIFICATION_STANDARD_CATEGORY_NAMES_MIGRATION,
    CLASSIFICATION_STANDARD_NAME_MIGRATION,
    CLASSIFICATION_STANDARD_RULES_MIGRATION,
    ClassificationStandardConflict,
    ClassificationStandardNotFound,
    ClassificationStandardService,
    ClassificationStandardValidationError,
)
from web_backend.classification_validation_quality import FACT_QUALITY_POLICY
from web_backend.database import Database
from web_backend.routers.classification_standards import (
    create_classification_standard_router,
)

_CandidateContext = tuple[ClassificationStandardService, str, dict[str, Any]]


def _service(tmp_path: Path) -> ClassificationStandardService:
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
    return ClassificationStandardService(database)


@pytest.fixture
def eyewear_candidate_context(
    tmp_path: Path,
) -> _CandidateContext:
    service = _service(tmp_path)
    standard = next(
        item for item in service.list() if item["standard_key"] == "eyewear"
    )
    standard_id = str(standard["id"])
    return service, standard_id, deepcopy(service.get(standard_id)["snapshot"])


def _mark_sample_validation_ready(
    service: ClassificationStandardService,
    draft: dict[str, object],
) -> str:
    run_id = f"standard-validation-ready-{draft['id']}-{draft['revision']}"
    with service.database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO classification_standard_validation_runs(
                id, standard_id, draft_id, draft_revision,
                base_version_id, source_result_version_id,
                config_version_id, status, stage, sample_size,
                processed_count, snapshot_json, source_json, sample_json,
                created_by, created_at, completed_at,
                approved_by, approved_at, approval_note
            ) VALUES (?, ?, ?, ?, ?, 'source-version', 'config-version',
                      'completed', 'completed', 1, 1, '{}', ?, '[]',
                      'user-1', 'now', 'now', 'user-1', 'now', '测试确认')
            """,
            (
                run_id,
                draft["standard_id"],
                draft["id"],
                draft["revision"],
                draft["base_version_id"],
                json.dumps(
                    {
                        "comparison_type": "standard_version",
                        "recognition_contract": {
                            "candidate": {
                                "fingerprint": recognition_fingerprint(
                                    TaxonomyConfig.model_validate(
                                        draft["snapshot"]["taxonomy"]
                                    )
                                )
                            }
                        },
                    }
                ),
            ),
        )
    return run_id


def test_active_registry_requires_initialized_database(tmp_path: Path) -> None:
    database = Database(tmp_path / "app.db")
    service = ClassificationStandardService(database)

    with pytest.raises(RuntimeError, match="分类标准数据表尚未初始化"):
        service.active_registry()


def test_draft_roundtrip_preserves_new_label_claim_bindings(tmp_path: Path) -> None:
    from web_backend.api_schemas import ClassificationStandardDraftUpdateRequest

    service = _service(tmp_path)
    standard = next(
        item for item in service.list() if item["standard_key"] == "footwear"
    )
    draft = service.create_draft(standard["id"], "user-1")
    content = service._editable_content(draft["snapshot"])
    label = deepcopy(
        next(
            item
            for item in content["labels"]
            if item["code"] == "FUNCTION_QUICK_DRY_U1"
        )
    )
    label["code"] = "TEST_DRYING_VARIANT"
    content["labels"].append(label)
    request = ClassificationStandardDraftUpdateRequest(
        expected_revision=draft["revision"],
        content=content,
        change_reason="验证声明引用",
    )
    updated = service.update_draft(
        draft["id"],
        request.expected_revision,
        request.content.model_dump(),
        request.change_reason,
        "user-1",
    )
    actual = next(
        item
        for item in updated["snapshot"]["taxonomy"]["labels"]
        if item["code"] == label["code"]
    )
    assert actual["allowed_claim_ids"] == ["CLM_DRY_01"]
    exported = service._editable_content(updated["snapshot"])
    assert next(item for item in exported["labels"] if item["code"] == label["code"])[
        "allowed_claim_ids"
    ] == ["CLM_DRY_01"]


def test_existing_category_config_is_imported_as_published_standards(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)

    standards = service.list()
    with service.database.connect() as connection:
        migration = connection.execute("SELECT * FROM app_migrations").fetchone()

    assert len(standards) == 4
    assert sum(item["category_count"] for item in standards) == 24
    assert sum(item["label_count"] for item in standards) == 181
    assert {item["standard_key"] for item in standards} == {
        "eyewear",
        "footwear",
        "gloves",
        "headwear",
    }
    assert all(item["status"] == "active" for item in standards)
    assert {item["name"] for item in standards} == {
        "眼镜用户反馈语义标准",
        "鞋履用户反馈语义标准",
        "手套用户反馈语义标准",
        "帽类用户反馈语义标准",
    }
    assert migration is not None
    assert migration["migration_id"] == ("20260824_01_seed_classification_standards")
    assert migration["status"] == "applied"
    assert len(migration["checksum"]) == 64


def test_legacy_gloves_standard_name_is_migrated_without_changing_version(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    gloves = next(item for item in service.list() if item["standard_key"] == "gloves")
    version_id = gloves["standard_version_id"]
    draft = service.create_draft(gloves["id"], "user-1")
    with service.database.transaction() as connection:
        connection.execute(
            """
            UPDATE classification_standards
            SET name = '手套退货问题标准' WHERE id = ?
            """,
            (gloves["id"],),
        )
        snapshot = draft["snapshot"]
        snapshot["name"] = "手套退货问题标准"
        connection.execute(
            """
            UPDATE classification_standard_drafts
            SET snapshot_json = ? WHERE id = ?
            """,
            (json.dumps(snapshot, ensure_ascii=False), draft["id"]),
        )
        connection.execute(
            "DELETE FROM app_migrations WHERE migration_id = ?",
            (CLASSIFICATION_STANDARD_NAME_MIGRATION,),
        )

    restored = ClassificationStandardService(service.database)
    migrated = restored.get(gloves["id"])
    migrated_draft = restored.get_draft(draft["id"])
    with service.database.connect() as connection:
        migration = connection.execute(
            "SELECT status FROM app_migrations WHERE migration_id = ?",
            (CLASSIFICATION_STANDARD_NAME_MIGRATION,),
        ).fetchone()

    assert migrated["name"] == "手套用户反馈语义标准"
    assert migrated["standard_version_id"] == version_id
    assert migrated_draft["snapshot"]["name"] == "手套用户反馈语义标准"
    assert migration["status"] == "applied"


def test_legacy_category_standard_names_are_migrated_without_changing_versions(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    standards = {
        item["standard_key"]: item
        for item in service.list()
        if item["standard_key"] != "gloves"
    }
    legacy_names = {
        "eyewear": "眼镜退货问题标准",
        "footwear": "鞋履退货问题标准",
        "headwear": "帽类退货问题标准",
    }
    drafts = {
        key: service.create_draft(item["id"], "user-1")
        for key, item in standards.items()
    }
    with service.database.transaction() as connection:
        for key, standard in standards.items():
            connection.execute(
                "UPDATE classification_standards SET name = ? WHERE id = ?",
                (legacy_names[key], standard["id"]),
            )
            snapshot = drafts[key]["snapshot"]
            snapshot["name"] = legacy_names[key]
            connection.execute(
                """
                UPDATE classification_standard_drafts
                SET snapshot_json = ? WHERE id = ?
                """,
                (json.dumps(snapshot, ensure_ascii=False), drafts[key]["id"]),
            )
        connection.execute(
            "DELETE FROM app_migrations WHERE migration_id = ?",
            (CLASSIFICATION_STANDARD_CATEGORY_NAMES_MIGRATION,),
        )

    restored = ClassificationStandardService(service.database)
    expected_names = {
        "eyewear": "眼镜用户反馈语义标准",
        "footwear": "鞋履用户反馈语义标准",
        "headwear": "帽类用户反馈语义标准",
    }
    for key, standard in standards.items():
        migrated = restored.get(standard["id"])
        migrated_draft = restored.get_draft(drafts[key]["id"])
        assert migrated["name"] == expected_names[key]
        assert migrated["standard_version_id"] == standard["standard_version_id"]
        assert migrated_draft["snapshot"]["name"] == expected_names[key]
    with service.database.connect() as connection:
        migration = connection.execute(
            "SELECT status FROM app_migrations WHERE migration_id = ?",
            (CLASSIFICATION_STANDARD_CATEGORY_NAMES_MIGRATION,),
        ).fetchone()
    assert migration["status"] == "applied"


def test_existing_standards_are_baselined_without_reimport(tmp_path: Path) -> None:
    service = _service(tmp_path)
    before = {
        item["standard_key"]: item["standard_version_id"] for item in service.list()
    }
    with service.database.transaction() as connection:
        connection.execute("DELETE FROM app_migrations")
        connection.execute(
            """
            UPDATE classification_standards
            SET name = '用户维护的标准'
            WHERE standard_key = 'footwear'
            """
        )

    restored = ClassificationStandardService(service.database)

    after = {
        item["standard_key"]: item["standard_version_id"] for item in restored.list()
    }
    footwear = next(
        item for item in restored.list() if item["standard_key"] == "footwear"
    )
    with service.database.connect() as connection:
        migration = connection.execute("SELECT * FROM app_migrations").fetchone()
    assert after == before
    assert footwear["name"] == "用户维护的标准"
    assert migration is not None
    assert migration["status"] == "baselined"


def test_standard_bootstrap_is_idempotent_and_registry_uses_snapshots(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    initial_versions = {
        item["standard_key"]: item["standard_version_id"] for item in service.list()
    }

    service.ensure_bootstrapped()
    registry = service.active_registry()

    assert {
        item["standard_key"]: item["standard_version_id"] for item in service.list()
    } == initial_versions
    eyewear = registry.resolve("眼镜", "儿童眼镜")
    assert eyewear is not None
    assert eyewear.taxonomy is not None
    assert len(eyewear.taxonomy.labels) == 39


def test_existing_snapshot_receives_configured_validation_rules(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    footwear = next(
        item for item in service.list() if item["standard_key"] == "footwear"
    )
    version_id = footwear["standard_version_id"]
    with service.database.transaction() as connection:
        row = connection.execute(
            """
            SELECT snapshot_json FROM classification_standard_versions
            WHERE id = ?
            """,
            (version_id,),
        ).fetchone()
        snapshot = json.loads(row["snapshot_json"])
        snapshot["taxonomy"].pop("validation_rules", None)
        encoded = json.dumps(
            snapshot,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        connection.execute(
            """
            UPDATE classification_standard_versions
            SET snapshot_json = ?, content_hash = ? WHERE id = ?
            """,
            (
                encoded,
                hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
                version_id,
            ),
        )
        connection.execute(
            "DELETE FROM app_migrations WHERE migration_id = ?",
            (CLASSIFICATION_STANDARD_RULES_MIGRATION,),
        )

    restored = ClassificationStandardService(service.database)
    taxonomy = restored.taxonomy_for_version(version_id)

    assert taxonomy.validation_rules.opposite_reason_labels["APPAREL_TOO_SMALL"] == [
        "FIT_TOO_LARGE_U1",
        "FIT_TOO_LONG_U1",
        "FIT_TOO_LOOSE_WIDE_U1",
    ]
    assert taxonomy.validation_rules.evidence_requirements[0].label_code == (
        "QUALITY_CHEAP_MATERIAL_U1"
    )


def test_current_version_for_standard_requires_active_published_version(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    footwear = next(
        item for item in service.list() if item["standard_key"] == "footwear"
    )

    version = service.current_version_for_standard(footwear["id"])

    assert version["id"] == footwear["standard_version_id"]
    assert version["status"] == "published"

    draft = service.create_standard(
        name="箱包退货问题标准",
        product_context="户外背包",
        category_a="箱包",
        category_b="户外背包",
        actor_id="user-1",
    )
    with pytest.raises(ClassificationStandardNotFound):
        service.current_version_for_standard(str(draft["standard_id"]))


def test_draft_does_not_affect_runtime_until_published(tmp_path: Path) -> None:
    service = _service(tmp_path)
    standard = next(
        item for item in service.list() if item["standard_key"] == "eyewear"
    )
    original_version_id = standard["standard_version_id"]
    draft = service.create_draft(standard["id"], "user-1")
    content = deepcopy(draft["content"])
    assert draft["validation"]["blocking"] == ["草稿与当前已发布版本没有差异"]
    content["product_context"] = "儿童及骑行眼镜"
    content["labels"][0]["keywords"] = ["pressure", "tight"]

    updated = service.update_draft(
        draft["id"],
        draft["revision"],
        content,
        "调整眼镜分类边界",
        "user-1",
    )

    assert updated["revision"] == 2
    assert updated["validation"]["blocking"] == []
    assert updated["diff"]["has_changes"] is True
    assert len(updated["diff"]["modified_labels"]) == 1
    assert updated["diff"]["semantic_label_changes"] == []
    active_before_publish = service.active_registry().resolve("眼镜", "儿童眼镜")
    assert active_before_publish is not None
    assert active_before_publish.taxonomy is not None
    assert active_before_publish.taxonomy.product_context != "儿童及骑行眼镜"

    _mark_sample_validation_ready(service, updated)
    published = service.publish_draft(
        draft["id"],
        updated["revision"],
        "发布眼镜标准 V2",
        "user-1",
    )

    assert published["version_no"] == 2
    assert published["standard_version_id"] != original_version_id
    assert service.get_version(original_version_id)["version_no"] == 1
    active_after_publish = service.active_registry().resolve("眼镜", "儿童眼镜")
    assert active_after_publish is not None
    assert active_after_publish.taxonomy is not None
    assert active_after_publish.taxonomy.product_context == "儿童及骑行眼镜"
    assert active_after_publish.taxonomy.labels[0].keywords == ["pressure", "tight"]


def test_published_label_semantics_require_a_new_code(tmp_path: Path) -> None:
    service = _service(tmp_path)
    standard = next(
        item for item in service.list() if item["standard_key"] == "eyewear"
    )
    draft = service.create_draft(standard["id"], "user-1")
    content = deepcopy(draft["content"])
    content["labels"][0]["description"] = "改变已发布标签的语义"

    updated = service.update_draft(
        draft["id"],
        draft["revision"],
        content,
        "尝试同码改义",
        "user-1",
    )

    assert updated["diff"]["semantic_label_changes"] == ["EYEWEAR_FIT_TIGHT_V2_U1"]
    assert any(
        "已发布标签不能同码改义" in item for item in updated["validation"]["blocking"]
    )


def test_candidate_validation_preserves_multi_issue_order(
    eyewear_candidate_context: _CandidateContext,
) -> None:
    service, standard_id, base = eyewear_candidate_context
    candidate = deepcopy(base)
    candidate["name"] = "   "
    candidate["variants"] = []
    taxonomy = candidate["taxonomy"]
    taxonomy["product_context"] = "   "
    taxonomy["instructions"] = []
    taxonomy["allowed_parts"] = []
    taxonomy["labels"][0]["description"] = "改变已发布标签的语义"
    changed_code = taxonomy["labels"][0]["code"]
    expected_blocking = [
        "标准名称不能为空",
        "适用商品说明不能为空",
        "至少需要一条分类规则",
        "至少需要一个适用品类",
        "证据部位必须保留“未指定部位”",
        f"已发布标签不能同码改义：{changed_code}；请停用旧标签并创建新编码",
    ]

    validation = service._validate_candidate(standard_id, candidate, base)

    assert validation == {
        "blocking": expected_blocking,
        "warnings": ["将移除 3 个适用品类，新任务不再匹配这些品类"],
        "issues": [
            {"kind": "invalid_structure", "message": message, "field": None}
            for message in expected_blocking
        ],
    }


def test_candidate_validation_keeps_v1_and_v2_policy_boundaries(
    eyewear_candidate_context: _CandidateContext,
) -> None:
    service, standard_id, base = eyewear_candidate_context
    legacy_candidate = deepcopy(base)
    legacy_candidate["name"] = f"{legacy_candidate['name']} V2"
    legacy_candidate["taxonomy"]["validation_rules"]["allowed_groups"] = ["自定义分组"]

    legacy_validation = service._validate_candidate(
        standard_id,
        legacy_candidate,
        base,
    )

    assert legacy_validation["blocking"][0] == "统一标准必须使用规定的七个业务分组"

    hierarchical_candidate = deepcopy(base)
    hierarchical_candidate["name"] = f"{hierarchical_candidate['name']} V2"
    hierarchical_candidate["taxonomy"] = {
        "version": "test-hierarchy-v2",
        "structure_version": 2,
        "recognition_profile": "semantic_v1",
        "agent_family": hierarchical_candidate["agent_family"],
        "product_context": "测试层级分类",
        "instructions": ["按层级判断"],
        "allowed_parts": ["UNSPECIFIED"],
        "categories": [
            {"code": "TEST_FUNCTION", "name": "体验"},
            {"code": "TEST_QUALITY", "name": "体验"},
        ],
        "labels": [
            {
                "code": "TEST_HIERARCHY_COLD",
                "name": "不保暖",
                "group": "体验",
                "parent_code": "TEST_FUNCTION",
                "description": "保暖不足",
                "allowed_sentiments": ["NEGATIVE"],
            },
            {
                "code": "TEST_HIERARCHY_FAULT",
                "name": "损坏",
                "group": "体验",
                "parent_code": "TEST_QUALITY",
                "description": "产品损坏",
                "allowed_sentiments": ["NEGATIVE"],
            },
        ],
        "validation_rules": {"allowed_groups": ["自定义分组"]},
    }

    hierarchical_validation = service._validate_candidate(
        standard_id,
        hierarchical_candidate,
        base,
    )

    assert hierarchical_validation["blocking"] == ["同一父节点下的分类和标签不能重名"]
    assert hierarchical_validation["issues"] == [
        {
            "kind": "invalid_structure",
            "message": "同一父节点下的分类和标签不能重名",
            "field": None,
        }
    ]


def test_publish_allows_direct_release_without_sample_validation(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    standard = next(
        item for item in service.list() if item["standard_key"] == "eyewear"
    )
    draft = service.create_draft(standard["id"], "user-1")
    content = deepcopy(draft["content"])
    content["product_context"] = "儿童及骑行眼镜"
    updated = service.update_draft(
        draft["id"],
        draft["revision"],
        content,
        "调整适用范围",
        "user-1",
    )

    published = service.publish_draft(
        draft["id"],
        updated["revision"],
        "直接发布新版本",
        "user-1",
    )

    assert published["version_no"] == 2
    with service.database.connect() as connection:
        audit = connection.execute(
            "SELECT after_json FROM audit_logs WHERE action = 'publish' "
            "ORDER BY created_at DESC, id DESC LIMIT 1"
        ).fetchone()
    after = json.loads(audit["after_json"])
    assert after["publication_mode"] == "direct"
    assert after["validation_run_id"] is None


def test_publish_rejects_invalid_test_evidence_but_keeps_direct_path(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    standard = next(
        item for item in service.list() if item["standard_key"] == "eyewear"
    )
    draft = service.create_draft(standard["id"], "user-1")
    content = deepcopy(draft["content"])
    content["product_context"] = "儿童及骑行眼镜"
    updated = service.update_draft(
        draft["id"],
        draft["revision"],
        content,
        "调整适用范围",
        "user-1",
    )

    with pytest.raises(ClassificationStandardValidationError) as exc_info:
        service.publish_draft(
            draft["id"],
            updated["revision"],
            "错误地关联测试",
            "user-1",
            "missing-validation-run",
        )
    assert exc_info.value.validation["blocking"] == ["所选测试记录不存在，请刷新后重试"]

    published = service.publish_draft(
        draft["id"],
        updated["revision"],
        "改为直接发布",
        "user-1",
    )
    assert published["version_no"] == 2


def test_glove_draft_accepts_detailed_hand_parts(tmp_path: Path) -> None:
    service = _service(tmp_path)
    standard = next(item for item in service.list() if item["standard_key"] == "gloves")
    draft = service.create_draft(standard["id"], "user-1")
    content = deepcopy(draft["content"])
    content["allowed_parts"].extend(
        ["BACK_OF_HAND", "FINGER_GUSSET", "THUMB_WEB", "KNUCKLE_GUARD"]
    )

    updated = service.update_draft(
        draft["id"],
        draft["revision"],
        content,
        "补充手套细分部位",
        "user-1",
    )

    assert updated["validation"]["blocking"] == []
    assert {
        "BACK_OF_HAND",
        "FINGER_GUSSET",
        "THUMB_WEB",
        "KNUCKLE_GUARD",
    }.issubset(updated["content"]["allowed_parts"])
    assert (
        service.get(standard["id"])["standard_version_id"]
        == (standard["standard_version_id"])
    )


def test_historical_version_restores_as_new_draft_and_publishes_v3(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    standard = next(
        item for item in service.list() if item["standard_key"] == "eyewear"
    )
    version_v1 = service.get_version(standard["standard_version_id"])
    draft = service.create_draft(standard["id"], "user-1")
    content = deepcopy(draft["content"])
    content["product_context"] = "V2 适用范围"
    updated = service.update_draft(
        draft["id"],
        draft["revision"],
        content,
        "发布 V2",
        "user-1",
    )
    _mark_sample_validation_ready(service, updated)
    published_v2 = service.publish_draft(
        draft["id"],
        updated["revision"],
        "发布 V2",
        "user-1",
    )
    version_v2_id = published_v2["standard_version_id"]

    app = FastAPI()
    app.include_router(
        create_classification_standard_router(
            service,
            validation_service=object(),
            current_user=lambda: {"id": "user-1"},
        )
    )
    with TestClient(app) as client:
        current_response = client.post(
            f"/api/classification-standard-versions/{version_v2_id}/restore-draft"
        )
        assert current_response.status_code == 400
        assert current_response.json()["detail"] == "当前版本无需恢复"

        restore_response = client.post(
            f"/api/classification-standard-versions/{version_v1['id']}/restore-draft"
        )
        assert restore_response.status_code == 201, restore_response.text
        restored = restore_response.json()

        duplicate_response = client.post(
            f"/api/classification-standard-versions/{version_v1['id']}/restore-draft"
        )
        assert duplicate_response.status_code == 409

    assert restored["base_version_id"] == version_v2_id
    assert restored["base_version_no"] == 2
    assert restored["change_reason"] == "恢复 V1 的内容"
    assert (
        restored["content"]["product_context"]
        == (version_v1["snapshot"]["taxonomy"]["product_context"])
    )
    assert restored["validation"]["blocking"] == []
    assert service.get(standard["id"])["standard_version_id"] == version_v2_id

    _mark_sample_validation_ready(service, restored)
    published_v3 = service.publish_draft(
        restored["id"],
        restored["revision"],
        "恢复 V1 并发布为 V3",
        "user-1",
    )

    assert published_v3["version_no"] == 3
    assert service.get_version(version_v1["id"])["version_no"] == 1
    assert service.get_version(version_v2_id)["version_no"] == 2
    assert (
        published_v3["snapshot"]["taxonomy"]["product_context"]
        == (version_v1["snapshot"]["taxonomy"]["product_context"])
    )


def test_draft_validation_blocks_global_category_conflicts(tmp_path: Path) -> None:
    service = _service(tmp_path)
    standard = next(
        item for item in service.list() if item["standard_key"] == "eyewear"
    )
    draft = service.create_draft(standard["id"], "user-1")
    content = deepcopy(draft["content"])
    content["variants"][0]["category_a"] = "水鞋"
    content["variants"][0]["category_b"] = "薄底水鞋"

    updated = service.update_draft(
        draft["id"],
        draft["revision"],
        content,
        "制造全局冲突",
        "user-1",
    )

    assert any("品类映射重复" in item for item in updated["validation"]["blocking"])


def test_draft_uses_optimistic_revision_and_can_be_discarded(tmp_path: Path) -> None:
    service = _service(tmp_path)
    standard = service.list()[0]
    draft = service.create_draft(standard["id"], "user-1")
    content = deepcopy(draft["content"])
    content["product_context"] = "更新后的适用范围"
    updated = service.update_draft(
        draft["id"],
        draft["revision"],
        content,
        "更新范围",
        "user-1",
    )

    with pytest.raises(ClassificationStandardConflict):
        service.update_draft(
            draft["id"],
            draft["revision"],
            content,
            "过期修改",
            "user-1",
        )

    service.discard_draft(
        draft["id"],
        updated["revision"],
        "放弃测试草稿",
        "user-1",
    )
    assert service.draft_for_standard(standard["id"]) is None


def test_new_standard_stays_inactive_until_first_publish(tmp_path: Path) -> None:
    service = _service(tmp_path)
    draft = service.create_standard(
        name="户外背包退货分类标准",
        product_context="户外及通勤背包",
        category_a="箱包",
        category_b="户外背包",
        actor_id="user-1",
    )

    assert draft["is_new"] is True
    assert draft["base_version_no"] == 0
    assert service.get(draft["standard_id"])["status"] == "inactive"
    assert service.versions(draft["standard_id"]) == []
    assert service.active_registry().resolve("箱包", "户外背包") is None

    content = deepcopy(draft["content"])
    content["product_context"] = "户外、通勤及旅行背包"
    partial = service.update_draft(
        draft["id"],
        draft["revision"],
        content,
        "先补充适用范围",
        "user-1",
    )
    assert "至少需要一条分类规则" in partial["validation"]["blocking"]
    assert "至少需要一个问题标签" in partial["validation"]["blocking"]

    content = deepcopy(partial["content"])
    content["instructions"] = ["识别背包结构、容量和佩戴问题"]
    content["labels"] = [
        {
            "code": "BACKPACK_STRUCTURE_DAMAGE",
            "name": "结构损坏",
            "group": "质量与耐用",
            "description": "背包主体、拉链或缝线发生损坏",
            "allowed_sentiments": ["NEGATIVE"],
        }
    ]
    updated = service.update_draft(
        draft["id"],
        partial["revision"],
        content,
        "建立背包分类标准",
        "user-1",
    )
    assert updated["validation"]["blocking"] == []
    _mark_sample_validation_ready(service, updated)

    published = service.publish_draft(
        draft["id"],
        updated["revision"],
        "首次发布背包标准",
        "user-1",
    )

    assert published["status"] == "active"
    assert published["version_no"] == 1
    assert len(service.versions(draft["standard_id"])) == 1
    capability = service.active_registry().resolve("箱包", "户外背包")
    assert capability is not None
    assert capability.agent_family == "户外背包退货智能体"
    assert capability.taxonomy is not None
    assert capability.taxonomy.agent_family == "户外背包退货智能体"


def test_discarding_new_standard_removes_unpublished_entry(tmp_path: Path) -> None:
    service = _service(tmp_path)
    draft = service.create_standard(
        name="测试分类标准",
        product_context="测试商品",
        category_a="测试品类 A",
        category_b="测试品类 B",
        actor_id="user-1",
    )

    service.discard_draft(
        draft["id"],
        draft["revision"],
        "放弃未发布标准",
        "user-1",
    )

    assert all(item["id"] != draft["standard_id"] for item in service.list())


def test_delete_unpublished_standard_removes_it_permanently(tmp_path: Path) -> None:
    service = _service(tmp_path)
    draft = service.create_standard(
        name="临时分类标准",
        product_context="临时商品",
        category_a="临时品类 A",
        category_b="临时品类 B",
        actor_id="user-1",
    )

    result = service.delete_standard(draft["standard_id"], "user-1")

    assert result["mode"] == "deleted"
    assert all(item["id"] != draft["standard_id"] for item in service.list())


def test_delete_published_standard_deactivates_without_removing_versions(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    standard = next(
        item for item in service.list() if item["standard_key"] == "eyewear"
    )
    version_id = standard["standard_version_id"]

    result = service.delete_standard(standard["id"], "user-1")

    assert result["mode"] == "deactivated"
    assert service.get(standard["id"])["status"] == "inactive"
    assert service.get_version(version_id)["version_no"] == 1
    assert service.active_registry().resolve("眼镜", "儿童眼镜") is None


def test_new_standard_api_creates_an_unpublished_draft(tmp_path: Path) -> None:
    service = _service(tmp_path)
    app = FastAPI()
    app.include_router(
        create_classification_standard_router(
            service,
            validation_service=object(),
            current_user=lambda: {"id": "user-1"},
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/classification-standards",
            json={
                "name": "户外背包退货分类标准",
                "product_context": "户外及通勤背包",
                "category_a": "箱包",
                "category_b": "户外背包",
            },
        )

    assert response.status_code == 201, response.text
    draft = response.json()
    assert draft["is_new"] is True
    assert service.get(draft["standard_id"])["status"] == "inactive"

    with TestClient(app) as client:
        partial_response = client.patch(
            f"/api/classification-standard-drafts/{draft['id']}",
            json={
                "expected_revision": draft["revision"],
                "content": {
                    **draft["content"],
                    "product_context": "更新后的适用范围",
                },
                "change_reason": "分阶段维护草稿",
            },
        )
    assert partial_response.status_code == 200, partial_response.text
    assert "至少需要一个问题标签" in partial_response.json()["validation"]["blocking"]

    with TestClient(app) as client:
        delete_response = client.delete(
            f"/api/classification-standards/{draft['standard_id']}"
        )
    assert delete_response.status_code == 200, delete_response.text
    assert delete_response.json()["mode"] == "deleted"


def test_draft_api_supports_edit_validation_and_conflict(tmp_path: Path) -> None:
    service = _service(tmp_path)
    standard = next(
        item for item in service.list() if item["standard_key"] == "eyewear"
    )
    app = FastAPI()
    app.include_router(
        create_classification_standard_router(
            service,
            validation_service=object(),
            current_user=lambda: {"id": "user-1"},
        )
    )

    with TestClient(app) as client:
        created_response = client.post(
            f"/api/classification-standards/{standard['id']}/draft"
        )
        assert created_response.status_code == 201, created_response.text
        draft = created_response.json()
        content = deepcopy(draft["content"])
        content["product_context"] = "儿童及运动眼镜"

        updated_response = client.patch(
            f"/api/classification-standard-drafts/{draft['id']}",
            json={
                "expected_revision": draft["revision"],
                "content": content,
                "change_reason": "补充适用范围",
            },
        )
        assert updated_response.status_code == 200, updated_response.text
        updated = updated_response.json()
        assert updated["revision"] == draft["revision"] + 1

        stale_response = client.patch(
            f"/api/classification-standard-drafts/{draft['id']}",
            json={
                "expected_revision": draft["revision"],
                "content": content,
                "change_reason": "过期提交",
            },
        )
        assert stale_response.status_code == 409

        validation_response = client.post(
            f"/api/classification-standard-drafts/{draft['id']}/validate",
            json={"expected_revision": updated["revision"]},
        )
        assert validation_response.status_code == 200, validation_response.text
        assert validation_response.json()["validation"]["blocking"] == []

        publish_response = client.post(
            f"/api/classification-standard-drafts/{draft['id']}/publish",
            json={"expected_revision": updated["revision"], "reason": "   "},
        )
        assert publish_response.status_code == 400
        assert publish_response.json()["detail"] == "变更说明不能为空"

        direct_publish_response = client.post(
            f"/api/classification-standard-drafts/{draft['id']}/publish",
            json={
                "expected_revision": updated["revision"],
                "reason": "用户确认直接发布",
                "validation_run_id": None,
            },
        )
        assert direct_publish_response.status_code == 200
        assert direct_publish_response.json()["version_no"] == 2


def test_published_version_export_can_only_import_into_draft(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    standard = next(
        item for item in service.list() if item["standard_key"] == "footwear"
    )
    draft = service.create_draft(standard["id"], "user-1")
    app = FastAPI()
    app.include_router(
        create_classification_standard_router(
            service,
            validation_service=object(),
            current_user=lambda: {"id": "user-1"},
        )
    )

    with TestClient(app) as client:
        exported_response = client.get(
            "/api/classification-standard-versions/"
            f"{standard['standard_version_id']}/export"
        )
        assert exported_response.status_code == 200, exported_response.text
        assert "attachment" in exported_response.headers["content-disposition"]
        document = exported_response.json()
        document["snapshot"]["standard_key"] = "external_standard"
        document["snapshot"]["agent_family"] = "外部智能体"
        document["snapshot"]["logic_version"] = "external-logic-v9"
        document["snapshot"]["taxonomy"]["agent_family"] = "外部智能体"
        document["snapshot"]["taxonomy"]["product_context"] = "导入后的适用范围"
        encoded = json.dumps(
            document["snapshot"],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        document["content_hash"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()

        imported_response = client.post(
            f"/api/classification-standard-drafts/{draft['id']}/import",
            json={
                "expected_revision": draft["revision"],
                "document": document,
                "change_reason": "从受控 JSON 导入",
            },
        )
        assert imported_response.status_code == 200, imported_response.text
        imported = imported_response.json()
        assert imported["snapshot"]["standard_key"] == "footwear"
        assert imported["snapshot"]["agent_family"] != "外部智能体"
        assert imported["snapshot"]["logic_version"] != "external-logic-v9"
        assert imported["content"]["product_context"] == "导入后的适用范围"
        assert (
            service.get(standard["id"])["standard_version_id"]
            == (standard["standard_version_id"])
        )
        published = service.get_version(standard["standard_version_id"])
        assert published["snapshot"]["taxonomy"]["product_context"] != (
            "导入后的适用范围"
        )

        document["snapshot"]["name"] = "未更新哈希的篡改"
        invalid_response = client.post(
            f"/api/classification-standard-drafts/{draft['id']}/import",
            json={
                "expected_revision": imported["revision"],
                "document": document,
                "change_reason": "篡改文件",
            },
        )
        assert invalid_response.status_code == 400
        assert invalid_response.json()["detail"] == "导入文件内容哈希校验失败"


def test_draft_validation_reports_blank_business_fields(tmp_path: Path) -> None:
    service = _service(tmp_path)
    standard = service.list()[0]
    draft = service.create_draft(standard["id"], "user-1")
    content = deepcopy(draft["content"])
    content["name"] = "   "
    content["labels"][0]["description"] = "   "

    updated = service.update_draft(
        draft["id"],
        draft["revision"],
        content,
        "验证空白字段",
        "user-1",
    )

    assert "标准名称不能为空" in updated["validation"]["blocking"]
    assert not any(
        issue.get("field") == "description" for issue in updated["validation"]["issues"]
    )
    assert any(
        "已发布标签不能同码改义" in item for item in updated["validation"]["blocking"]
    )


def test_tested_publish_records_quality_result_without_turning_it_into_a_gate(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    standard = next(
        item for item in service.list() if item["standard_key"] == "eyewear"
    )
    draft = service.create_draft(standard["id"], "user-1")
    content = deepcopy(draft["content"])
    comment = (
        "The frame stays comfortable through a full school day and does not "
        "press against the nose or the sides of the head."
    )
    content["labels"][0]["examples"] = [
        {
            "text": comment,
            "applies": True,
            "sentiment": "NEGATIVE",
            "explanation": "验证边界",
        }
    ]
    updated = service.update_draft(
        draft["id"],
        draft["revision"],
        content,
        "补充边界示例",
        "user-1",
    )
    run_id = _mark_sample_validation_ready(service, updated)
    with service.database.transaction() as connection:
        source = json.loads(
            connection.execute(
                "SELECT source_json FROM classification_standard_validation_runs "
                "WHERE id = ?",
                (run_id,),
            ).fetchone()["source_json"]
        )
        source["quality_policy"] = FACT_QUALITY_POLICY
        connection.execute(
            "UPDATE classification_standard_validation_runs "
            "SET source_json = ?, sample_json = ? "
            "WHERE id = ?",
            (
                json.dumps(source),
                json.dumps(
                    [
                        {
                            "review_id": "review-1234-abcd",
                            "comment": comment,
                        }
                    ]
                ),
                run_id,
            ),
        )

    published = service.publish_draft(
        updated["id"],
        updated["revision"],
        "验收测试后发布",
        "user-1",
        run_id,
    )

    with service.database.connect() as connection:
        validation = connection.execute(
            "SELECT published_version_id FROM classification_standard_validation_runs "
            "WHERE id = ?",
            (run_id,),
        ).fetchone()
        audit = connection.execute(
            "SELECT after_json FROM audit_logs WHERE action = 'publish' "
            "ORDER BY created_at DESC, id DESC LIMIT 1"
        ).fetchone()
    after = json.loads(audit["after_json"])
    assert validation["published_version_id"] == published["standard_version_id"]
    assert after["publication_mode"] == "validated"
    assert after["validation_run_id"] == run_id
    assert after["validation_quality_passed"] is False
