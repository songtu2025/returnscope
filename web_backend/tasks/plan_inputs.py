from __future__ import annotations

import json
from typing import Any

from web_backend.database import Database


class TaskPlanInputsMixin:
    database: Database

    def _load_inputs(
        self,
        dataset_version_id: str,
        product_version_id: str,
        config_version_id: str | None,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        with self.database.connect() as connection:
            returns_row = connection.execute(
                """
                SELECT v.*, d.name AS dataset_name, d.kind
                FROM dataset_versions v
                JOIN datasets d ON d.id = v.dataset_id
                WHERE v.id = ? AND d.archived_at IS NULL
                """,
                (dataset_version_id,),
            ).fetchone()
            products_row = connection.execute(
                """
                SELECT v.*, d.name AS dataset_name, d.kind
                FROM dataset_versions v
                JOIN datasets d ON d.id = v.dataset_id
                WHERE v.id = ? AND d.archived_at IS NULL
                """,
                (product_version_id,),
            ).fetchone()
            if config_version_id:
                config_row = connection.execute(
                    """
                    SELECT v.*, c.name AS connection_name,
                           c.active_version_id
                    FROM api_config_versions v
                    JOIN api_connections c ON c.id = v.connection_id
                    WHERE v.id = ?
                    """,
                    (config_version_id,),
                ).fetchone()
            else:
                config_row = connection.execute(
                    """
                    SELECT v.*, c.name AS connection_name,
                           c.active_version_id
                    FROM api_connections c
                    JOIN api_config_versions v ON v.id = c.active_version_id
                    ORDER BY c.updated_at DESC LIMIT 1
                    """
                ).fetchone()
        if returns_row is None or returns_row["kind"] != "returns":
            raise ValueError("请选择有效的用户反馈数据版本")
        if products_row is None or products_row["kind"] != "products":
            raise ValueError("请选择有效的商品维度版本")
        if config_row is None or config_row["published_at"] is None:
            raise ValueError("请先验证并发布一个 API 配置")
        return dict(returns_row), dict(products_row), dict(config_row)

    def _apply_model_policy(
        self,
        config: dict[str, Any],
        policy: dict[str, Any],
    ) -> dict[str, Any]:
        connection_id = str(policy.get("connection_id") or "")
        if connection_id != str(config["connection_id"]):
            raise ValueError("本次模型策略与所选模型服务连接不一致")
        values = {
            "cheap_model": (policy.get("cheap_model") or "").strip() or None,
            "cheap_effort": str(policy.get("cheap_effort") or "low"),
            "primary_model": str(policy.get("primary_model") or "").strip(),
            "primary_effort": str(policy.get("primary_effort") or "medium"),
            "secondary_model": (policy.get("secondary_model") or "").strip() or None,
            "secondary_effort": str(policy.get("secondary_effort") or "high"),
            "cheap_audit_percent": int(policy.get("cheap_audit_percent", 5)),
        }
        if not values["primary_model"]:
            raise ValueError("主分析模型不能为空")
        with self.database.connect() as connection:
            active = connection.execute(
                "SELECT active_version_id FROM api_connections WHERE id = ?",
                (connection_id,),
            ).fetchone()
            if active is None or str(active["active_version_id"] or "") != str(
                config["id"]
            ):
                raise ValueError("请选择当前已发布的模型服务连接")
            for model_key, effort in (
                (values["cheap_model"], values["cheap_effort"]),
                (values["primary_model"], values["primary_effort"]),
                (values["secondary_model"], values["secondary_effort"]),
            ):
                if not model_key:
                    continue
                row = connection.execute(
                    """
                    SELECT display_name, supported_efforts_json, active, validation_status
                    FROM api_models WHERE connection_id = ? AND model_key = ?
                    """,
                    (connection_id, model_key),
                ).fetchone()
                if row is None or not row["active"]:
                    raise ValueError(f"模型 {model_key} 不可用")
                if row["validation_status"] != "validated":
                    raise ValueError(f"模型 {row['display_name']} 必须先验证通过")
                if effort not in json.loads(row["supported_efforts_json"]):
                    raise ValueError(
                        f"模型 {row['display_name']} 不支持 {effort} 推理强度"
                    )
        return {**config, **values}
