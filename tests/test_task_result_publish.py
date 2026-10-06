from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from task_execution_helpers import (
    EVENT_FAILURE,
    audit_rows,
    fail_event_write,
    trace_queries,
    transaction_statements,
)
from test_classification_result_pool import _seed_result_context

from web_backend.agent_runner import AgentRunner
from web_backend.task_service import (
    TaskResultPublishConflict,
    TaskRevisionConflict,
    TaskService,
)


@pytest.fixture
def publication(tmp_path):
    seed = _seed_result_context(tmp_path)
    checkpoint = tmp_path / "synthetic-checkpoint.json"
    AgentRunner._write_checkpoint(checkpoint, seed.results)
    with seed.database.transaction() as connection:
        connection.execute(
            "UPDATE task_segments SET status = 'completed', result_publish_status = 'failed', result_json_path = ? WHERE id = ?",
            (str(checkpoint), seed.segment_id),
        )
    publisher = Mock(return_value={})
    service = TaskService(seed.database, result_publisher=publisher)
    return SimpleNamespace(
        seed=seed, service=service, publisher=publisher, checkpoint=checkpoint
    )


@pytest.mark.parametrize("status", ["completed", "completed_with_errors"])
def test_result_retry_commits_before_publisher_and_preserves_query_budget(
    publication, monkeypatch, status
):
    seed, service = publication.seed, publication.service
    with seed.database.transaction() as connection:
        connection.execute(
            "UPDATE task_segments SET status = ? WHERE id = ?",
            (status, seed.segment_id),
        )
    before = service.get(seed.task_id)
    queries = trace_queries(seed.database, monkeypatch)

    def publish(task_id, segment_id):
        with seed.database.connect() as connection:
            row = connection.execute(
                "SELECT result_publish_status FROM task_segments WHERE id = ?",
                (segment_id,),
            ).fetchone()
            assert row["result_publish_status"] == "publishing"
            assert service.get(task_id)["revision"] == before["revision"] + 1
        return {}

    publication.publisher.side_effect = publish
    result = service.retry_result_publish(
        seed.task_id, seed.segment_id, "user-1", before["revision"], "  合成发布  "
    )
    publication.publisher.assert_called_once_with(seed.task_id, seed.segment_id)
    assert result["revision"] == before["revision"] + 1
    assert [sql.split()[0] for sql in transaction_statements(queries)] == [
        "SELECT",
        "SELECT",
        "UPDATE",
        "UPDATE",
        "INSERT",
        "INSERT",
    ]
    event = service.events(seed.task_id)[-1]
    assert event["event_type"] == "result_publish_retry"
    assert event["data"]["reason"] == "合成发布"


@pytest.mark.parametrize(
    "case, message",
    [
        ("blank", "请填写结果发布重试原因"),
        ("service", "服务未配置"),
        ("missing", "任务不存在"),
        ("stale", "任务已被他人修改"),
        ("segment", "Listing 片段不存在"),
        ("publishing", "正在发布"),
        ("published", "已经发布"),
        ("pending", "不处于发布失败状态"),
        ("running", "仅分类已完成"),
        ("checkpoint", "没有可用的分类检查点"),
    ],
)
def test_result_retry_preserves_rejection_priority(publication, case, message):
    seed, service = publication.seed, publication.service
    if case in {"publishing", "published", "pending", "running"}:
        with seed.database.transaction() as connection:
            connection.execute(
                "UPDATE task_segments SET result_publish_status = ?, status = ? WHERE id = ?",
                (case if case != "running" else "failed", "running", seed.segment_id),
            )
    if case == "service":
        service.result_publisher = None
    if case == "checkpoint":
        publication.checkpoint.unlink()
    before = service.get(seed.task_id)
    error = (
        ValueError
        if case in {"blank", "missing", "segment"}
        else (TaskRevisionConflict if case == "stale" else TaskResultPublishConflict)
    )
    with pytest.raises(error, match=message):
        service.retry_result_publish(
            "missing" if case in {"blank", "service", "missing"} else seed.task_id,
            "missing" if case in {"stale", "segment"} else seed.segment_id,
            "user-1",
            before["revision"] - 1 if case == "stale" else before["revision"],
            " " if case == "blank" else "合成发布",
        )
    assert service.get(seed.task_id) == before
    publication.publisher.assert_not_called()


def test_result_retry_event_failure_rolls_back_without_publishing(publication):
    seed, service = publication.seed, publication.service
    before = service.get(seed.task_id)
    events = service.events(seed.task_id)
    audit = audit_rows(seed.database)
    fail_event_write(seed.database)
    with pytest.raises(EVENT_FAILURE, match="合成回滚"):
        service.retry_result_publish(
            seed.task_id, seed.segment_id, "user-1", before["revision"], "合成发布"
        )
    assert service.get(seed.task_id) == before
    assert service.events(seed.task_id) == events
    assert audit_rows(seed.database) == audit
    publication.publisher.assert_not_called()
