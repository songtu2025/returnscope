"""复用监督循环串行生成结果文件，避免大文件导出挤占分析任务。"""

import logging

from web_backend.worker_health import ServiceWorker


class ResultExportWorker(ServiceWorker):
    thread_name = "result-export-worker"
    error_message = "结果导出监督循环异常"
    worker_logger = logging.getLogger(__name__)
