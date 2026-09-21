from datetime import date
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest
from test_classification_result_pool import _publish, _seed_result_context
from test_result_version_reviews import _publish_review_required

from return_analysis.data import load_analysis_data
from return_semantics.exporter import export_results
from return_semantics.schemas import TaxonomyConfig
from web_backend.analysis_service import AnalysisFilters, AnalysisService
from web_backend.classification_result_service import ClassificationResultService
from web_backend.classification_standard_service import ClassificationStandardService
from web_backend.common import json_text
from web_backend.dashboard_service import DashboardService
from web_backend.result_hierarchy import result_taxonomy
from web_backend.review_service import ReviewService


def test_result_tree_filters_count_feedback_groups_and_exports_paths(
    tmp_path: Path, monkeypatch
) -> None:
    context = _seed_result_context(tmp_path)
    payload = context.taxonomy.model_dump(mode="json")
    payload["structure_version"] = 2
    payload["categories"] = [
        {"code": "ROOT", "name": "尺码", "parent_code": None},
        {"code": "FIT", "name": "不合身", "parent_code": "ROOT"},
    ]
    for label in payload["labels"]:
        label["parent_code"] = "FIT"
    taxonomy = TaxonomyConfig.model_validate(payload)
    version = _publish(context)
    service = ClassificationResultService(context.database)
    monkeypatch.setattr(service, "taxonomy", lambda _: taxonomy)
    version_id = str(version["version_id"])
    sibling = next(
        label for label in taxonomy.labels if label.code != "FIT_TOO_SMALL_U1"
    )
    with context.database.transaction() as connection:
        connection.execute(
            """INSERT INTO classification_unit_labels
            (result_version_id, classification_key, label_kind, label_code, label_name, label_group)
            VALUES (?, ?, 'problem', ?, ?, ?)""",
            (version_id, context.key, sibling.code, sibling.name, "尺码"),
        )
    rows = service.records(version_id, problem="ROOT", order_id="ORDER-DUP")
    assert rows["total"] == 2
    assert rows["items"][0]["classification"]["semantic_units"][0]["label_path"][
        :2
    ] == ["尺码", "不合身"]
    counts = service.drilldown(version_id, "category", order_id="ORDER-DUP")
    root = next(item for item in counts["items"] if item["value"] == "ROOT")
    assert root["record_count"] == 1
    assert root["unit_count"] == 1
    assert root["label_path"] == ["尺码"]
    content, _ = service.download(version_id)
    exported = pd.read_excel(BytesIO(content), sheet_name="语义层级")
    assert len(exported) == 3
    assert exported["第1级标签"].tolist() == ["尺码"] * 3
    assert exported["证据原文"].tolist() == ["Too small"] * 3
    workbook = tmp_path / "hierarchy.xlsx"
    export_results(workbook, context.dataset, context.results, taxonomy)
    data = load_analysis_data(workbook)
    analysis = AnalysisService(context.database)
    monkeypatch.setattr(analysis, "_task_source", lambda *_: {"result_version": 1})
    monkeypatch.setattr(analysis, "_load_task_data", lambda _: data)
    monkeypatch.setattr(analysis, "_apply_task_scope", lambda frame, _: frame)
    filtered = analysis._filter(
        data.details, AnalysisFilters(problem_code="ROOT"), data.semantics
    )
    assert len(filtered) == 3
    content, _ = analysis.export_filtered(
        "task", AnalysisFilters(problem_code="ROOT", start_date=date(2026, 8, 2))
    )
    exported = pd.read_excel(BytesIO(content), sheet_name="语义层级")
    assert exported.iloc[0]["标签编码路径"].startswith("ROOT → FIT → ")
    assert exported.iloc[0]["重复记录数"] == 2


def test_result_paths_use_bound_snapshot_and_missing_binding_stays_unknown(
    tmp_path: Path,
) -> None:
    context = _seed_result_context(tmp_path)
    version = _publish(context)
    version_id = str(version["version_id"])
    standards = ClassificationStandardService(context.database)
    standards.ensure_bootstrapped()
    with context.database.transaction() as connection:
        connection.execute(
            "UPDATE classification_results SET standard_version_id = NULL"
        )
        assert result_taxonomy(connection, version_id) is None
        standard = connection.execute(
            "SELECT id FROM classification_standard_versions LIMIT 1"
        ).fetchone()
        payload = context.taxonomy.model_dump(mode="json")
        payload["structure_version"] = 2
        payload["categories"] = [
            {"code": "ROOT", "name": "历史根节点", "parent_code": None}
        ]
        for label in payload["labels"]:
            label["parent_code"] = "ROOT"
        connection.execute(
            "UPDATE classification_standard_versions SET snapshot_json = ? WHERE id = ?",
            (json_text({"taxonomy": payload}), standard["id"]),
        )
        connection.execute(
            "UPDATE classification_results SET standard_version_id = ?",
            (standard["id"],),
        )
    service = ClassificationResultService(context.database)
    records = service.records(version_id)
    path = records["items"][0]["classification"]["semantic_units"][0]["label_path"]
    assert path[0] == "历史根节点"
    dashboards = DashboardService(context.database)
    plan = dashboards.preflight([version_id], {"problem": "ROOT"})
    assert plan["summary"]["record_count"] == 2
    dashboard = dashboards.create(
        name="层级统计",
        description="测试数据",
        result_version_ids=[version_id],
        filters={"problem": "ROOT"},
        plan_hash=plan["plan_hash"],
        reason="验证版本路径",
        actor_id="user-1",
    )
    insights = dashboards.insights(
        dashboard["id"],
        dashboard["version"]["version_id"],
        date_from="2026-08-02",
        date_to="2026-08-02",
    )
    root = next(
        item for item in insights["hierarchy_problems"] if item["value"] == "ROOT"
    )
    assert root["record_count"] == 1
    assert insights["group_alignment"] == "original"
    rows = dashboards.records(
        dashboard["id"], dashboard["version"]["version_id"], problem="ROOT"
    )
    assert rows["total"] == 3
    assert (
        rows["items"][0]["classification"]["semantic_units"][0]["label_path"][0]
        == "历史根节点"
    )
    with context.database.connect() as connection:
        assert DashboardService._mixed_hierarchy(
            connection,
            [
                {
                    "standard_version_id": standard["id"],
                    "result_version_id": version_id,
                },
                {
                    "standard_version_id": "another-version",
                    "result_version_id": version_id,
                },
            ],
        )


def test_unbound_review_stays_readable_and_rejects_new_labels(tmp_path: Path) -> None:
    context, version = _publish_review_required(tmp_path)
    service = ReviewService(context.database)
    batch = service.create_batch(str(version["version_id"]), "user-1", "验证历史绑定")
    with context.database.transaction() as connection:
        connection.execute(
            "UPDATE classification_results SET standard_version_id = NULL"
        )
    rows = service.batch_records(batch["id"])
    assert rows["taxonomy"] is None
    assert "problem_label_paths" not in rows["items"][0]
    review = rows["items"][0]
    with pytest.raises(ValueError, match="缺少标准版本绑定"):
        service.update_batch_record(
            batch["id"],
            review["id"],
            review["revision"],
            "user-1",
            "FIT_TOO_SMALL_U1",
            "不能借用最新标签",
            action="modify",
        )
