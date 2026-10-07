from __future__ import annotations

import json
import random
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from return_semantics.model_cache import JsonlCache as JsonlCache
from return_semantics.model_payload import (
    flatten_integer_metrics as flatten_integer_metrics,
)
from return_semantics.model_payload import (
    normalize_model_payload as normalize_model_payload,
)
from return_semantics.model_payload import parse_json_object as parse_json_object
from return_semantics.model_results import JsonModelCallResult as JsonModelCallResult
from return_semantics.model_results import ModelCallResult as ModelCallResult
from return_semantics.model_results import ModelClient as ModelClient
from return_semantics.model_results import ModelClientSettings as ModelClientSettings
from return_semantics.model_settings import Sub2APISettings as Sub2APISettings
from return_semantics.model_settings import _read_float_env as _read_float_env
from return_semantics.model_settings import _read_int_env as _read_int_env
from return_semantics.model_settings import load_dotenv as load_dotenv
from return_semantics.schemas import ModelClassification


class ModelHTTPError(RuntimeError):
    def __init__(
        self,
        provider: str,
        status_code: int,
        body: str,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(f"{provider} HTTP {status_code}: {body}")
        self.status_code = status_code
        self.retry_after = retry_after


class RequestRateLimiter:
    def __init__(self, requests_per_minute: int) -> None:
        self.interval_seconds = (
            60.0 / requests_per_minute if requests_per_minute > 0 else 0.0
        )
        self._next_request_at = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        if self.interval_seconds == 0:
            return

        with self._lock:
            now = time.monotonic()
            wait_seconds = max(0.0, self._next_request_at - now)
            self._next_request_at = max(now, self._next_request_at) + (
                self.interval_seconds
            )
        if wait_seconds > 0:
            time.sleep(wait_seconds)


def _retry_after_seconds(error: urllib.error.HTTPError) -> float | None:
    value = error.headers.get("Retry-After") if error.headers else None
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


class Sub2APIClient:
    def __init__(
        self,
        settings: Sub2APISettings,
        rate_limiter: RequestRateLimiter | None = None,
    ) -> None:
        self.settings = settings
        self._rate_limiter = rate_limiter or RequestRateLimiter(
            settings.requests_per_minute,
        )

    def classify(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        thinking: bool = False,
    ) -> ModelCallResult:
        model_name = model or self.settings.model
        if thinking:
            reasoning_effort = self.settings.secondary_reasoning_effort
        elif model_name == self.settings.cheap_model:
            reasoning_effort = self.settings.cheap_reasoning_effort
        else:
            reasoning_effort = self.settings.reasoning_effort
        result = self.generate_json(
            messages,
            model=model_name,
            reasoning_effort=reasoning_effort,
        )
        payload = normalize_model_payload(result.payload)
        # 诊断信息属于系统控制面，不能信任模型回传的内容。
        payload["review_diagnostics"] = []
        classification = ModelClassification.model_validate(payload)
        return ModelCallResult(
            classification=classification,
            model_name=result.model_name,
            usage=result.usage,
            metrics=result.metrics,
        )

    def generate_json(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        reasoning_effort: str | None = None,
    ) -> JsonModelCallResult:
        model_name = model or self.settings.model
        payload: dict[str, Any] = {
            "model": model_name,
            "input": messages,
            "reasoning": {"effort": reasoning_effort or self.settings.reasoning_effort},
        }
        if self.settings.use_fast:
            payload["service_tier"] = "fast"
        if self.settings.prompt_cache_key:
            payload["prompt_cache_key"] = self.settings.prompt_cache_key

        last_error: Exception | None = None
        timeout_failures = 0
        started_at = time.monotonic()
        for attempt in range(self.settings.retries + 1):
            try:
                response = self._post(payload)
                content = self._extract_output_text(response)
                result_payload = parse_json_object(content)
                usage = flatten_integer_metrics(response.get("usage", {}))
                return JsonModelCallResult(
                    payload=result_payload,
                    model_name=str(response.get("model", model_name)),
                    usage=usage,
                    metrics={
                        "attempts": attempt + 1,
                        "retries": attempt,
                        "latency_ms": int((time.monotonic() - started_at) * 1000),
                    },
                )
            except (
                KeyError,
                TypeError,
                ValueError,
                ModelHTTPError,
                TimeoutError,
                urllib.error.URLError,
            ) as exc:
                last_error = exc
                if isinstance(exc, TimeoutError):
                    timeout_failures += 1
                if attempt >= self.settings.retries:
                    break
                if timeout_failures > 1:
                    break
                if isinstance(exc, ModelHTTPError) and (
                    exc.status_code < 500 and exc.status_code not in {408, 409, 429}
                ):
                    break

                if isinstance(exc, ModelHTTPError) and exc.retry_after is not None:
                    delay_seconds = exc.retry_after
                else:
                    base_delay = min(
                        self.settings.retry_base_seconds * (2**attempt),
                        self.settings.retry_max_seconds,
                    )
                    delay_seconds = base_delay + random.uniform(
                        0,
                        base_delay * 0.25,
                    )
                time.sleep(delay_seconds)

        raise RuntimeError(f"Sub2API 调用失败: {last_error}") from last_error

    @staticmethod
    def _extract_output_text(response: dict[str, Any]) -> str:
        parts = []
        for item in response.get("output", []):
            if not isinstance(item, dict):
                continue
            for content in item.get("content", []):
                if not isinstance(content, dict):
                    continue
                if content.get("type") == "output_text":
                    text = content.get("text")
                    if isinstance(text, str):
                        parts.append(text)

        output_text = "".join(parts).strip()
        if not output_text:
            raise ValueError("Sub2API 返回了空内容")
        return output_text

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._rate_limiter.wait()
        request = urllib.request.Request(
            url=f"{self.settings.base_url.rstrip('/')}/responses",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.settings.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=self.settings.timeout_seconds,
            ) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:500]
            raise ModelHTTPError(
                provider="Sub2API",
                status_code=exc.code,
                body=body,
                retry_after=_retry_after_seconds(exc),
            ) from exc


def create_model_client(
    dotenv_path: Path | None = None,
) -> Sub2APIClient:
    settings = Sub2APISettings.from_env(dotenv_path)
    return Sub2APIClient(settings)


# 保留已有导入入口和类型序列化路径，模块内部按职责独立实现。
for _entry in (
    flatten_integer_metrics,
    normalize_model_payload,
    parse_json_object,
    load_dotenv,
    _read_int_env,
    _read_float_env,
    Sub2APISettings,
    ModelClientSettings,
    ModelClient,
    ModelCallResult,
    JsonModelCallResult,
    JsonlCache,
):
    _entry.__module__ = __name__
