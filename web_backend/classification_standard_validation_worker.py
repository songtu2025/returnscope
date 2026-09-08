from __future__ import annotations

import logging

from web_backend.classification_standard_validation_service import (
    ClassificationStandardValidationService,
)
from web_backend.worker_health import ServiceWorker


class ClassificationStandardValidationWorker(ServiceWorker):
    thread_name = "classification-standard-validation-worker"
    error_message = "分类标准验证监督循环异常"
    worker_logger = logging.getLogger(__name__)

    def __init__(self, service: ClassificationStandardValidationService) -> None:
        super().__init__(service)
