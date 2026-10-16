import json
from pathlib import Path

import pandas as pd
import pytest
from test_classification_result_pool import _publish, _seed_result_context
from test_manual_correction import _items, _record
from test_result_version_reviews import _publish_review_required

from return_analysis.data import load_analysis_data
from return_semantics.exporter import export_results
from return_semantics.schemas import ValidatedClassification
from web_backend.analysis_service import AnalysisFilters, AnalysisService
from web_backend.analysis_services.result_data import published_analysis_data
from web_backend.classification_result_service import ClassificationResultService
from web_backend.classification_results.manual_correction import correct_group
from web_backend.classification_standard_service import ClassificationStandardService


def _bind_standard(context):
    standard = next(
        item
        for item in ClassificationStandardService(context.database).list()
        if item["standard_key"] == "footwear"
    )
    with context.database.transaction() as c:
        c.execute(
            "UPDATE task_segments SET standard_version_id=? WHERE id=?",
            (standard["standard_version_id"], context.segment_id),
        )
        c.execute("UPDATE tasks SET status='completed',result_file_path=NULL")
    return standard


def test_database_analysis_matches_existing_frames_without_files(tmp_path, monkeypatch):
    context = _seed_result_context(tmp_path)
    _bind_standard(context)
    version = _publish(context)
    with context.database.connect() as c:
        row = c.execute(
            "SELECT classification_json FROM classification_units WHERE result_version_id=?",
            (version["version_id"],),
        ).fetchone()
    published = ValidatedClassification.model_validate(json.loads(row[0]))
    legacy = tmp_path / "legacy-reference.xlsx"
    export_results(legacy, context.dataset, {context.key: published}, context.taxonomy)
    expected = load_analysis_data(legacy)

    def no_file(*args, **kwargs):
        raise AssertionError("结构化分析不应解析文件")

    monkeypatch.setattr(pd, "read_excel", no_file)
    monkeypatch.setattr(pd, "read_csv", no_file)
    restored = published_analysis_data(context.database, (version["version_id"],))
    pd.testing.assert_frame_equal(
        expected.details.fillna(""), restored.details.fillna(""), check_dtype=False
    )
    pd.testing.assert_frame_equal(
        expected.semantics.fillna(""), restored.semantics.fillna(""), check_dtype=False
    )
    service = AnalysisService(context.database)
    response = service.get(context.task_id, AnalysisFilters())
    assert response["scope"]["total_records"] == 3
    content, _name = service.export_filtered(context.task_id, AnalysisFilters())
    assert content.startswith(b"PK")


def test_database_analysis_follows_manual_versions_and_removal(tmp_path):
    context, version = _publish_review_required(tmp_path)
    _bind_standard(context)
    service = AnalysisService(context.database)
    before = service.get(context.task_id, AnalysisFilters())
    corrected = correct_group(
        ClassificationResultService(context.database),
        version["version_id"],
        _record(context, version),
        _items(),
        "user-2",
    )
    after = service.get(context.task_id, AnalysisFilters())
    assert before["overview"]["metrics"]["review_records"] == 3
    assert after["overview"]["metrics"]["review_records"] == 1
    assert after["scope"]["total_records"] == 3
    with context.database.transaction() as c:
        c.execute(
            "UPDATE classification_results SET deleted_at='2026-10-17' WHERE id=?",
            (corrected["result_id"],),
        )
    with pytest.raises(ValueError, match="已移除"):
        published_analysis_data(context.database, (corrected["version_id"],))
    with pytest.raises(ValueError, match="已移除"):
        service.get(context.task_id, AnalysisFilters())


def test_structured_completion_keeps_checkpoint_and_skips_legacy_exports(
    tmp_path, monkeypatch
):
    from types import SimpleNamespace
    from unittest.mock import Mock

    from web_backend.agent_runner import AgentRunner

    context = _seed_result_context(tmp_path)
    _bind_standard(context)
    runner = AgentRunner(context.database, SimpleNamespace(data_dir=tmp_path), Mock())
    task = runner._load_task(context.task_id)
    segment = runner._load_segment(context.segment_id)
    execution = runner._segment_run_context(
        context.task_id, context.segment_id, task, segment
    )

    def no_export(*args, **kwargs):
        raise AssertionError("结构化任务不应自动生成旧版 Excel")

    monkeypatch.setattr(
        "web_backend.task_execution.legacy_export.export_results", no_export
    )
    runner._export_legacy_segment_result(
        execution,
        tmp_path / "unused.xlsx",
        context.dataset,
        context.results,
        context.taxonomy,
    )
    runner._write_checkpoint(execution.checkpoint_path, context.results)
    _publish(context)
    with context.database.transaction() as c:
        c.execute(
            "UPDATE task_segments SET result_json_path=?",
            (str(execution.checkpoint_path),),
        )
    runner._build_parent_result(context.task_id, context.dataset, "completed")
    task = runner._load_task(context.task_id)
    assert task["result_file_path"] is None and task["results_json_path"] is None
    assert Path(execution.checkpoint_path).is_file()
    assert not list(tmp_path.glob("results/**/*.xlsx"))
    from web_backend.classification_results.export_jobs import ResultExportService

    exports = ResultExportService(
        ClassificationResultService(context.database), tmp_path / "exports"
    )
    segment = runner._load_segment(context.segment_id)
    job = exports.create([segment["result_version_id"]])
    assert exports.claim_next() == job["id"]
    exports.run(job["id"])
    path, _name = exports.file(job["id"])
    assert path.read_bytes().startswith(b"PK")
