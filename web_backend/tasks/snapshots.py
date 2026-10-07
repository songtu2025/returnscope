from __future__ import annotations

from typing import Any


class TaskSnapshotsMixin:
    """集中创建与重新规划共用的冻结快照及模型策略读取。"""

    @staticmethod
    def _dataset_version_snapshot(version: dict[str, Any]) -> dict[str, Any]:
        return {
            "dataset_id": version["dataset_id"],
            "version_id": version["id"],
            "version": version["version"],
            "name": version["dataset_name"],
            "sha256": version["sha256"],
        }

    @staticmethod
    def _model_config_snapshot(
        config: dict[str, Any],
        model_policy: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return {
            "version_id": config["id"],
            "version": config["version"],
            "connection_id": config["connection_id"],
            "connection": config["connection_name"],
            "strategy_source": "task" if model_policy else "connection",
            "primary_model": config["primary_model"],
            "primary_effort": config["primary_effort"],
            "cheap_model": config["cheap_model"],
            "cheap_effort": config["cheap_effort"],
            "cheap_audit_percent": config["cheap_audit_percent"],
            "secondary_model": config["secondary_model"],
            "secondary_effort": config["secondary_effort"],
        }

    @staticmethod
    def _execution_plan_snapshot(
        response: dict[str, Any],
        plan_hash: str,
        unresolved_policy: str,
        segment_order: list[str],
    ) -> dict[str, Any]:
        summary = {
            key: value
            for key, value in response.items()
            if key
            not in {
                "inputs",
                "plan_hash",
                "registry_version",
                "unresolved_product_count",
                "unresolved_products",
                "category_options",
            }
        }
        return {
            "registry_version": response["registry_version"],
            "plan_hash": plan_hash,
            "unresolved_policy": unresolved_policy,
            "segment_order": segment_order,
            "summary": summary,
        }

    @staticmethod
    def _snapshot_model_policy(task: dict[str, Any]) -> dict[str, Any] | None:
        config = task.get("snapshot", {}).get("config", {})
        if config.get("strategy_source") != "task":
            return None
        connection_id = config.get("connection_id")
        primary_model = config.get("primary_model")
        if not connection_id or not primary_model:
            return None
        return {
            "connection_id": connection_id,
            "cheap_model": config.get("cheap_model"),
            "cheap_effort": config.get("cheap_effort") or "low",
            "primary_model": primary_model,
            "primary_effort": config.get("primary_effort") or "medium",
            "secondary_model": config.get("secondary_model"),
            "secondary_effort": config.get("secondary_effort") or "high",
            "cheap_audit_percent": config.get("cheap_audit_percent", 5),
        }
