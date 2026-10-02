from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_classification_result_pool import (
    _clone_publishable_segment,
    _seed_result_context,
)

from web_backend.agent_runner import AgentRunner
from web_backend.classification_result_publication import SegmentPublicationState
from web_backend.classification_result_service import (
    ClassificationResultService,
    ResultPublicationError,
)
from web_backend.common import json_value


@pytest.fixture
def publication(tmp_path: Path) -> SimpleNamespace:
    seed = _seed_result_context(tmp_path)
    with seed.database.transaction() as connection:
        connection.execute(
            """
            UPDATE task_segments
            SET error = '历史运行异常', requested_action = 'pause',
                result_publish_error = '历史发布异常'
            WHERE id = ?
            """,
            (seed.segment_id,),
        )
    return SimpleNamespace(
        seed=seed,
        service=ClassificationResultService(seed.database),
        state={
            "task_id": seed.task_id,
            "segment_id": seed.segment_id,
            "segment_status": "completed",
            "progress_total": 9,
            "model_calls": 11,
            "cache_hits": 13,
            "checkpoint_path": str(tmp_path / "合成检查点.json"),
            "legacy_result_version": 6,
        },
    )


def _publish(publication: SimpleNamespace) -> dict:
    seed = publication.seed
    return publication.service.publish_v1(
        dataset=seed.dataset,
        results=seed.results,
        taxonomy=seed.taxonomy,
        segment_state=SegmentPublicationState(**publication.state),
    )


def _segment(publication: SimpleNamespace) -> dict:
    with publication.seed.database.connect() as connection:
        return dict(
            connection.execute(
                "SELECT * FROM task_segments WHERE id = ?",
                (publication.seed.segment_id,),
            ).fetchone()
        )


@pytest.mark.parametrize("status", ["completed", "completed_with_errors"])
@pytest.mark.parametrize("failures", [None, 17])
def test_publication_preserves_supplied_segment_state(
    publication, status, failures
) -> None:
    publication.state["segment_status"] = status
    if failures is not None:
        publication.state["model_failures"] = failures

    version = _publish(publication)

    segment = _segment(publication)
    expected = {
        "status": status,
        "progress_current": 9,
        "progress_total": 9,
        "model_calls": 11,
        "cache_hits": 13,
        "model_failures": failures or 0,
        "result_json_path": publication.state["checkpoint_path"],
        "result_version": 6,
        "result_version_id": version["version_id"],
        "result_publish_status": "published",
        "result_quality_status": "ready",
        "error": None,
        "requested_action": None,
        "result_publish_error": None,
    }
    assert {key: segment[key] for key in expected} == expected
    assert segment["completed_at"] == segment["heartbeat_at"]
    assert segment["completed_at"] == segment["result_published_at"]
    assert version["version"] == 1
    assert version["record_count"] == 3
    with publication.seed.database.connect() as connection:
        event = connection.execute(
            "SELECT data_json FROM task_events WHERE event_type = 'segment_completed'"
        ).fetchone()
    assert json_value(event["data_json"], {}) == {
        "segment_id": publication.seed.segment_id,
        "status": status,
        "result_version_id": version["version_id"],
        "result_version": 1,
        "parent_version_id": None,
        "quality_status": "ready",
    }


def test_identical_publication_does_not_overwrite_segment_state(publication) -> None:
    first = _publish(publication)
    original = _segment(publication)
    publication.state.update(
        segment_status="completed_with_errors",
        progress_total=1,
        model_calls=101,
        cache_hits=103,
        model_failures=107,
        checkpoint_path="其他检查点.json",
        legacy_result_version=10,
    )

    repeated = _publish(publication)

    assert repeated == first
    assert _segment(publication) == original
    with publication.seed.database.connect() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM classification_result_versions"
            ).fetchone()[0]
            == 1
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM task_events WHERE event_type = 'segment_completed'"
            ).fetchone()[0]
            == 1
        )


@pytest.mark.parametrize("method", ["_insert_units", "_insert_records"])
def test_failed_publication_rolls_back_supplied_state(
    publication, monkeypatch, method
) -> None:
    before = _segment(publication)
    monkeypatch.setattr(
        publication.service, method, Mock(side_effect=RuntimeError("模拟事务写入失败"))
    )

    with pytest.raises(ResultPublicationError, match="模拟事务写入失败"):
        _publish(publication)

    after = _segment(publication)
    assert after == {
        **before,
        "result_publish_status": "failed",
        "result_publish_error": "模拟事务写入失败",
        "revision": before["revision"] + 1,
    }
    with publication.seed.database.connect() as connection:
        for table in (
            "classification_results",
            "classification_result_versions",
            "classification_units",
            "classification_unit_labels",
            "classification_result_records",
        ):
            assert (
                connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
            )


def test_publication_rejects_segment_from_another_task(publication) -> None:
    other = _clone_publishable_segment(publication.seed, "other")
    publication.state["segment_id"] = other.segment_id
    before = _segment(publication)

    with pytest.raises(ResultPublicationError, match="任务或 Listing 片段不存在"):
        _publish(publication)

    assert _segment(publication) == before
    with publication.seed.database.connect() as connection:
        other_segment = connection.execute(
            "SELECT status, result_version_id FROM task_segments WHERE id = ?",
            (other.segment_id,),
        ).fetchone()
        assert other_segment["status"] == "running"
        assert other_segment["result_version_id"] is None
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM classification_result_versions"
            ).fetchone()[0]
            == 0
        )


def test_retry_publication_keeps_persisted_runtime_without_model_calls(
    publication, tmp_path, monkeypatch
) -> None:
    seed = publication.seed
    config_service = Mock()
    runner = AgentRunner(
        seed.database, SimpleNamespace(data_dir=tmp_path), config_service
    )
    classify = Mock()
    monkeypatch.setattr(runner, "_classify_segment", classify)
    checkpoint_path = tmp_path / "retry-checkpoint.json"
    runner._write_checkpoint(checkpoint_path, seed.results)
    with seed.database.transaction() as connection:
        connection.execute(
            """
            UPDATE task_segments SET status = 'completed_with_errors',
                result_publish_status = 'publishing', model_calls = 3,
                cache_hits = 5, model_failures = 7, result_version = 4,
                result_json_path = ?, progress_total = 9
            WHERE id = ?
            """,
            (str(checkpoint_path), seed.segment_id),
        )

    version = runner.retry_result_publish(seed.task_id, seed.segment_id)

    segment = _segment(publication)
    assert segment["status"] == "completed_with_errors"
    assert segment["progress_current"] == segment["progress_total"] == 1
    assert (
        segment["model_calls"],
        segment["cache_hits"],
        segment["model_failures"],
    ) == (3, 5, 7)
    assert segment["result_version"] == 5
    assert segment["result_json_path"] == str(checkpoint_path)
    assert segment["result_version_id"] == version["version_id"]
    assert version["quality_status"] == "ready"
    classify.assert_not_called()
    config_service.build_model_settings.assert_not_called()
