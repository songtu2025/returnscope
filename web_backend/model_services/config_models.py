from __future__ import annotations

import builtins
from typing import TYPE_CHECKING, Any

from web_backend.database import Database
from web_backend.model_catalog import DEFAULT_EFFORTS, ModelCatalogService
from web_backend.model_probe import ModelProbe


class _ConfigModelOperations:
    """同步接入方目录并维护模型及其同步验证结果。"""

    database: Database
    model_catalog: ModelCatalogService
    model_probe: ModelProbe

    if TYPE_CHECKING:

        def list(self) -> builtins.list[dict[str, Any]]: ...

        def get_version(
            self, version_id: str, include_secret: bool = False
        ) -> dict[str, Any] | None: ...

    def get_model(self, model_id: str) -> dict[str, Any] | None:
        return self.model_catalog.get(model_id)

    def add_model(
        self,
        connection_id: str,
        actor_id: str,
        model_key: str,
        display_name: str,
        supported_efforts: builtins.list[str],
        active: bool = True,
    ) -> dict[str, Any]:
        return self.model_catalog.add(
            connection_id=connection_id,
            actor_id=actor_id,
            model_key=model_key,
            display_name=display_name,
            supported_efforts=supported_efforts,
            active=active,
        )

    def update_model(
        self,
        model_id: str,
        actor_id: str,
        display_name: str,
        supported_efforts: builtins.list[str],
        active: bool,
    ) -> dict[str, Any]:
        return self.model_catalog.update(
            model_id=model_id,
            actor_id=actor_id,
            display_name=display_name,
            supported_efforts=supported_efforts,
            active=active,
        )

    def sync_models_from_provider(
        self,
        connection_id: str,
        actor_id: str,
    ) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT id FROM api_config_versions
                WHERE connection_id = ?
                ORDER BY version DESC LIMIT 1
                """,
                (connection_id,),
            ).fetchone()
        if row is None:
            raise ValueError("请先保存 API 接入配置，再读取模型目录")
        config = self.get_version(str(row["id"]), include_secret=True)
        if config is None:
            raise ValueError("API 配置不存在")
        model_keys = self.model_probe.list_models(config)
        model_connection = next(
            (item for item in self.list() if item["id"] == connection_id),
            None,
        )
        if model_connection is None:
            raise ValueError("API 接入不存在")
        existing = {item["model_key"]: item for item in model_connection["models"]}
        discovered = set(model_keys)
        for model_key in model_keys:
            model = existing.get(model_key)
            if model is None:
                self.add_model(
                    connection_id,
                    actor_id,
                    model_key,
                    model_key,
                    DEFAULT_EFFORTS,
                )
            elif not model["active"]:
                self.update_model(
                    model["id"],
                    actor_id,
                    model["display_name"],
                    model["supported_efforts"],
                    True,
                )
        for model_key, model in existing.items():
            if model_key not in discovered and model["active"]:
                self.update_model(
                    model["id"],
                    actor_id,
                    model["display_name"],
                    model["supported_efforts"],
                    False,
                )
        return {"model_keys": model_keys, "count": len(model_keys)}

    def validate_model(
        self,
        model_id: str,
        actor_id: str,
        effort: str | None = None,
    ) -> dict[str, Any]:
        model, chosen_effort, version_id = self.model_catalog.prepare_validation(
            model_id, effort
        )
        config = self.get_version(version_id, include_secret=True)
        if config is None:
            raise ValueError("API 配置不存在")
        try:
            self.model_probe.test(config, model["model_key"], chosen_effort)
        except Exception as exc:
            message = str(exc)[:500]
            self.model_catalog.set_validation(
                model,
                "failed",
                message,
                actor_id,
            )
            raise ValueError(message) from exc
        self.model_catalog.set_validation(
            model,
            "validated",
            f"使用 {chosen_effort} 推理强度测试通过",
            actor_id,
        )
        return self.get_model(model_id) or {}
