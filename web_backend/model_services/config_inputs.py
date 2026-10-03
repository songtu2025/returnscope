from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import urlparse

from web_backend.common import new_id
from web_backend.model_catalog import clean_model_definition, validate_effort
from web_backend.security import utc_now


def _validate_url(value: str) -> str:
    url = value.strip().rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Base URL 必须是有效的 HTTP 或 HTTPS 地址")
    if parsed.scheme != "https" and parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("非本地 API 必须使用 HTTPS")
    return url


@dataclass(frozen=True)
class _CreateVersionInput:
    actor_id: str
    name: str
    provider: str
    base_url: str
    api_key: str
    primary_model: str
    primary_effort: str
    cheap_model: str | None
    cheap_effort: str
    secondary_model: str | None
    secondary_effort: str
    cheap_audit_percent: int
    requests_per_minute: int
    max_workers: int
    timeout_seconds: int
    change_note: str
    connection_id: str | None
    models: list[dict[str, Any]] | None


@dataclass(frozen=True)
class _CreateVersionContext:
    values: _CreateVersionInput
    connection_id: str
    version_id: str
    now: str
    model_definitions: list[dict[str, Any]]
    model_keys: list[str]
    selected_models: list[tuple[str | None, str]]


@dataclass(frozen=True)
class _ConnectionVersionContext:
    version: int
    api_key_ciphertext: str
    is_new_connection: bool


def _prepare_create_version(values: _CreateVersionInput) -> _CreateVersionContext:
    base_url = _validate_url(values.base_url)
    primary_model = values.primary_model.strip()
    if not primary_model:
        raise ValueError("主模型不能为空")
    primary_effort = validate_effort(values.primary_effort, "主模型推理强度")
    cheap_model = (values.cheap_model or "").strip() or None
    cheap_effort = validate_effort(values.cheap_effort, "低成本模型推理强度")
    secondary_model = (values.secondary_model or "").strip() or None
    secondary_effort = validate_effort(
        values.secondary_effort,
        "二次复核模型推理强度",
    )
    if not 0 <= values.cheap_audit_percent <= 100:
        raise ValueError("低成本模型抽检比例必须在 0 到 100 之间")
    if not 1 <= values.requests_per_minute <= 10000:
        raise ValueError("每分钟请求数必须在 1 到 10000 之间")
    if not 1 <= values.max_workers <= 16:
        raise ValueError("单任务并发必须在 1 到 16 之间")
    if not 5 <= values.timeout_seconds <= 600:
        raise ValueError("请求超时必须在 5 到 600 秒之间")
    change_note = values.change_note.strip()
    if not change_note:
        raise ValueError("请填写配置变更原因")
    model_definitions = [
        clean_model_definition(value) for value in (values.models or [])
    ]
    model_keys = [value["model_key"] for value in model_definitions]
    if len(model_keys) != len(set(model_keys)):
        raise ValueError("模型列表中存在重复的模型 ID")
    normalized_values = replace(
        values,
        base_url=base_url,
        primary_model=primary_model,
        primary_effort=primary_effort,
        cheap_model=cheap_model,
        cheap_effort=cheap_effort,
        secondary_model=secondary_model,
        secondary_effort=secondary_effort,
        change_note=change_note,
    )
    return _CreateVersionContext(
        values=normalized_values,
        connection_id=values.connection_id or new_id("conn"),
        version_id=new_id("cfg"),
        now=utc_now(),
        model_definitions=model_definitions,
        model_keys=model_keys,
        selected_models=[
            (primary_model, primary_effort),
            (cheap_model, cheap_effort),
            (secondary_model, secondary_effort),
        ],
    )
