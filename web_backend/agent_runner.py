from __future__ import annotations

import logging
import threading
import time

from return_semantics.capabilities import load_capability_registry
from return_semantics.claims import ClaimsResolver
from return_semantics.model_client import (
    JsonlCache,
    RequestRateLimiter,
)
from return_semantics.pipeline import (
    ModelServiceUnavailable,
    PipelineCancelled,
)
from web_backend.agent_runner_parent_result import ParentResultMixin
from web_backend.agent_runner_result_publication import (
    IncompleteResultCheckpoint as IncompleteResultCheckpoint,
)
from web_backend.agent_runner_result_publication import ResultPublicationMixin
from web_backend.agent_runner_segment_execution import SegmentExecutionMixin
from web_backend.agent_runner_segment_execution import (
    _SegmentRunContext as _SegmentRunContext,
)
from web_backend.agent_runner_segment_outcomes import SegmentOutcomesMixin
from web_backend.classification_result_service import (
    ClassificationResultService,
    ResultPublicationError,
)
from web_backend.classification_standard_service import ClassificationStandardService
from web_backend.config_service import ConfigService
from web_backend.database import Database
from web_backend.settings import PROJECT_ROOT, Settings
from web_backend.task_execution.classification import ClassificationExecutionMixin
from web_backend.task_execution.legacy_export import LegacyResultExportMixin
from web_backend.task_execution.model_runtime import ModelRuntimeMixin

performance_logger = logging.getLogger("uvicorn.error.performance")


class AgentRunner(
    ClassificationExecutionMixin,
    LegacyResultExportMixin,
    ModelRuntimeMixin,
    SegmentExecutionMixin,
    SegmentOutcomesMixin,
    ResultPublicationMixin,
    ParentResultMixin,
):
    def __init__(
        self,
        database: Database,
        settings: Settings,
        config_service: ConfigService,
        result_service: ClassificationResultService | None = None,
        standard_service: ClassificationStandardService | None = None,
    ) -> None:
        self.database = database
        self.settings = settings
        self.config_service = config_service
        self.result_service = result_service or ClassificationResultService(database)
        self.standard_service = standard_service or ClassificationStandardService(
            database
        )
        self.capability_registry = (
            self.standard_service.active_registry()
            if self.standard_service._tables_exist()
            else load_capability_registry(
                PROJECT_ROOT / "config" / "category_capabilities.json"
            )
        )
        self.claims_resolver = ClaimsResolver(
            PROJECT_ROOT / "config" / "listing_claims_registry.json"
        )
        self._rate_limiters: dict[str, RequestRateLimiter] = {}
        self._rate_limiters_lock = threading.Lock()
        self._caches: dict[str, JsonlCache] = {}
        self._caches_lock = threading.Lock()
        self._task_locks: dict[str, threading.Lock] = {}
        self._task_locks_lock = threading.Lock()

    def _get_cache(self, config_version_id: str) -> JsonlCache:
        with self._caches_lock:
            cache = self._caches.get(config_version_id)
            if cache is None:
                cache = JsonlCache(
                    self.settings.data_dir / "cache" / f"{config_version_id}.jsonl"
                )
                self._caches[config_version_id] = cache
            return cache

    def run_segment(self, task_id: str, segment_id: str) -> None:
        started = time.perf_counter()
        outcome = "completed"
        task = self._load_task(task_id)
        segment = self._load_segment(segment_id)
        if task is None or segment is None or segment["status"] != "running":
            performance_logger.info(
                "segment_performance task_id=%s segment_id=%s outcome=skipped "
                "total_ms=%.2f",
                task_id,
                segment_id,
                (time.perf_counter() - started) * 1000,
            )
            return
        context = self._segment_run_context(task_id, segment_id, task, segment)
        try:
            self._execute_segment(context)
        except PipelineCancelled:
            outcome = "interrupted"
            self._finish_interrupted_segment(context)
        except ModelServiceUnavailable as exc:
            outcome = "model_service_paused"
            self._finish_model_service_paused(context, str(exc))
        except ResultPublicationError as exc:
            outcome = "result_publish_failed"
            self._finish_result_publish_failed_segment(context, str(exc))
        except Exception as exc:
            outcome = "failed"
            self._finish_failed_segment(context, str(exc))
        finally:
            performance_logger.info(
                "segment_performance task_id=%s segment_id=%s outcome=%s total_ms=%.2f",
                task_id,
                segment_id,
                outcome,
                (time.perf_counter() - started) * 1000,
            )

    def _get_rate_limiter(
        self,
        config_version_id: str,
        requests_per_minute: int,
    ) -> RequestRateLimiter:
        with self._rate_limiters_lock:
            return self._rate_limiters.setdefault(
                config_version_id,
                RequestRateLimiter(requests_per_minute),
            )
