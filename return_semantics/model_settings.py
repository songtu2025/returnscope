from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


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
