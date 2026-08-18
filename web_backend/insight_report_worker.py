from __future__ import annotations

import threading

from web_backend.insight_report_service import InsightReportService


class InsightReportWorker:
    def __init__(self, service: InsightReportService) -> None:
        self.service = service
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self.service.recover()
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name="ai-insight-report-worker",
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
        while not self._stop.is_set():
            report_id = self.service.claim_next()
            if report_id is None:
                self._stop.wait(1.0)
                continue
            self.service.run(report_id)
