from __future__ import annotations

import builtins
from typing import Any

from return_semantics.model_client import Sub2APISettings
from web_backend.common import add_audit
from web_backend.database import Database
from web_backend.model_catalog import (
    ModelCatalogService,
)
from web_backend.model_probe import ModelProbe
from web_backend.model_services.config_creation import _ConfigVersionCreation
from web_backend.model_services.config_inputs import (
    _CreateVersionInput,
    _prepare_create_version,
)
from web_backend.model_services.config_lifecycle import _ConfigVersionLifecycle
from web_backend.model_services.config_models import _ConfigModelOperations
from web_backend.security import SecretBox
from web_backend.validation_run_service import ValidationRunService


class ConfigService(
    _ConfigVersionCreation, _ConfigVersionLifecycle, _ConfigModelOperations
):
    def __init__(self, database: Database, secret_box: SecretBox) -> None:
        self.database = database
        self.secret_box = secret_box
        self.model_catalog = ModelCatalogService(database)
        self.model_probe = ModelProbe()
        self.validation_runs = ValidationRunService(
            database=database,
            model_catalog=self.model_catalog,
            model_probe=self.model_probe,
            get_version=self.get_version,
        )

    def list(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            connections = connection.execute(
                """
                SELECT c.*, u.display_name AS creator_name
                FROM api_connections c
                JOIN users u ON u.id = c.created_by
                ORDER BY c.updated_at DESC
                """
            ).fetchall()
            versions = connection.execute(
                """
                SELECT v.*, u.display_name AS creator_name
                FROM api_config_versions v
                JOIN users u ON u.id = v.created_by
                ORDER BY v.connection_id, v.version DESC
                """
            ).fetchall()
            models = connection.execute(
                """
                SELECT m.*, creator.display_name AS creator_name,
                       updater.display_name AS updater_name
                FROM api_models m
                JOIN users creator ON creator.id = m.created_by
                JOIN users updater ON updater.id = m.updated_by
                ORDER BY m.connection_id, m.active DESC, m.updated_at DESC
                """
            ).fetchall()
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in versions:
            item = self._serialize(dict(row))
            grouped.setdefault(str(row["connection_id"]), []).append(item)
        grouped_models: dict[str, list[dict[str, Any]]] = {}
        for row in models:
            item = self.model_catalog.serialize(dict(row))
            grouped_models.setdefault(str(row["connection_id"]), []).append(item)
        output = []
        for row in connections:
            item = dict(row)
            item["versions"] = grouped.get(str(row["id"]), [])
            item["models"] = grouped_models.get(str(row["id"]), [])
            item["active_version"] = next(
                (
                    version
                    for version in item["versions"]
                    if version["id"] == row["active_version_id"]
                ),
                None,
            )
            output.append(item)
        return output

    def get_version(
        self,
        version_id: str,
        include_secret: bool = False,
    ) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT v.*, c.name AS connection_name, c.provider,
                       c.active_version_id
                FROM api_config_versions v
                JOIN api_connections c ON c.id = v.connection_id
                WHERE v.id = ?
                """,
                (version_id,),
            ).fetchone()
        if row is None:
            return None
        item = dict(row)
        if include_secret:
            item["api_key"] = self.secret_box.decrypt(str(item["api_key_ciphertext"]))
        return self._serialize(item)

    def start_model_validation(
        self,
        model_id: str,
        actor_id: str,
        effort: str | None = None,
    ) -> dict[str, Any]:
        return self.validation_runs.start_model_validation(
            model_id,
            actor_id,
            effort,
        )

    def start_config_validation(
        self,
        version_id: str,
        actor_id: str,
    ) -> dict[str, Any]:
        return self.validation_runs.start_config_validation(
            version_id,
            actor_id,
        )

    def get_validation_run(self, run_id: str) -> dict[str, Any] | None:
        return self.validation_runs.get_validation_run(run_id)

    def latest_active_validation_run(
        self,
        connection_id: str,
    ) -> dict[str, Any] | None:
        return self.validation_runs.latest_active_validation_run(connection_id)

    def validation_events(
        self,
        run_id: str,
        after_id: int = 0,
    ) -> builtins.list[dict[str, Any]]:
        return self.validation_runs.validation_events(run_id, after_id)

    def recover_validation_runs(self) -> None:
        self.validation_runs.recover_validation_runs()

    def run_validation(self, run_id: str) -> None:
        self.validation_runs.run_validation(run_id)

    def create_version(
        self,
        actor_id: str,
        name: str,
        provider: str,
        base_url: str,
        api_key: str,
        primary_model: str,
        primary_effort: str,
        cheap_model: str | None,
        cheap_effort: str,
        secondary_model: str | None,
        secondary_effort: str,
        cheap_audit_percent: int,
        requests_per_minute: int,
        max_workers: int,
        timeout_seconds: int,
        change_note: str,
        connection_id: str | None = None,
        models: builtins.list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        context = _prepare_create_version(
            _CreateVersionInput(
                actor_id=actor_id,
                name=name,
                provider=provider,
                base_url=base_url,
                api_key=api_key,
                primary_model=primary_model,
                primary_effort=primary_effort,
                cheap_model=cheap_model,
                cheap_effort=cheap_effort,
                secondary_model=secondary_model,
                secondary_effort=secondary_effort,
                cheap_audit_percent=cheap_audit_percent,
                requests_per_minute=requests_per_minute,
                max_workers=max_workers,
                timeout_seconds=timeout_seconds,
                change_note=change_note,
                connection_id=connection_id,
                models=models,
            )
        )
        connection_context = self._persist_created_version(context)
        add_audit(
            self.database,
            "api_connection",
            context.connection_id,
            "create_version",
            actor_id,
            after={
                "version": connection_context.version,
                "version_id": context.version_id,
                "note": context.values.change_note,
            },
        )
        return self.get_version(context.version_id) or {}

    def active_version(self) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT active_version_id FROM api_connections
                WHERE active_version_id IS NOT NULL
                ORDER BY updated_at DESC LIMIT 1
                """
            ).fetchone()
        return self.get_version(str(row["active_version_id"])) if row else None

    def build_model_settings(self, version_id: str) -> Sub2APISettings:
        config = self.get_version(version_id, include_secret=True)
        if config is None:
            raise ValueError("任务使用的 API 配置不存在")
        return Sub2APISettings(
            api_key=str(config["api_key"]),
            model=str(config["primary_model"]),
            base_url=str(config["base_url"]),
            timeout_seconds=int(config["timeout_seconds"]),
            secondary_model=config.get("secondary_model"),
            cheap_model=config.get("cheap_model"),
            reasoning_effort=str(config["primary_effort"]),
            cheap_reasoning_effort=str(config["cheap_effort"]),
            secondary_reasoning_effort=str(config["secondary_effort"]),
            cheap_model_audit_percent=int(config["cheap_audit_percent"]),
            requests_per_minute=int(config["requests_per_minute"]),
            max_workers=int(config["max_workers"]),
        )

    def _serialize(self, item: dict[str, Any]) -> dict[str, Any]:
        cipher = item.pop("api_key_ciphertext", "")
        suffix = self.secret_box.decrypt(cipher)[-4:] if cipher else ""
        item["api_key_masked"] = f"••••{suffix}" if suffix else ""
        return item
