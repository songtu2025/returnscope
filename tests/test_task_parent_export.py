import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest
from test_agent_runner_segment_outcomes import runtime as runtime

from return_semantics.data import ReturnDataset
from return_semantics.schemas import ValidatedClassification
from web_backend.agent_runner_parent_result import ParentResultMixin
from web_backend.classification_standard_validation_service import (
    ClassificationStandardValidationService,
)
from web_backend.common import json_text, json_value


def _registries(runtime, monkeypatch):
    registry = SimpleNamespace(
        version="fallback-registry",
        combined_taxonomy=Mock(return_value=runtime.seed.taxonomy),
    )
    frozen = SimpleNamespace(
        version="historical-registry",
        combined_taxonomy=Mock(return_value=runtime.seed.taxonomy),
    )
    monkeypatch.setattr(runtime.runner, "capability_registry", registry)
    runtime.runner.standard_service.registry_for_versions = Mock(return_value=frozen)
    return registry, frozen


def _prepare(runtime, monkeypatch, status="completed", historical=False, version=0):
    seed = runtime.seed
    runner = runtime.runner
    runner._write_checkpoint(runtime.context.checkpoint_path, seed.results)
    with seed.database.transaction() as connection:
        standard_id = (
            connection.execute(
                "SELECT id FROM classification_standard_versions ORDER BY id LIMIT 1"
            ).fetchone()[0]
            if historical
            else None
        )
        connection.execute(
            "UPDATE task_segments SET status = ?, result_json_path = ?, standard_version_id = ? WHERE id = ?",
            (
                status,
                str(runtime.context.checkpoint_path),
                standard_id,
                seed.segment_id,
            ),
        )
        connection.execute(
            "UPDATE tasks SET result_version = ?, metrics_json = ?, snapshot_json = ? WHERE id = ?",
            (
                version,
                json_text({"existing": "keep", "records": 999}),
                json_text(
                    {
                        "execution_plan": {
                            "summary": {"excluded_count": 7, "excluded_record_count": 9}
                        }
                    }
                ),
                seed.task_id,
            ),
        )
    registry, frozen = _registries(runtime, monkeypatch)
    load = Mock(wraps=runner._load_segments)
    monkeypatch.setattr(runner, "_load_segments", load)
    export = Mock(side_effect=lambda **kwargs: kwargs["output_path"].touch())
    monkeypatch.setattr(
        "web_backend.task_execution.legacy_export.export_results", export
    )
    return SimpleNamespace(
        registry=registry,
        frozen=frozen,
        export=export,
        load=load,
        standard_id=standard_id,
    )


@pytest.mark.parametrize("status", ["completed", "completed_with_errors"])
@pytest.mark.parametrize("historical", [False, True])
@pytest.mark.parametrize(
    "export_case",
    [
        ("completed", 0, "analysis-v1.xlsx"),
        ("cancelled", 4, "analysis-partial-v5.xlsx"),
        ("partial", 0, "analysis-partial-v1.xlsx"),
    ],
)
def test_parent_export_preserves_files_scope_registry_and_metrics(
    runtime, monkeypatch, status, historical, export_case
):
    parent_status, version, suffix = export_case
    prepared = _prepare(runtime, monkeypatch, status, historical, version)
    runtime.runner._build_parent_result(
        runtime.seed.task_id, runtime.seed.dataset, parent_status
    )
    task = runtime.runner._load_task(runtime.seed.task_id)
    metrics = json_value(task["metrics_json"], {})
    assert Path(task["result_file_path"]).name == suffix
    assert Path(task["result_file_path"]).exists()
    assert Path(task["results_json_path"]).name == "classifications-v1.json"
    assert (
        runtime.runner._load_checkpoint(Path(task["results_json_path"]))
        == runtime.seed.results
    )
    assert task["result_version"] == version + 1
    assert metrics["existing"] == "keep" and metrics["records"] == 3
    assert (
        metrics["delivered_records"],
        metrics["delivered_comments"],
        metrics["completed_segment_count"],
    ) == (3, 1, 1)
    assert (metrics["excluded_comments"], metrics["excluded_records"]) == (7, 9)
    assert metrics["partial_result"] == (parent_status != "completed")
    assert metrics["category_registry_version"] == (
        "historical-registry" if historical else "fallback-registry"
    )
    assert prepared.load.call_count == 2
    assert set(prepared.export.call_args.kwargs["results"]) == set(runtime.seed.results)
    if historical:
        runtime.runner.standard_service.registry_for_versions.assert_called_once_with(
            [prepared.standard_id]
        )
        prepared.frozen.combined_taxonomy.assert_called_once()
    else:
        runtime.runner.standard_service.registry_for_versions.assert_not_called()
        prepared.registry.combined_taxonomy.assert_called_once()


@pytest.mark.parametrize("kind", ["path", "incomplete"])
def test_completed_checkpoint_failure_precedes_export_and_database(
    runtime, monkeypatch, kind
):
    prepared = _prepare(runtime, monkeypatch)
    if kind == "path":
        with runtime.seed.database.transaction() as connection:
            connection.execute(
                "UPDATE task_segments SET result_json_path = NULL WHERE id = ?",
                (runtime.seed.segment_id,),
            )
    else:
        runtime.runner._write_checkpoint(runtime.context.checkpoint_path, {})
    before = runtime.runner._load_task(runtime.seed.task_id)
    with pytest.raises(ValueError, match="缺少结果检查点|结果不完整"):
        runtime.runner._build_parent_result(
            runtime.seed.task_id, runtime.seed.dataset, "completed"
        )
    assert runtime.runner._load_task(runtime.seed.task_id) == before
    prepared.export.assert_not_called()
    prepared.registry.combined_taxonomy.assert_not_called()


def test_missing_parent_does_not_load_segments_or_export(runtime, monkeypatch):
    prepared = _prepare(runtime, monkeypatch)
    runtime.runner._build_parent_result(
        "missing-synthetic", runtime.seed.dataset, "completed"
    )
    prepared.load.assert_not_called()
    prepared.export.assert_not_called()


@pytest.mark.parametrize("failure", ["export", "database"])
def test_parent_file_failure_preserves_database_and_written_checkpoint(
    runtime, monkeypatch, failure
):
    prepared = _prepare(runtime, monkeypatch)
    if failure == "export":
        prepared.export.side_effect = OSError("合成导出失败")
        expected = OSError
    else:
        with runtime.seed.database.transaction() as connection:
            connection.execute(
                "CREATE TRIGGER reject_parent_update BEFORE UPDATE ON tasks BEGIN SELECT RAISE(ABORT, '合成持久化失败'); END"
            )
        expected = sqlite3.IntegrityError
    before = runtime.runner._load_task(runtime.seed.task_id)
    with pytest.raises(expected):
        runtime.runner._build_parent_result(
            runtime.seed.task_id, runtime.seed.dataset, "completed"
        )
    assert runtime.runner._load_task(runtime.seed.task_id) == before
    checkpoint = (
        runtime.runner.settings.data_dir
        / "results"
        / runtime.seed.task_id
        / "classifications-v1.json"
    )
    assert runtime.runner._load_checkpoint(checkpoint) == runtime.seed.results


@pytest.mark.parametrize(
    "status,disposition,diagnostic,comment,expected_review,expected_error",
    [
        ("UNKNOWN_SEMANTIC", "OUT_OF_SCOPE", None, "They should be warm", 0, 0),
        ("UNKNOWN_SEMANTIC", "EXPECTED_ABSTENTION", None, "They should be warm", 0, 0),
        ("UNKNOWN_SEMANTIC", "MAPPING_UNCERTAIN", None, "They should be warm", 1, 0),
        ("UNKNOWN_SEMANTIC", "TAXONOMY_GAP", None, "They should be warm", 1, 0),
        ("MODEL_ERROR", None, "MODEL_RUN_TIMEOUT", "They should be warm", 0, 1),
        (
            "SECONDARY_REVIEW",
            "OUT_OF_SCOPE",
            "MODEL_RESULT_MISMATCH",
            "They should be warm",
            1,
            0,
        ),
        (
            "SECONDARY_REVIEW",
            "OUT_OF_SCOPE",
            "SECONDARY_MODEL_MISSING",
            "They should be warm",
            0,
            0,
        ),
        ("NO_TEXT_EVIDENCE", None, None, "", 0, 0),
        ("AUTO_APPROVED", None, None, "Uncovered source text", 1, 0),
    ],
)
def test_parent_and_validation_review_counts_follow_semantic_disposition(
    taxonomy, status, disposition, diagnostic, comment, expected_review, expected_error
):
    result = ValidatedClassification.model_validate(
        {
            "classification_key": "synthetic",
            "semantic_units": [],
            "unknown_semantics": [
                {
                    "opinion": comment,
                    "evidence": comment,
                    "reason": "合成分类依据",
                    "disposition": disposition,
                }
            ]
            if disposition
            else [],
            "problem_label_codes": [],
            "positive_label_codes": [],
            "primary_label_codes": [],
            "status": status,
            "review_reasons": [],
            "review_diagnostics": [{"code": diagnostic}] if diagnostic else [],
            "model_name": "synthetic",
            "prompt_version": "test",
            "taxonomy_version": taxonomy.version,
        }
    )
    samples = [
        {
            "classification_key": "synthetic",
            "comment": comment,
            "category_a": "合成品类",
            "category_b": "合成子类",
            "baseline": {},
        }
    ]
    dataset = ReturnDataset(
        records=pd.DataFrame(),
        unique_comments=pd.DataFrame(
            [{"classification_key": "synthetic", "comment_normalized": comment}]
        ),
        mskus=frozenset(),
    )
    assert (
        ParentResultMixin._review_count(
            {"synthetic": result.model_dump(mode="json")}, dataset, taxonomy
        )
        == expected_review
    )
    items = ClassificationStandardValidationService._comparison_items(
        samples, {"synthetic": result}
    )
    summary = ClassificationStandardValidationService._summary(items, taxonomy)
    assert summary["review_count"] == expected_review
    assert summary["error_count"] == expected_error


def test_parent_review_count_keeps_manually_resolved_feedback_out_of_pending(runtime):
    seed = runtime.seed
    key = next(iter(seed.results))
    payload = seed.results[key].model_dump(mode="json")
    payload.update(status="MANUAL_REVIEW", human_review_assessment={"resolved": True})
    assert (
        ParentResultMixin._review_count({key: payload}, seed.dataset, seed.taxonomy)
        == 0
    )
