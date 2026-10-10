from __future__ import annotations

from typing import Any

EFFORTS = {"low", "medium", "high"}
DEFAULT_EFFORTS = ["low", "medium", "high"]
MODEL_VALIDATION_MESSAGE_LIMIT = 500


def validate_effort(value: str, field_name: str) -> str:
    effort = value.strip().lower()
    if effort not in EFFORTS:
        raise ValueError(f"{field_name} 仅支持 low、medium、high")
    return effort


def validate_supported_efforts(values: list[str]) -> list[str]:
    efforts = []
    for value in values:
        effort = validate_effort(value, "模型推理强度")
        if effort not in efforts:
            efforts.append(effort)
    if not efforts:
        raise ValueError("至少选择一种模型推理强度")
    return efforts


def clean_model_definition(value: dict[str, Any]) -> dict[str, Any]:
    model_key = str(value.get("model_key", "")).strip()
    if not model_key:
        raise ValueError("模型 ID 不能为空")
    if len(model_key) > 120:
        raise ValueError("模型 ID 不能超过 120 个字符")
    display_name = str(value.get("display_name", "")).strip() or model_key
    if len(display_name) > 80:
        raise ValueError("模型显示名称不能超过 80 个字符")
    efforts = validate_supported_efforts(
        list(value.get("supported_efforts") or DEFAULT_EFFORTS)
    )
    return {
        "model_key": model_key,
        "display_name": display_name,
        "supported_efforts": efforts,
        "active": bool(value.get("active", True)),
    }
