from __future__ import annotations

import json
import os
import random
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

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


def flatten_integer_metrics(
    values: dict[str, Any],
    prefix: str = "",
) -> dict[str, int]:
    output: dict[str, int] = {}
    for key, value in values.items():
        metric_name = f"{prefix}.{key}" if prefix else key
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            output[metric_name] = value
        elif isinstance(value, dict):
            output.update(flatten_integer_metrics(value, metric_name))
    return output


def _retry_after_seconds(error: urllib.error.HTTPError) -> float | None:
    value = error.headers.get("Retry-After") if error.headers else None
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _read_int_env(
    name: str,
    default: int,
    minimum: int = 0,
    maximum: int | None = None,
) -> int:
    try:
        value = int(os.getenv(name, str(default)).strip())
    except ValueError as exc:
        raise ValueError(f"{name} 必须是整数") from exc
    if value < minimum or (maximum is not None and value > maximum):
        raise ValueError(f"{name} 超出允许范围")
    return value


def _read_float_env(
    name: str,
    default: float,
    minimum: float = 0.0,
) -> float:
    try:
        value = float(os.getenv(name, str(default)).strip())
    except ValueError as exc:
        raise ValueError(f"{name} 必须是数字") from exc
    if value < minimum:
        raise ValueError(f"{name} 超出允许范围")
    return value


@dataclass(frozen=True)
class Sub2APISettings:
    api_key: str = field(repr=False)
    model: str
    base_url: str
    timeout_seconds: int = 120
    retries: int = 5
    use_fast: bool = False
    secondary_model: str | None = "gpt-5.6-sol"
    cheap_model: str | None = "gpt-5.4-mini"
    reasoning_effort: str = "medium"
    cheap_reasoning_effort: str = "medium"
    secondary_reasoning_effort: str = "high"
    cheap_model_audit_percent: int = 5
    requests_per_minute: int = 60
    max_workers: int = 4
    retry_base_seconds: float = 1.0
    retry_max_seconds: float = 60.0
    prompt_cache_key: str | None = None
    provider: str = field(default="sub2api", init=False)

    @property
    def cache_namespace(self) -> str:
        return (
            f"{self.provider}:primary={self.reasoning_effort}:"
            f"secondary={self.secondary_reasoning_effort}"
        )

    @classmethod
    def from_env(cls, dotenv_path: Path | None = None) -> "Sub2APISettings":
        if dotenv_path is not None:
            load_dotenv(dotenv_path)

        api_key = os.getenv("SUB2API_API_KEY", "").strip()
        model = os.getenv("SUB2API_MODEL", "gpt-5.5").strip()
        base_url = os.getenv("SUB2API_BASE_URL", "").strip()
        secondary_model = os.getenv(
            "SUB2API_SECONDARY_MODEL",
            "gpt-5.6-sol",
        ).strip()
        cheap_model = os.getenv(
            "SUB2API_CHEAP_MODEL",
            "gpt-5.4-mini",
        ).strip()
        reasoning_effort = os.getenv(
            "SUB2API_REASONING_EFFORT",
            "medium",
        ).strip()
        cheap_reasoning_effort = os.getenv(
            "SUB2API_CHEAP_REASONING_EFFORT",
            "medium",
        ).strip()
        secondary_reasoning_effort = os.getenv(
            "SUB2API_SECONDARY_REASONING_EFFORT",
            "high",
        ).strip()
        timeout_text = os.getenv("SUB2API_TIMEOUT", "120").strip()
        prompt_cache_key = os.getenv(
            "SUB2API_PROMPT_CACHE_KEY",
            "",
        ).strip()
        use_fast = os.getenv("SUB2API_USE_FAST", "false").strip().lower()

        if not api_key:
            raise ValueError("缺少 SUB2API_API_KEY")
        if not model:
            raise ValueError("缺少 SUB2API_MODEL")
        if not base_url:
            raise ValueError("缺少 SUB2API_BASE_URL")
        if not reasoning_effort:
            raise ValueError("缺少 SUB2API_REASONING_EFFORT")
        if cheap_model and not cheap_reasoning_effort:
            raise ValueError("缺少 SUB2API_CHEAP_REASONING_EFFORT")
        if not secondary_reasoning_effort:
            raise ValueError("缺少 SUB2API_SECONDARY_REASONING_EFFORT")
        try:
            timeout_seconds = int(timeout_text)
        except ValueError as exc:
            raise ValueError("SUB2API_TIMEOUT 必须是整数") from exc
        if timeout_seconds <= 0:
            raise ValueError("SUB2API_TIMEOUT 必须大于 0")

        return cls(
            api_key=api_key,
            model=model,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            retries=_read_int_env("SUB2API_RETRIES", 5),
            use_fast=use_fast in {"1", "true", "yes", "on"},
            secondary_model=secondary_model or None,
            cheap_model=cheap_model or None,
            reasoning_effort=reasoning_effort,
            cheap_reasoning_effort=cheap_reasoning_effort,
            secondary_reasoning_effort=secondary_reasoning_effort,
            cheap_model_audit_percent=_read_int_env(
                "SUB2API_CHEAP_MODEL_AUDIT_PERCENT",
                5,
                maximum=100,
            ),
            requests_per_minute=_read_int_env(
                "SUB2API_REQUESTS_PER_MINUTE",
                60,
            ),
            max_workers=_read_int_env(
                "SUB2API_MAX_WORKERS",
                4,
                minimum=1,
                maximum=16,
            ),
            retry_base_seconds=_read_float_env(
                "SUB2API_RETRY_BASE_SECONDS",
                1.0,
            ),
            retry_max_seconds=_read_float_env(
                "SUB2API_RETRY_MAX_SECONDS",
                60.0,
            ),
            prompt_cache_key=prompt_cache_key or None,
        )


class ModelClientSettings(Protocol):
    model: str
    secondary_model: str | None
    cheap_model: str | None
    cheap_model_audit_percent: int
    max_workers: int
    provider: str
    cache_namespace: str


class ModelClient(Protocol):
    settings: ModelClientSettings

    def classify(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        thinking: bool = False,
    ) -> "ModelCallResult": ...


@dataclass(frozen=True)
class ModelCallResult:
    classification: ModelClassification
    model_name: str
    usage: dict[str, int]
    metrics: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class JsonModelCallResult:
    payload: dict[str, Any]
    model_name: str
    usage: dict[str, int]
    metrics: dict[str, int] = field(default_factory=dict)


def normalize_model_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    semantic_units = list(normalized.get("semantic_units", []))
    unknown_semantics = []

    for item in normalized.get("unknown_semantics", []):
        if isinstance(item, str):
            unknown_semantics.append(
                {
                    "opinion": item,
                    "evidence": item,
                    "reason": "模型未提供未映射原因",
                }
            )
        elif isinstance(item, dict) and "label_code" in item:
            semantic_units.append(item)
        elif isinstance(item, dict) and "opinion" in item and "evidence" in item:
            unknown_semantics.append(
                {
                    "opinion": item["opinion"],
                    "evidence": item["evidence"],
                    "reason": item.get(
                        "reason",
                        "模型未提供未映射原因",
                    ),
                }
            )
        elif isinstance(item, dict) and "description" in item and "evidence" in item:
            unknown_semantics.append(
                {
                    "opinion": item["description"],
                    "evidence": item["evidence"],
                    "reason": item.get(
                        "reason",
                        "模型未提供未映射原因",
                    ),
                }
            )
        elif isinstance(item, dict) and "text" in item:
            normalized_item = dict(item)
            text = normalized_item.pop("text")
            normalized_item.setdefault("opinion", text)
            normalized_item.setdefault("evidence", text)
            unknown_semantics.append(normalized_item)
        else:
            unknown_semantics.append(item)

    normalized["semantic_units"] = semantic_units
    normalized["unknown_semantics"] = unknown_semantics
    return normalized


def parse_json_object(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            text = "\n".join(lines[1:-1]).strip()

    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("模型返回的 JSON 顶层必须是对象")
    return payload


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
        classification = ModelClassification.model_validate(
            normalize_model_payload(result.payload)
        )
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
            "reasoning": {
                "effort": reasoning_effort or self.settings.reasoning_effort
            },
        }
        if self.settings.use_fast:
            payload["service_tier"] = "fast"
        if self.settings.prompt_cache_key:
            payload["prompt_cache_key"] = self.settings.prompt_cache_key

        last_error: Exception | None = None
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
                urllib.error.URLError,
            ) as exc:
                last_error = exc
                if attempt >= self.settings.retries:
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


class JsonlCache:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._items: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._key_locks: dict[str, threading.Lock] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                item = json.loads(line)
                self._items[item["cache_key"]] = item

    def lock_for(self, cache_key: str) -> threading.Lock:
        with self._lock:
            return self._key_locks.setdefault(
                cache_key,
                threading.Lock(),
            )

    def get(self, cache_key: str) -> ModelCallResult | None:
        with self._lock:
            item = self._items.get(cache_key)
        if item is None:
            return None
        return ModelCallResult(
            classification=ModelClassification.model_validate(item["classification"]),
            model_name=item["model_name"],
            usage=item.get("usage", {}),
            metrics=item.get("metrics", {}),
        )

    def put(self, cache_key: str, result: ModelCallResult) -> None:
        item = {
            "cache_key": cache_key,
            "model_name": result.model_name,
            "usage": result.usage,
            "metrics": result.metrics,
            "classification": result.classification.model_dump(mode="json"),
        }
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as cache_file:
                cache_file.write(json.dumps(item, ensure_ascii=False) + "\n")
            self._items[cache_key] = item
