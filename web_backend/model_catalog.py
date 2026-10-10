from __future__ import annotations

import json
from typing import Any

from web_backend.common import add_audit, new_id
from web_backend.database import Database
from web_backend.model_services import catalog_definitions as _definitions
from web_backend.security import utc_now

EFFORTS = _definitions.EFFORTS
DEFAULT_EFFORTS = _definitions.DEFAULT_EFFORTS
MODEL_VALIDATION_MESSAGE_LIMIT = _definitions.MODEL_VALIDATION_MESSAGE_LIMIT
validate_effort = _definitions.validate_effort
validate_supported_efforts = _definitions.validate_supported_efforts
clean_model_definition = _definitions.clean_model_definition


class ModelCatalogService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def get(self, model_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT m.*, creator.display_name AS creator_name,
                       updater.display_name AS updater_name
                FROM api_models m
                JOIN users creator ON creator.id = m.created_by
                JOIN users updater ON updater.id = m.updated_by
                WHERE m.id = ?
                """,
                (model_id,),
            ).fetchone()
        return self.serialize(dict(row)) if row else None

    def prepare_validation(
        self,
        model_id: str,
        effort: str | None,
    ) -> tuple[dict[str, Any], str, str]:
        model = self.get(model_id)
        if model is None:
            raise ValueError("模型不存在")
        if not model["active"]:
            raise ValueError("停用模型不能验证")
        chosen_effort = effort or (
            "medium"
            if "medium" in model["supported_efforts"]
            else model["supported_efforts"][0]
        )
        chosen_effort = validate_effort(chosen_effort, "模型推理强度")
        if chosen_effort not in model["supported_efforts"]:
            raise ValueError("所选推理强度不在模型支持范围内")
        with self.database.connect() as connection:
            version = connection.execute(
                """
                SELECT id FROM api_config_versions
                WHERE connection_id = ?
                ORDER BY version DESC LIMIT 1
                """,
                (model["connection_id"],),
            ).fetchone()
        if version is None:
            raise ValueError("请先保存 API 接入配置，再验证模型")
        return model, chosen_effort, str(version["id"])

    def add(
        self,
        connection_id: str,
        actor_id: str,
        model_key: str,
        display_name: str,
        supported_efforts: list[str],
        active: bool = True,
    ) -> dict[str, Any]:
        definition = clean_model_definition(
            {
                "model_key": model_key,
                "display_name": display_name,
                "supported_efforts": supported_efforts,
                "active": active,
            }
        )
        model_id = new_id("model")
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            exists = connection.execute(
                "SELECT 1 FROM api_connections WHERE id = ?",
                (connection_id,),
            ).fetchone()
            if exists is None:
                raise ValueError("API 接入不存在")
            duplicate = connection.execute(
                """
                SELECT 1 FROM api_models
                WHERE connection_id = ? AND model_key = ?
                """,
                (connection_id, definition["model_key"]),
            ).fetchone()
            if duplicate:
                raise ValueError("该模型 ID 已存在")
            self.insert_model_row(
                connection,
                connection_id,
                actor_id,
                now,
                definition,
                model_id=model_id,
            )
        add_audit(
            self.database,
            "api_model",
            model_id,
            "create",
            actor_id,
            after=definition,
        )
        return self.get(model_id) or {}

    def update(
        self,
        model_id: str,
        actor_id: str,
        display_name: str,
        supported_efforts: list[str],
        active: bool,
    ) -> dict[str, Any]:
        before = self.get(model_id)
        if before is None:
            raise ValueError("模型不存在")
        definition = clean_model_definition(
            {
                "model_key": before["model_key"],
                "display_name": display_name,
                "supported_efforts": supported_efforts,
                "active": active,
            }
        )
        efforts_changed = before["supported_efforts"] != definition["supported_efforts"]
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                UPDATE api_models
                SET display_name = ?, supported_efforts_json = ?, active = ?,
                    validation_status = ?, validation_message = ?,
                    validated_at = ?, updated_by = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    definition["display_name"],
                    json.dumps(definition["supported_efforts"]),
                    int(definition["active"]),
                    "draft" if efforts_changed else before["validation_status"],
                    "" if efforts_changed else before["validation_message"],
                    None if efforts_changed else before["validated_at"],
                    actor_id,
                    now,
                    model_id,
                ),
            )
        after = self.get(model_id) or {}
        add_audit(
            self.database,
            "api_model",
            model_id,
            "update",
            actor_id,
            before=self.audit_value(before),
            after=self.audit_value(after),
        )
        return after

    def get_by_key(
        self,
        connection_id: str,
        model_key: str,
    ) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT id FROM api_models
                WHERE connection_id = ? AND model_key = ?
                """,
                (connection_id, model_key),
            ).fetchone()
        return self.get(str(row["id"])) if row else None

    def set_validation(
        self,
        model: dict[str, Any],
        status: str,
        message: str,
        actor_id: str,
    ) -> None:
        now = utc_now()
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE api_models
                SET validation_status = ?, validation_message = ?,
                    validated_at = ?, updated_by = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, message, now, actor_id, now, model["id"]),
            )
        add_audit(
            self.database,
            "api_model",
            str(model["id"]),
            "validate",
            actor_id,
            before={"status": model["validation_status"]},
            after={"status": status, "message": message},
        )

    @staticmethod
    def insert_model_row(
        connection: Any,
        connection_id: str,
        actor_id: str,
        now: str,
        definition: dict[str, Any],
        model_id: str | None = None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO api_models(
                id, connection_id, model_key, display_name,
                supported_efforts_json, active, validation_status,
                created_by, created_at, updated_by, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'draft', ?, ?, ?, ?)
            """,
            (
                model_id or new_id("model"),
                connection_id,
                definition["model_key"],
                definition["display_name"],
                json.dumps(definition["supported_efforts"]),
                int(definition["active"]),
                actor_id,
                now,
                actor_id,
                now,
            ),
        )

    @staticmethod
    def ensure_pipeline_models(
        connection: Any,
        connection_id: str,
        models: list[tuple[str | None, str]],
        require_validated: bool = False,
    ) -> None:
        for model_key, effort in models:
            if not model_key:
                continue
            row = connection.execute(
                """
                SELECT display_name, supported_efforts_json, active,
                       validation_status
                FROM api_models
                WHERE connection_id = ? AND model_key = ?
                """,
                (connection_id, model_key),
            ).fetchone()
            if row is None:
                raise ValueError(f"模型 {model_key} 不在当前接入的模型列表中")
            if not row["active"]:
                raise ValueError(f"模型 {row['display_name']} 已停用")
            if require_validated and row["validation_status"] != "validated":
                raise ValueError(f"模型 {row['display_name']} 必须先验证通过")
            supported_efforts = json.loads(row["supported_efforts_json"])
            if effort not in supported_efforts:
                raise ValueError(f"模型 {row['display_name']} 不支持 {effort} 推理强度")

    @staticmethod
    def audit_value(model: dict[str, Any]) -> dict[str, Any]:
        return {
            "model_key": model.get("model_key"),
            "display_name": model.get("display_name"),
            "supported_efforts": model.get("supported_efforts"),
            "active": model.get("active"),
            "validation_status": model.get("validation_status"),
        }

    @staticmethod
    def serialize(item: dict[str, Any]) -> dict[str, Any]:
        item["supported_efforts"] = json.loads(item.pop("supported_efforts_json"))
        item["active"] = bool(item["active"])
        return item


# 保持现有公开校验入口的模块归属。
for _entry in (validate_effort, validate_supported_efforts, clean_model_definition):
    _entry.__module__ = __name__
del _entry
