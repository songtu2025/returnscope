from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from itertools import groupby
from threading import Barrier
from unittest.mock import Mock

import pytest
from test_classification_result_publication_state import (
    _publish,
    _segment,
)
from test_classification_result_publication_state import (
    publication as publication,
)

from web_backend.classification_result_publication import SegmentPublicationState
from web_backend.classification_result_service import (
    ResultPublicationConflict,
    ResultPublicationError,
)
from web_backend.classification_results import (
    publication_transaction,
    publication_writes,
)


def _publication_trace(publication, monkeypatch) -> tuple[list, list]:
    queries = []
    connections = []
    original_connect = publication.seed.database.connect

    def connect():
        connection = original_connect()
        connection.set_trace_callback(queries.append)
        return connection

    monkeypatch.setattr(publication.seed.database, "connect", connect)
    for module, name in [
        (publication_transaction, "insert_result"),
        (publication_transaction, "insert_version"),
        (publication.service, "_insert_units"),
        (publication.service, "_insert_records"),
        (publication_transaction, "publish_version"),
    ]:
        original = getattr(module, name)

        def checked(*args, original=original):
            assert args[0].in_transaction
            connections.append(args[0])
            return original(*args)

        monkeypatch.setattr(module, name, checked)

    return queries, connections


def test_publication_writes_use_one_immediate_transaction(
    publication, monkeypatch
) -> None:
    queries, connections = _publication_trace(publication, monkeypatch)

    _publish(publication)

    assert len(connections) == 5
    assert all(connection is connections[0] for connection in connections)
    statements = [" ".join(query.split()) for query in queries]
    assert statements.count("BEGIN IMMEDIATE") == 1
    writes = [
        query.split()[0:3]
        for query in statements
        if query.startswith(("INSERT", "UPDATE"))
    ]
    writes = [key for key, _ in groupby(writes)]
    assert writes == [
        ["INSERT", "INTO", "classification_results("],
        ["INSERT", "INTO", "classification_result_versions("],
        ["INSERT", "INTO", "classification_units("],
        ["INSERT", "INTO", "classification_unit_labels("],
        ["INSERT", "INTO", "classification_unit_semantics("],
        ["INSERT", "INTO", "classification_result_records("],
        ["UPDATE", "classification_result_versions", "SET"],
        ["UPDATE", "task_segments", "SET"],
        ["INSERT", "INTO", "task_events("],
    ]
    assert statements.count("COMMIT") == 1


@pytest.mark.parametrize("step", ["update_segment", "record_completion"])
def test_failure_after_state_or_event_write_rolls_back_everything(
    publication, monkeypatch, step
) -> None:
    original = getattr(publication_writes, step)
    before = _segment(publication)

    def fail_after_write(*args):
        original(*args)
        raise RuntimeError("模拟最终写回失败")

    monkeypatch.setattr(publication_writes, step, fail_after_write)

    with pytest.raises(ResultPublicationError, match="模拟最终写回失败"):
        _publish(publication)

    assert _segment(publication) == {
        **before,
        "result_publish_status": "failed",
        "result_publish_error": "模拟最终写回失败",
        "revision": before["revision"] + 1,
    }
    with publication.seed.database.connect() as connection:
        for table in [
            "classification_results",
            "classification_result_versions",
            "classification_units",
            "classification_unit_labels",
            "classification_unit_semantics",
            "classification_result_records",
        ]:
            assert (
                connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
            )
        events = connection.execute("SELECT event_type FROM task_events").fetchall()
    assert [event[0] for event in events] == ["result_publish_failed"]


def test_conflict_commits_event_without_marking_publication_failed(
    publication, monkeypatch
) -> None:
    first = _publish(publication)
    before = _segment(publication)
    publication.seed.results = deepcopy(publication.seed.results)
    next(iter(publication.seed.results.values())).model_name = "合成冲突模型"
    mark_failed = Mock()
    monkeypatch.setattr(publication.service, "mark_publish_failed", mark_failed)

    with pytest.raises(ResultPublicationConflict, match="拒绝覆盖"):
        _publish(publication)

    mark_failed.assert_not_called()
    after = _segment(publication)
    assert after["result_version_id"] == first["version_id"]
    assert after["revision"] == before["revision"] + 1
    assert after["result_publish_status"] == "published"
    with publication.seed.database.connect() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM classification_result_versions"
            ).fetchone()[0]
            == 1
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM task_events WHERE event_type='result_publish_conflict'"
            ).fetchone()[0]
            == 1
        )


@pytest.mark.parametrize("different", [False, True])
def test_concurrent_publications_create_only_one_version(
    publication, different
) -> None:
    seed = publication.seed
    inputs = [seed.results, deepcopy(seed.results)]
    if different:
        next(iter(inputs[1].values())).model_name = "合成并发模型"
    barrier = Barrier(2)

    def publish(results):
        barrier.wait(timeout=10)
        try:
            return publication.service.publish_v1(
                dataset=seed.dataset,
                results=results,
                taxonomy=seed.taxonomy,
                segment_state=SegmentPublicationState(**publication.state),
            )["version_id"]
        except ResultPublicationConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outputs = list(executor.map(publish, inputs))

    assert outputs.count("conflict") == int(different)
    assert len(set(value for value in outputs if value != "conflict")) == 1
    with seed.database.connect() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM classification_result_versions"
            ).fetchone()[0]
            == 1
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM task_events WHERE event_type='segment_completed'"
            ).fetchone()[0]
            == 1
        )


@pytest.mark.parametrize("step", ["_prepare_publication", "get"])
def test_failures_outside_transaction_keep_original_exception_boundary(
    publication, monkeypatch, step
) -> None:
    mark_failed = Mock()
    monkeypatch.setattr(publication.service, "mark_publish_failed", mark_failed)
    monkeypatch.setattr(
        publication.service, step, Mock(side_effect=ValueError("模拟边界异常"))
    )

    with pytest.raises(ValueError, match="模拟边界异常"):
        _publish(publication)

    mark_failed.assert_not_called()
    with publication.seed.database.connect() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM classification_result_versions"
        ).fetchone()[0]
    assert count == int(step == "get")
