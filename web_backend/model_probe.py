from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from typing import Any, Callable


class ModelValidationError(ValueError):
    def __init__(
        self,
        message: str,
        category: str,
        suggestion: str,
        http_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.suggestion = suggestion
        self.http_status = http_status


def _extract_output_text(response: dict[str, Any]) -> str:
    parts = []
    for item in response.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                parts.append(str(content.get("text", "")))
    return "".join(parts).strip()


class ModelProbe:
    @staticmethod
    def list_models(config: dict[str, Any]) -> list[str]:
        request = urllib.request.Request(
            url=f"{str(config['base_url']).rstrip('/')}/models",
            headers={"Authorization": f"Bearer {config['api_key']}"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=int(config["timeout_seconds"]),
            ) as response:
                raw_body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:300]
            raise ModelValidationError(
                f"读取模型目录失败：HTTP {exc.code} {body}",
                "catalog_request",
                "请确认上游服务支持 /models 接口且密钥具备读取模型目录的权限",
                exc.code,
            ) from exc
        except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
            raise ModelValidationError(
                f"读取模型目录失败：{exc}",
                "catalog_request",
                "请检查 Base URL、网络连接和上游服务状态",
            ) from exc
        try:
            payload = json.loads(raw_body)
            items = payload.get("data") if isinstance(payload, dict) else payload
            model_ids = sorted(
                {
                    str(item.get("id", "")).strip()
                    for item in items
                    if isinstance(item, dict) and str(item.get("id", "")).strip()
                }
            )
        except (AttributeError, TypeError, json.JSONDecodeError) as exc:
            raise ModelValidationError(
                "模型目录返回格式不正确",
                "catalog_response",
                "请确认上游服务的 /models 接口返回 OpenAI 兼容的 data[].id 列表",
            ) from exc
        if not model_ids:
            raise ModelValidationError(
                "模型目录未返回可用模型",
                "catalog_response",
                "请确认当前密钥已获授权访问至少一个模型",
            )
        return model_ids

    @staticmethod
    def test(
        config: dict[str, Any],
        model: str,
        effort: str,
        on_stage: Callable[[str, str, dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        started = time.monotonic()
        payload = {
            "model": model,
            "input": "仅返回 OK",
            "reasoning": {"effort": effort},
        }
        request = urllib.request.Request(
            url=f"{str(config['base_url']).rstrip('/')}/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {config['api_key']}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        if on_stage:
            on_stage("requesting", "正在发送测试请求并等待模型响应", {})
        try:
            with urllib.request.urlopen(
                request,
                timeout=int(config["timeout_seconds"]),
            ) as response:
                http_status = int(getattr(response, "status", 200))
                raw_body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:300]
            category = "http_error"
            suggestion = "请检查接入地址和上游服务状态"
            if exc.code in {401, 403}:
                category = "authentication"
                suggestion = "请检查 API 密钥是否正确且具备模型访问权限"
            elif exc.code == 404:
                category = "model_not_found"
                suggestion = "请检查 Base URL 和模型 ID 是否正确"
            elif exc.code == 429:
                category = "rate_limited"
                suggestion = "请检查配额或稍后重新验证"
            raise ModelValidationError(
                f"{model} 测试失败：HTTP {exc.code} {body}",
                category,
                suggestion,
                exc.code,
            ) from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise ModelValidationError(
                    f"{model} 请求超时",
                    "timeout",
                    "请检查网络、上游模型状态或适当增加请求超时时间",
                ) from exc
            raise ModelValidationError(
                f"{model} 连接失败：{exc.reason}",
                "connection",
                "请检查 Base URL、网络连接和上游服务状态",
            ) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise ModelValidationError(
                f"{model} 请求超时",
                "timeout",
                "请检查网络、上游模型状态或适当增加请求超时时间",
            ) from exc
        if on_stage:
            on_stage(
                "checking",
                f"已收到 HTTP {http_status}，正在检查响应结构",
                {"http_status": http_status},
            )
        try:
            result = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise ModelValidationError(
                f"{model} 返回的内容不是有效 JSON",
                "response_format",
                "请确认接口兼容 Responses API 响应格式",
                http_status,
            ) from exc
        output_text = _extract_output_text(result)
        if not output_text:
            raise ModelValidationError(
                f"{model} 返回内容为空",
                "empty_response",
                "请确认模型能够返回 output_text 内容",
                http_status,
            )
        return {
            "http_status": http_status,
            "duration_ms": round((time.monotonic() - started) * 1000),
            "response_model": str(result.get("model") or model),
            "output_chars": len(output_text),
        }
