from __future__ import annotations

from typing import Any, Callable

from web_backend.database import Database
from web_backend.model_catalog import ModelCatalogService
from web_backend.model_probe import ModelProbe
from web_backend.model_services.validation_execution import _ValidationRunExecution
from web_backend.model_services.validation_records import _ValidationTarget


class ValidationRunService(_ValidationRunExecution):
    def __init__(
        self,
        database: Database,
        model_catalog: ModelCatalogService,
        model_probe: ModelProbe,
        get_version: Callable[..., dict[str, Any] | None],
    ) -> None:
        self.database = database
        self.model_catalog = model_catalog
        self.model_probe = model_probe
        self.get_version = get_version

    def start_model_validation(
        self,
        model_id: str,
        actor_id: str,
        effort: str | None = None,
    ) -> dict[str, Any]:
        model, chosen_effort, version_id = self.model_catalog.prepare_validation(
            model_id, effort
        )
        config = self.get_version(version_id)
        if config is None:
            raise ValueError("API 配置不存在")
        return self._create_validation_run(
            target=_ValidationTarget(
                kind="model",
                target_id=model_id,
                connection_id=str(model["connection_id"]),
                config_version_id=version_id,
            ),
            actor_id=actor_id,
            config=config,
            items=[
                self._validation_item(
                    model,
                    chosen_effort,
                    "单模型验证",
                )
            ],
        )

    def start_config_validation(
        self,
        version_id: str,
        actor_id: str,
    ) -> dict[str, Any]:
        config = self.get_version(version_id)
        if config is None:
            raise ValueError("配置版本不存在")
        pipeline = [
            (config.get("cheap_model"), config["cheap_effort"], "低成本初筛"),
            (config["primary_model"], config["primary_effort"], "主分析"),
            (
                config.get("secondary_model"),
                config["secondary_effort"],
                "风险二次复核",
            ),
        ]
        with self.database.connect() as connection:
            self.model_catalog.ensure_pipeline_models(
                connection,
                str(config["connection_id"]),
                [(model, effort) for model, effort, _role in pipeline],
            )
        items: list[dict[str, Any]] = []
        by_key: dict[str, dict[str, Any]] = {}
        for model_key, effort, role in pipeline:
            if not model_key:
                continue
            existing = by_key.get(str(model_key))
            if existing:
                existing["role"] = f"{existing['role']} / {role}"
                continue
            model = self.model_catalog.get_by_key(
                str(config["connection_id"]),
                str(model_key),
            )
            if model is None:
                raise ValueError(f"模型 {model_key} 不存在")
            item = self._validation_item(model, str(effort), role)
            items.append(item)
            by_key[str(model_key)] = item
        return self._create_validation_run(
            target=_ValidationTarget(
                kind="config",
                target_id=version_id,
                connection_id=str(config["connection_id"]),
                config_version_id=version_id,
            ),
            actor_id=actor_id,
            config=config,
            items=items,
        )

    @staticmethod
    def _validation_item(
        model: dict[str, Any],
        effort: str,
        role: str,
    ) -> dict[str, Any]:
        return {
            "model_id": model["id"],
            "model_key": model["model_key"],
            "display_name": model["display_name"],
            "effort": effort,
            "role": role,
            "status": "pending",
            "stage": "queued",
            "message": "等待验证",
            "duration_ms": None,
            "http_status": None,
            "response_model": None,
            "error_category": None,
            "suggestion": None,
            "started_at": None,
            "completed_at": None,
        }
