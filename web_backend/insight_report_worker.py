from __future__ import annotations

import logging

from web_backend.insight_report_service import InsightReportService
from web_backend.worker_health import ServiceWorker


class InsightReportWorker(ServiceWorker):
    thread_name = "ai-insight-report-worker"
    error_message = "AI 洞察报告监督循环异常"
    worker_logger = logging.getLogger(__name__)

    def __init__(self, service: InsightReportService) -> None:
        super().__init__(service)
