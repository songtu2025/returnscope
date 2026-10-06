from __future__ import annotations

from collections.abc import Callable
from threading import Event, Lock

from return_semantics.model_client import ModelCallResult, ModelHTTPError
from return_semantics.pipeline_models import ModelServiceUnavailable, PipelineRun
from return_semantics.schemas import ValidatedClassification

MODEL_SERVICE_ALERT_FAILURES = 3
MODEL_SERVICE_PAUSE_FAILURES = 5


def _add_usage(total: dict[str, int], usage: dict[str, int]) -> None:
    for key, value in usage.items():
        total[key] = total.get(key, 0) + value


def _is_model_service_error(exc: Exception) -> bool:
    current: BaseException | None = exc
    while current is not None:
        if isinstance(current, ModelHTTPError):
            return current.status_code >= 500
        current = current.__cause__
    return False


class _RunTracker:
    def __init__(
        self,
        on_model_degraded: Callable[[PipelineRun, int, str], None] | None,
    ) -> None:
        self.results: dict[str, ValidatedClassification] = {}
        self.usage: dict[str, int] = {}
        self.usage_by_model: dict[str, dict[str, int]] = {}
        self.cache_hits = 0
        self.cache_hits_by_model: dict[str, int] = {}
        self.model_calls = 0
        self.model_calls_by_model: dict[str, int] = {}
        self.model_failures = 0
        self.consecutive_service_failures = 0
        self.last_service_error = ""
        self.request_metrics: dict[str, int] = {}
        self.routing: dict[str, int] = {}
        self._on_model_degraded = on_model_degraded
        self._lock = Lock()
        self._service_breaker = Event()

    def increment_routing(self, route_name: str) -> None:
        with self._lock:
            self.routing[route_name] = self.routing.get(route_name, 0) + 1

    def record_call(
        self,
        requested_model: str,
        call_result: ModelCallResult,
        cache_hit: bool,
    ) -> None:
        with self._lock:
            if cache_hit:
                self.cache_hits += 1
                self.cache_hits_by_model[requested_model] = (
                    self.cache_hits_by_model.get(requested_model, 0) + 1
                )
                return

            self.consecutive_service_failures = 0
            call_count = call_result.metrics.get(
                "fact_model_calls", 1
            ) + call_result.metrics.get("output_correction_calls", 0)
            self.model_calls += call_count
            self.model_calls_by_model[requested_model] = (
                self.model_calls_by_model.get(requested_model, 0) + call_count
            )
            _add_usage(self.usage, call_result.usage)
            model_usage = self.usage_by_model.setdefault(requested_model, {})
            _add_usage(model_usage, call_result.usage)
            _add_usage(self.request_metrics, call_result.metrics)

    def record_failure(self, exc: Exception) -> int:
        is_service_error = _is_model_service_error(exc)
        with self._lock:
            self.model_failures += 1
            if is_service_error:
                self.consecutive_service_failures += 1
                self.last_service_error = str(exc)
            else:
                self.consecutive_service_failures = 0
            failure_count = self.consecutive_service_failures
        if (
            failure_count >= MODEL_SERVICE_ALERT_FAILURES
            and self._on_model_degraded is not None
        ):
            self._on_model_degraded(self.snapshot(), failure_count, str(exc))
        return failure_count

    def raise_if_service_paused(self) -> None:
        if not self._service_breaker.is_set():
            return
        with self._lock:
            failure_count = self.consecutive_service_failures
            error = self.last_service_error
        raise ModelServiceUnavailable(
            f"模型服务连续失败 {failure_count} 次，已自动暂停：{error}",
            failure_count,
        )

    def pause_after_failure(self, failure_count: int, exc: Exception) -> None:
        if failure_count < MODEL_SERVICE_PAUSE_FAILURES:
            return
        self._service_breaker.set()
        raise ModelServiceUnavailable(
            f"模型服务连续失败 {failure_count} 次，已自动暂停：{exc}",
            failure_count,
        ) from exc

    def add_result(
        self,
        classification_key: str,
        validated: ValidatedClassification,
    ) -> None:
        with self._lock:
            self.results[classification_key] = validated

    def snapshot(self) -> PipelineRun:
        with self._lock:
            return PipelineRun(
                classifications=dict(self.results),
                usage=dict(self.usage),
                usage_by_model={
                    key: dict(values) for key, values in self.usage_by_model.items()
                },
                cache_hits=self.cache_hits,
                cache_hits_by_model=dict(self.cache_hits_by_model),
                model_calls=self.model_calls,
                model_calls_by_model=dict(self.model_calls_by_model),
                request_metrics=dict(self.request_metrics),
                routing=dict(self.routing),
                model_failures=self.model_failures,
            )
