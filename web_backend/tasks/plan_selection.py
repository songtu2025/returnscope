from __future__ import annotations

from typing import Any

from web_backend.task_contracts import TaskPlanConflict


def selected_plan(
    response: dict[str, Any], selected_keys: list[str] | None
) -> dict[str, Any]:
    if selected_keys is None:
        return response
    segments = response["segments"]
    available = {item["segment_key"] for item in segments}
    requested = set(selected_keys)
    if not requested:
        raise ValueError("请至少选择一个 Listing")
    if len(requested) != len(selected_keys) or not requested.issubset(available):
        raise TaskPlanConflict("所选分组与最新执行计划不一致，请重新预检")
    chosen = [item for item in segments if item["segment_key"] in requested]
    # 同一店铺和Listing作为整体选择，不能遗漏该Listing的其他品类分组。
    scopes = [item.get("scope", {}) for item in chosen]
    if any(
        item.get("scope", {}) in scopes and item["segment_key"] not in requested
        for item in segments
    ):
        raise ValueError("请选择该 Listing 的全部执行分组")
    ready = sum(
        item["unique_comments"] for item in chosen if item["status"] != "blocked"
    )
    blocked = sum(
        item["unique_comments"] for item in chosen if item["status"] == "blocked"
    )
    return {
        **response,
        "segments": chosen,
        "record_count": sum(item["record_count"] for item in chosen),
        "valid_comment_count": sum(item["record_count"] for item in chosen),
        "unique_comment_count": ready + blocked,
        "executable_count": ready,
        "executable_record_count": sum(
            item["record_count"] for item in chosen if item["status"] != "blocked"
        ),
        "blocked_count": blocked,
        "blocked_record_count": sum(
            item["record_count"] for item in chosen if item["status"] == "blocked"
        ),
        "excluded_count": blocked,
    }


def restrict_plan_listings(
    response: dict[str, Any], listings: list[dict[str, str]] | None
) -> dict[str, Any]:
    if listings is None:
        return response
    keys = [
        item["segment_key"]
        for item in response["segments"]
        if item.get("scope", {}) in listings
    ]
    return selected_plan(response, keys)
