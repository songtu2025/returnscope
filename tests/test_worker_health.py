from __future__ import annotations

from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, call

import pytest

from web_backend.classification_standard_validation_worker import (
    ClassificationStandardValidationWorker,
)
from web_backend.database import Database
from web_backend.insight_report_worker import InsightReportWorker
from web_backend.worker import TaskWorker


class LoopControl:
    def __init__(self) -> None:
        self.wait_count = 0

    def is_set(self) -> bool:
        return self.wait_count >= 2

    def wait(self, _timeout: float) -> None:
        self.wait_count += 1

    def set(self) -> None:
        self.wait_count = 2


class RecoveringService:
    def __init__(self) -> None:
        self.claim_count = 0

    def claim_next(self) -> None:
        self.claim_count += 1
        if self.claim_count == 1:
            raise RuntimeError("领取失败")
        return None

    def run(self, _item_id: str) -> None:
        return


class NoopRunner:
    def run_segment(self, _task_id: str, _segment_id: str) -> None:
        return

    def finalize_task(self, _task_id: str) -> None:
        return


class RecoveringTaskWorker(TaskWorker):
    def __init__(self, database: Database) -> None:
        super().__init__(database, NoopRunner(), concurrency=1)
        self.claim_count = 0

    def _claim_next_segment(self) -> tuple[str, str] | None:
        self.claim_count += 1
        if self.claim_count == 1:
            raise RuntimeError("领取失败")
        return None

    def _finalize_pending_results(self) -> None:
        return


@pytest.mark.parametrize(
    "worker_class",
    [InsightReportWorker, ClassificationStandardValidationWorker],
)
def test_service_worker_keeps_supervising_after_unhandled_error(
    worker_class: type[Any],
) -> None:
    service = RecoveringService()
    worker = worker_class(service)
    worker._stop = LoopControl()

    worker._loop()

    assert service.claim_count == 2
    assert worker.health["last_error"] == "RuntimeError: 领取失败"
    assert worker.health["last_error_at"] is not None


def test_task_worker_keeps_supervising_after_unhandled_error(
    tmp_path: Path,
) -> None:
    worker = RecoveringTaskWorker(Database(tmp_path / "app.db"))
    worker._stop = LoopControl()

    worker._loop()

    assert worker.claim_count == 2
    assert worker.health["last_error"] == "RuntimeError: 领取失败"
    assert worker.health["last_error_at"] is not None
    worker.stop()


def test_task_worker_records_unhandled_segment_error(tmp_path: Path) -> None:
    worker = TaskWorker(Database(tmp_path / "app.db"), NoopRunner(), concurrency=1)
    worker._active.add("segment-1")
    future: Future[None] = Future()
    future.set_exception(RuntimeError("片段失败"))

    worker._segment_finished("segment-1", future)

    assert worker.health["last_error"] == "RuntimeError: 片段失败"
    assert worker.health["last_error_at"] is not None
    assert "segment-1" not in worker._active
    worker.stop()


@pytest.fixture(
    params=[InsightReportWorker, ClassificationStandardValidationWorker],
    ids=["insight_report", "classification_standard_validation"],
)
def service_worker(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> SimpleNamespace:
    service = Mock()
    stop = LoopControl()
    stop.wait = Mock(wraps=stop.wait)
    worker = request.param(service)
    worker._stop = stop
    worker.worker_logger = Mock()
    monkeypatch.setattr(
        "web_backend.worker_health.utc_now", lambda: "2026-10-02T01:02:03+00:00"
    )
    return SimpleNamespace(service=service, stop=stop, worker=worker)


def test_service_worker_waits_for_empty_queue_without_error(
    service_worker: SimpleNamespace,
) -> None:
    service_worker.service.claim_next.return_value = None

    service_worker.worker._loop()

    assert service_worker.service.claim_next.call_count == 2
    service_worker.service.run.assert_not_called()
    assert service_worker.stop.wait.call_args_list == [call(1.0), call(1.0)]
    assert service_worker.worker.health == {
        "last_error": None,
        "last_error_type": None,
        "last_error_at": None,
    }
    service_worker.worker.worker_logger.exception.assert_not_called()


def test_service_worker_processes_next_item_after_execution_error(
    service_worker: SimpleNamespace,
) -> None:
    service_worker.service.claim_next.side_effect = ["first", "second", None]
    service_worker.service.run.side_effect = [RuntimeError("执行失败"), None]

    service_worker.worker._loop()

    assert service_worker.service.claim_next.call_count == 3
    assert service_worker.service.run.call_args_list == [call("first"), call("second")]
    assert service_worker.stop.wait.call_args_list == [call(1.0), call(1.0)]
    assert service_worker.worker.health == {
        "last_error": "RuntimeError: 执行失败",
        "last_error_type": "RuntimeError",
        "last_error_at": "2026-10-02T01:02:03+00:00",
    }
    service_worker.worker.worker_logger.exception.assert_called_once_with(
        service_worker.worker.error_message
    )


def test_service_worker_does_not_claim_after_stop_signal(
    service_worker: SimpleNamespace,
) -> None:
    service_worker.stop.set()

    service_worker.worker._loop()

    service_worker.service.claim_next.assert_not_called()
    service_worker.service.run.assert_not_called()
    service_worker.stop.wait.assert_not_called()
    assert service_worker.worker.health["last_error"] is None


def test_service_worker_stops_after_current_item(
    service_worker: SimpleNamespace,
) -> None:
    service_worker.service.claim_next.return_value = "current"
    service_worker.service.run.side_effect = lambda _item_id: service_worker.stop.set()

    service_worker.worker._loop()

    service_worker.service.claim_next.assert_called_once_with()
    service_worker.service.run.assert_called_once_with("current")
    service_worker.stop.wait.assert_not_called()
    assert service_worker.worker.health["last_error"] is None


def test_service_worker_keeps_original_callbacks_during_loop(
    service_worker: SimpleNamespace,
) -> None:
    service = service_worker.service
    original_claim = service.claim_next
    original_run = service.run
    replacement_claim = Mock(side_effect=AssertionError("不应切换领取回调"))
    replacement_run = Mock(side_effect=AssertionError("不应切换执行回调"))
    original_claim.side_effect = ["first", "second", None]

    def run(item_id: str) -> None:
        if item_id == "first":
            service.claim_next = replacement_claim
            service.run = replacement_run
            raise RuntimeError("执行失败")

    original_run.side_effect = run

    service_worker.worker._loop()

    assert original_claim.call_count == 3
    assert original_run.call_args_list == [call("first"), call("second")]
    replacement_claim.assert_not_called()
    replacement_run.assert_not_called()
    assert service_worker.stop.wait.call_args_list == [call(1.0), call(1.0)]
    assert service_worker.worker.health["last_error"] == "RuntimeError: 执行失败"


def test_service_worker_records_latest_error(
    service_worker: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    service_worker.service.claim_next.side_effect = [RuntimeError("领取失败"), "first"]
    service_worker.service.run.side_effect = ValueError("执行失败")
    monkeypatch.setattr(
        "web_backend.worker_health.utc_now",
        Mock(side_effect=["2026-10-02T01:02:03+00:00", "2026-10-02T01:02:04+00:00"]),
    )

    service_worker.worker._loop()

    assert service_worker.service.claim_next.call_count == 2
    service_worker.service.run.assert_called_once_with("first")
    assert service_worker.worker.health == {
        "last_error": "ValueError: 执行失败",
        "last_error_type": "ValueError",
        "last_error_at": "2026-10-02T01:02:04+00:00",
    }
    assert service_worker.worker.worker_logger.exception.call_args_list == [
        call(service_worker.worker.error_message),
        call(service_worker.worker.error_message),
    ]
    assert service_worker.stop.wait.call_args_list == [call(1.0), call(1.0)]
