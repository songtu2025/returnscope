from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Protocol

from web_backend.security import utc_now


class StopEvent(Protocol):
    def is_set(self) -> bool: ...

    def wait(self, timeout: float) -> bool | None: ...


class WorkerService(Protocol):
    def recover(self) -> None: ...

    def claim_next(self) -> str | None: ...

    def run(self, item_id: str) -> None: ...


class WorkerHealthState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_error: str | None = None
        self._last_error_type: str | None = None
        self._last_error_at: str | None = None

    def record_error(self, error: BaseException) -> None:
        with self._lock:
            self._last_error = f"{type(error).__name__}: {error}"
            self._last_error_type = type(error).__name__
            self._last_error_at = utc_now()

    def snapshot(self) -> dict[str, str | None]:
        with self._lock:
            return {
                "last_error": self._last_error,
                "last_error_type": self._last_error_type,
                "last_error_at": self._last_error_at,
            }


class WorkerHealthMixin:
    _health: WorkerHealthState

    @property
    def health(self) -> dict[str, str | None]:
        return self._health.snapshot()


def run_service_worker_loop(
    *,
    stop: StopEvent,
    claim_next: Callable[[], str | None],
    run: Callable[[str], None],
    health: WorkerHealthState,
    logger: logging.Logger,
    error_message: str,
) -> None:
    while not stop.is_set():
        try:
            item_id = claim_next()
            if item_id is None:
                stop.wait(1.0)
                continue
            run(item_id)
        except Exception as exc:
            health.record_error(exc)
            logger.exception(error_message)
            stop.wait(1.0)


class ServiceWorker(WorkerHealthMixin):
    thread_name: str
    error_message: str
    worker_logger: logging.Logger

    def __init__(self, service: WorkerService) -> None:
        self.service = service
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._health = WorkerHealthState()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self.service.recover()
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name=self.thread_name,
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    @property
    def is_alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _loop(self) -> None:
        run_service_worker_loop(
            stop=self._stop,
            claim_next=self.service.claim_next,
            run=self.service.run,
            health=self._health,
            logger=self.worker_logger,
            error_message=self.error_message,
        )
