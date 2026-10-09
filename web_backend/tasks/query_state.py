from __future__ import annotations

from typing import Any

from web_backend.common import json_value


class TaskQueryStateMixin:
    @staticmethod
    def _serialize_list(item: dict[str, Any]) -> dict[str, Any]:
        item["partial_queue"] = bool(item.get("partial_queue"))
        return item

    @staticmethod
    def _status_text(status: str) -> tuple[str, str]:
        values = {
            "queued": ("等待运行", "任务执行计划已更新并进入队列"),
            "running": ("语义分析", "Listing 片段正在运行"),
            "paused": ("已暂停", "未完成 Listing 已暂停"),
            "completed": ("分析完成", "全部任务片段已经完成"),
            "partial": ("部分完成", "已有分类结果，仍有片段待处理"),
            "blocked": ("等待品类处理", "当前没有可执行的任务片段"),
            "cancelled": ("已取消", "未完成 Listing 已取消"),
            "failed": ("运行失败", "Listing 片段运行失败"),
        }
        return values[status]

    @staticmethod
    def _segment_status(
        segment: dict[str, Any],
        unresolved_policy: str,
        has_blocked: bool,
    ) -> str:
        if segment["status"] == "blocked":
            return "blocked"
        if unresolved_policy == "block_all" and has_blocked:
            return "not_started"
        return "queued"

    @staticmethod
    def _serialize(item: dict[str, Any]) -> dict[str, Any]:
        item["snapshot"] = json_value(item.pop("snapshot_json", None), {})
        item["metrics"] = json_value(item.pop("metrics_json", None), {})
        item["cancel_requested"] = bool(item.get("cancel_requested"))
        item["pause_requested"] = bool(item.get("pause_requested"))
        return item

    @staticmethod
    def _attach_system_retry_state(
        item: dict[str, Any],
        system_failure_count: int,
    ) -> None:
        item["system_failure_count"] = system_failure_count
        item["system_retry_available"] = bool(
            item.get("status") == "completed_with_errors"
            and item.get("result_version_id")
            and system_failure_count
        )

    @classmethod
    def _serialize_segment(
        cls,
        item: dict[str, Any],
        system_failure_count: int = 0,
    ) -> dict[str, Any]:
        item["variants"] = json_value(item.pop("variants_json", None), [])
        item["scope"] = json_value(item.pop("scope_json", None), {})
        item["model_policy"] = json_value(
            item.pop("model_policy_json", None),
            None,
        )
        item.pop("classification_keys_json", None)
        requested_action = item.get("requested_action")
        item["display_status"] = (
            f"{requested_action}_pending"
            if item.get("status") == "running" and requested_action
            else item.get("status")
        )
        cls._attach_system_retry_state(item, system_failure_count)
        return item
