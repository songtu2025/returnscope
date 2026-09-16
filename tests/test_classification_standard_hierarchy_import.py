from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from io import BytesIO
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import Workbook
from test_classification_result_pool import _publish, _seed_result_context
from test_classification_standards import _service

from return_semantics.schemas import TaxonomyConfig
from return_semantics.taxonomy_hierarchy import label_path
from web_backend.api_schemas import ClassificationStandardDraftContentRequest
from web_backend.classification_standard_excel import preview_excel
from web_backend.classification_standard_service import (
    ClassificationStandardNotFound,
    ClassificationStandardService,
)
from web_backend.database import Database
from web_backend.routers.classification_standards import (
    create_classification_standard_router,
)

MAPPING = {
    "hierarchy_columns": ["一级", "二级", "三级"],
    "source_label_column": "原始说法",
    "sentiment_column": "方向",
}


def _workbook(rows, merged=None):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "框架"
    sheet.append(["一级", "二级", "三级", "原始说法", "方向"])
    for row in rows:
        sheet.append(row)
    for cells in merged or []:
        sheet.merge_cells(cells)
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def _content():
    return {
        "name": "手套",
        "structure_version": 1,
        "recognition_profile": "semantic_v1",
        "product_context": "手套",
        "instructions": ["按原文证据选择标签"],
        "allowed_parts": ["UNSPECIFIED"],
        "validation_rules": {},
        "variants": [{"category_a": "服饰", "category_b": "手套", "attributes": {}}],
        "labels": [],
    }


def test_preview_preserves_hierarchy_sources_and_duplicate_paths():
    data = _workbook(
        [
            ["功能", "保暖性", "不保暖", "冷", "负向"],
            ["功能", "保暖性", "不保暖", "冻手", "负向"],
            ["质量", "其他", "不保暖", "破洞漏风", "负向"],
        ]
    )
    current = _content()
    result = preview_excel(data, "框架", MAPPING, current, "standard-1")
    assert result["stats"] == {"rows": 3, "categories": 4, "labels": 2}
    assert current == _content()
    content = result["content"]
    assert content["labels"][0]["code"] != content["labels"][1]["code"]
    assert content["import_sources"][1]["source_label"] == "冻手"
    assert content["labels"][0]["keywords"] == []
    assert content["labels"][0]["description"] == ""
    assert all(issue["severity"] == "warning" for issue in result["issues"])
    assert not any("定义" in issue["message"] for issue in result["issues"])


def test_reimport_reuses_codes_and_definitions_but_isolates_standards():
    data = _workbook([["功能", "保暖性", "不保暖", "冷", "负向"]])
    first = preview_excel(data, "框架", MAPPING, _content(), "one")["content"]
    first["labels"][0].update(code="MANUAL_STABLE_ID", description="明确表示保暖不足")
    second = preview_excel(data, "框架", MAPPING, first, "one")["content"]
    assert second["labels"] == first["labels"]
    other = preview_excel(data, "框架", MAPPING, _content(), "two")["content"]
    assert other["categories"][0]["code"] != first["categories"][0]["code"]


def test_merge_ranges_are_restored_but_plain_blanks_are_not():
    data = _workbook(
        [
            ["功能", "保暖性", "不保暖", "冷", "负向"],
            [None, "防水性", "不防水", "湿", "负向"],
            [None, "其他", "异常", "异常", "负向"],
        ],
        ["A2:A3"],
    )
    result = preview_excel(data, "框架", MAPPING, _content(), "one")
    assert result["stats"]["rows"] == 2
    assert any(
        issue["row"] == 4 and issue["severity"] == "blocking"
        for issue in result["issues"]
    )


def test_conflicting_sentiment_is_not_silently_merged():
    data = _workbook(
        [
            ["功能", "保暖性", "不保暖", "冷", "负向"],
            ["功能", "保暖性", "不保暖", "暖", "正向"],
        ]
    )
    result = preview_excel(data, "框架", MAPPING, _content(), "one")
    assert any(
        issue["row"] == 3 and issue["severity"] == "blocking"
        for issue in result["issues"]
    )


def test_sheet_and_mapping_are_explicit():
    data = _workbook([["功能", "保暖性", "不保暖", "冷", "负向"]])
    assert preview_excel(data, "", {}, _content(), "one")["content"] is None
    result = preview_excel(data, "框架", {}, _content(), "one")
    assert result["headers"] == ["一级", "二级", "三级", "原始说法", "方向"]
    with pytest.raises(ValueError):
        preview_excel(
            data,
            "框架",
            {**MAPPING, "hierarchy_columns": ["不存在"]},
            _content(),
            "one",
        )


def test_reimport_does_not_guess_identity_after_category_rename():
    data = _workbook([["功能", "保暖性", "不保暖", "冷", "负向"]])
    first = preview_excel(data, "框架", MAPPING, _content(), "one")["content"]
    first["categories"][0]["name"] = "功能表现"
    result = preview_excel(data, "框架", MAPPING, first, "one")
    assert any(issue["severity"] == "blocking" for issue in result["issues"])


def test_unknown_rules_remain_visible_until_explicitly_repaired(tmp_path):
    service = ClassificationStandardService(Database(tmp_path / "unused.db"))
    current = _content()
    current["validation_rules"] = {"required_review_labels": ["OLD_LABEL"]}
    data = _workbook([["功能", "保暖性", "不保暖", "冷", "负向"]])
    content = preview_excel(data, "框架", MAPPING, current, "one")["content"]
    source = {
        "name": "手套",
        "variants": [],
        "taxonomy": {"version": "test", "agent_family": "gloves", "labels": []},
    }
    snapshot = service._snapshot_from_content(source, content)
    assert snapshot["taxonomy"]["validation_rules"]["required_review_labels"] == [
        "OLD_LABEL"
    ]
    with pytest.raises(ValueError, match="OLD_LABEL"):
        TaxonomyConfig.model_validate(snapshot["taxonomy"])


def test_unknown_sentiments_keep_rows_and_require_draft_review():
    data = _workbook(
        [
            ["功能", "保暖性", "不保暖", "冷", "负向"],
            ["功能", "保暖性", "不保暖", "冻手", "其他"],
            ["功能", "防水性", "不防水", "湿", None],
        ]
    )
    result = preview_excel(data, "框架", MAPPING, _content(), "one")
    content = result["content"]
    assert result["stats"]["rows"] == 3
    assert all(not label["allowed_sentiments"] for label in content["labels"])
    assert all(issue["severity"] == "warning" for issue in result["issues"])
    assert content["import_sources"][1]["source_sentiment"] == "其他"
    ClassificationStandardDraftContentRequest.model_validate(content)


def test_attachment_preserves_all_source_rows():
    path = Path(__file__).parents[1] / "标签框架-手套.xlsx"
    if not path.exists():
        pytest.skip("用户附件未随代码分发")
    result = preview_excel(
        path.read_bytes(),
        "Sheet2",
        {
            "hierarchy_columns": ["一级标签", "二级标签", "三级标签-处理"],
            "source_label_column": "三级标签-AI",
            "sentiment_column": "标签类型",
        },
        _content(),
        "gloves-preview",
    )
    assert result["stats"]["rows"] == 112
    assert len(result["content"]["import_sources"]) == 112
    assert not any(issue["severity"] == "blocking" for issue in result["issues"])


def test_publish_validation_blocks_empty_direction(tmp_path):
    database = Database(tmp_path / "app.db")
    database.initialize()
    service = ClassificationStandardService(database)
    standard = service.list()[0]
    base = service.current_version_for_standard(standard["id"])["snapshot"]
    data = _workbook([["功能", "保暖性", "不保暖", "冷", "其他"]])
    content = preview_excel(data, "框架", MAPPING, _content(), "one")["content"]
    content["labels"][0]["description"] = "明确表示保暖不足"
    candidate = service._snapshot_from_content(base, content)
    validation = service._validate_candidate(standard["id"], candidate, base)
    assert any("至少需要一种适用情感" in message for message in validation["blocking"])


def test_validation_issues_locate_missing_fields_and_old_rule(tmp_path):
    database = Database(tmp_path / "app.db")
    database.initialize()
    service = ClassificationStandardService(database)
    standard = service.list()[0]
    base = service.current_version_for_standard(standard["id"])["snapshot"]
    current = _content()
    current["validation_rules"] = {"required_review_labels": ["OLD_LABEL"]}
    data = _workbook(
        [
            ["功能", "保暖性", "其他", "冷", "其他"],
            ["质量", "耐用性", "其他", "坏", "负向"],
        ]
    )
    content = preview_excel(data, "框架", MAPPING, current, "one")["content"]
    candidate = service._snapshot_from_content(base, content)
    result = service._validate_candidate(standard["id"], candidate, base)
    assert not any(item.get("field") == "description" for item in result["issues"])
    assert not any("编码、名称" in message for message in result["blocking"])
    direction = next(
        item for item in result["issues"] if item["kind"] == "missing_sentiment"
    )
    assert direction["label_index"] == 0
    assert direction["field"] == "allowed_sentiments"
    rule = next(item for item in result["issues"] if item["kind"] == "invalid_rule")
    assert "OLD_LABEL" in rule["message"]
    assert rule["field"] == "validation_rules"
    assert set(result["blocking"]) == {item["message"] for item in result["issues"]}


@pytest.mark.parametrize("structure_version", [1, 2])
@pytest.mark.parametrize("omit_description", [False, True])
def test_optional_description_survives_draft_and_json_import(
    tmp_path, structure_version, omit_description
):
    service = _service(tmp_path)
    standard = service.list()[0]
    draft = service.create_draft(standard["id"], "user-1")
    data = _workbook([["功能", "保暖性", "不保暖", "冷", "负向"]])
    content = preview_excel(data, "框架", MAPPING, _content(), "one")["content"]
    content["structure_version"] = structure_version
    if omit_description:
        content["labels"][0].pop("description")
    if structure_version == 1:
        content["categories"] = []
        content["labels"][0].pop("parent_code")
        content["validation_rules"] = {}
    app = FastAPI()
    app.include_router(
        create_classification_standard_router(
            service,
            validation_service=object(),
            current_user=lambda: {"id": "user-1"},
        )
    )
    with TestClient(app) as client:
        response = client.patch(
            f"/api/classification-standard-drafts/{draft['id']}",
            json={
                "expected_revision": draft["revision"],
                "content": content,
                "change_reason": "验证无需判定说明的标签框架",
            },
        )
        assert response.status_code == 200, response.text
        saved = response.json()
        assert saved["validation"]["blocking"] == []
        assert saved["content"]["labels"][0]["description"] == ""
        snapshot = deepcopy(saved["snapshot"])
        if omit_description:
            snapshot["taxonomy"]["labels"][0].pop("description")
        encoded = json.dumps(
            snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        imported = service.import_draft_document(
            draft["id"],
            saved["revision"],
            {
                "format": "classification-standard",
                "format_version": 1,
                "snapshot": snapshot,
                "content_hash": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
            },
            "导入没有判定说明的快照",
            "user-1",
        )
        restored = service.get_draft(imported["id"])
        assert restored["content"]["labels"][0]["description"] == ""
        assert restored["validation"]["blocking"] == []
        taxonomy = TaxonomyConfig.model_validate(snapshot["taxonomy"])
        assert taxonomy.labels[0].description == ""
        assert (
            service.get(standard["id"])["standard_version_id"]
            == (standard["standard_version_id"])
        )


def test_unbound_history_cannot_borrow_current_hierarchy(tmp_path, monkeypatch):
    context = _seed_result_context(tmp_path)
    result = _publish(context)
    service = ClassificationStandardService(context.database)
    payload = context.taxonomy.model_dump(mode="json")
    payload.update(
        structure_version=2,
        categories=[
            {
                "code": "NEW_ROOT",
                "name": "新标准根节点",
                "parent_code": None,
            }
        ],
    )
    for label in payload["labels"]:
        label["parent_code"] = "NEW_ROOT"
    current = TaxonomyConfig.model_validate(payload)
    monkeypatch.setattr(service, "combined_taxonomy", lambda: current)
    with context.database.transaction() as connection:
        connection.execute(
            "UPDATE classification_results SET standard_version_id = NULL"
        )
    with pytest.raises(ClassificationStandardNotFound, match="恢复正确的历史标准绑定"):
        service.taxonomy_config_for_result_version(result["version_id"])


def test_snapshot_roundtrip_preserves_tree_and_sources(tmp_path):
    service = ClassificationStandardService(Database(tmp_path / "unused.db"))
    data = _workbook([["功能", "保暖性", "不保暖", "冷", "负向"]])
    content = preview_excel(data, "框架", MAPPING, _content(), "one")["content"]
    payload = ClassificationStandardDraftContentRequest.model_validate(
        content
    ).model_dump()
    source = {
        "name": "手套",
        "variants": [],
        "taxonomy": {"version": "test", "agent_family": "gloves", "labels": []},
    }
    snapshot = service._snapshot_from_content(source, payload)
    restored = service._editable_content(snapshot)
    assert restored == payload
    taxonomy = TaxonomyConfig.model_validate(snapshot["taxonomy"])
    code = taxonomy.labels[0].code
    assert label_path(taxonomy, code) == ["功能", "保暖性", "不保暖"]
    changed = deepcopy(snapshot)
    changed["taxonomy"]["categories"][0]["name"] = "功能表现"
    diff = service._diff_snapshots(snapshot, changed)
    assert diff["hierarchy_changed"]
    assert diff["has_changes"]
    assert not diff["semantic_label_changes"]
