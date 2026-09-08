from __future__ import annotations

from concurrent.futures import Future
from pathlib import Path
from typing import Any

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
