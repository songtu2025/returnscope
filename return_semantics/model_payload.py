from __future__ import annotations

import json
from typing import Any


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


def _normalize_unknown_semantic(item: Any) -> Any:
    if isinstance(item, str):
        return {
            "opinion": item,
            "evidence": item,
            "reason": "模型未提供未映射原因",
        }
    if not isinstance(item, dict):
        return item
    opinion_key = "opinion" if "opinion" in item else "description"
    if opinion_key in item and "evidence" in item:
        return {
            "opinion": item[opinion_key],
            "evidence": item["evidence"],
            "reason": item.get("reason", "模型未提供未映射原因"),
        }
    if "text" in item:
        normalized = dict(item)
        text = normalized.pop("text")
        normalized.setdefault("opinion", text)
        normalized.setdefault("evidence", text)
        return normalized
    return item


def normalize_model_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    semantic_units = list(normalized.get("semantic_units", []))
    unknown_semantics = []
    for item in normalized.get("unknown_semantics", []):
        if isinstance(item, dict) and item.get("label_code"):
            semantic_units.append(item)
        else:
            unknown_semantics.append(_normalize_unknown_semantic(item))
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


def _output_text_parts(item: Any) -> list[str]:
    if not isinstance(item, dict):
        return []
    parts = []
    for content in item.get("content", []):
        if not isinstance(content, dict):
            continue
        if content.get("type") == "output_text":
            text = content.get("text")
            if isinstance(text, str):
                parts.append(text)
    return parts
