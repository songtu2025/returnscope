from __future__ import annotations

import builtins
from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import urlparse

from return_semantics.model_client import Sub2APISettings
from web_backend.common import add_audit, new_id
from web_backend.database import Database
from web_backend.model_catalog import (
    DEFAULT_EFFORTS,
    ModelCatalogService,
    clean_model_definition,
    validate_effort,
)
from web_backend.model_probe import ModelProbe
from web_backend.security import SecretBox, utc_now
from web_backend.validation_run_service import ValidationRunService


def _validate_url(value: str) -> str:
    url = value.strip().rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Base URL 必须是有效的 HTTP 或 HTTPS 地址")
    if parsed.scheme != "https" and parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("非本地 API 必须使用 HTTPS")
    return url


@dataclass(frozen=True)
class _CreateVersionInput:
    actor_id: str
    name: str
    provider: str
    base_url: str
    api_key: str
    primary_model: str
    primary_effort: str
    cheap_model: str | None
    cheap_effort: str
    secondary_model: str | None
    secondary_effort: str
    cheap_audit_percent: int
    requests_per_minute: int
    max_workers: int
    timeout_seconds: int
    change_note: str
    connection_id: str | None
    models: list[dict[str, Any]] | None


@dataclass(frozen=True)
class _CreateVersionContext:
    values: _CreateVersionInput
    connection_id: str
    version_id: str
    now: str
    model_definitions: list[dict[str, Any]]
    model_keys: list[str]
    selected_models: list[tuple[str | None, str]]


@dataclass(frozen=True)
class _ConnectionVersionContext:
    version: int
    api_key_ciphertext: str
    is_new_connection: bool


def _prepare_create_version(values: _CreateVersionInput) -> _CreateVersionContext:
    base_url = _validate_url(values.base_url)
    primary_model = values.primary_model.strip()
    if not primary_model:
        raise ValueError("主模型不能为空")
    primary_effort = validate_effort(values.primary_effort, "主模型推理强度")
    cheap_model = (values.cheap_model or "").strip() or None
    cheap_effort = validate_effort(values.cheap_effort, "低成本模型推理强度")
    secondary_model = (values.secondary_model or "").strip() or None
    secondary_effort = validate_effort(
        values.secondary_effort,
        "二次复核模型推理强度",
    )
    if not 0 <= values.cheap_audit_percent <= 100:
        raise ValueError("低成本模型抽检比例必须在 0 到 100 之间")
    if not 1 <= values.requests_per_minute <= 10000:
        raise ValueError("每分钟请求数必须在 1 到 10000 之间")
    if not 1 <= values.max_workers <= 16:
        raise ValueError("单任务并发必须在 1 到 16 之间")
    if not 5 <= values.timeout_seconds <= 600:
        raise ValueError("请求超时必须在 5 到 600 秒之间")
    change_note = values.change_note.strip()
    if not change_note:
        raise ValueError("请填写配置变更原因")
    model_definitions = [
        clean_model_definition(value) for value in (values.models or [])
    ]
    model_keys = [value["model_key"] for value in model_definitions]
    if len(model_keys) != len(set(model_keys)):
        raise ValueError("模型列表中存在重复的模型 ID")
    normalized_values = replace(
        values,
        base_url=base_url,
        primary_model=primary_model,
        primary_effort=primary_effort,
        cheap_model=cheap_model,
        cheap_effort=cheap_effort,
        secondary_model=secondary_model,
        secondary_effort=secondary_effort,
        change_note=change_note,
    )
    return _CreateVersionContext(
        values=normalized_values,
        connection_id=values.connection_id or new_id("conn"),
        version_id=new_id("cfg"),
        now=utc_now(),
        model_definitions=model_definitions,
        model_keys=model_keys,
        selected_models=[
            (primary_model, primary_effort),
            (cheap_model, cheap_effort),
            (secondary_model, secondary_effort),
        ],
    )


class ConfigService:
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

    def _persist_created_version(
        self,
        context: _CreateVersionContext,
    ) -> _ConnectionVersionContext:
        with self.database.transaction(immediate=True) as connection:
            connection_context = self._prepare_connection_version(
                connection,
                context,
            )
            self._prepare_model_catalog(connection, context, connection_context)
            self._insert_config_version(connection, context, connection_context)
        return connection_context

    def _prepare_connection_version(
        self,
        connection: Any,
        context: _CreateVersionContext,
    ) -> _ConnectionVersionContext:
        values = context.values
        existing = connection.execute(
            "SELECT * FROM api_connections WHERE id = ?",
            (context.connection_id,),
        ).fetchone()
        is_new_connection = existing is None
        api_key_ciphertext = ""
        if is_new_connection:
            if not values.name.strip():
                raise ValueError("接入名称不能为空")
            connection.execute(
                """
                INSERT INTO api_connections(
                    id, name, provider, created_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    context.connection_id,
                    values.name.strip(),
                    values.provider.strip() or "responses-compatible",
                    values.actor_id,
                    context.now,
                    context.now,
                ),
            )
            version = 1
        else:
            latest = connection.execute(
                """
                SELECT version, api_key_ciphertext
                FROM api_config_versions
                WHERE connection_id = ?
                ORDER BY version DESC LIMIT 1
                """,
                (context.connection_id,),
            ).fetchone()
            version = int(latest["version"]) + 1
            if not values.api_key.strip():
                api_key_ciphertext = str(latest["api_key_ciphertext"])
        if values.api_key.strip():
            api_key_ciphertext = self.secret_box.encrypt(values.api_key.strip())
        elif is_new_connection:
            raise ValueError("API 密钥不能为空")
        return _ConnectionVersionContext(
            version=version,
            api_key_ciphertext=api_key_ciphertext,
            is_new_connection=is_new_connection,
        )

    def _prepare_model_catalog(
        self,
        connection: Any,
        context: _CreateVersionContext,
        connection_context: _ConnectionVersionContext,
    ) -> None:
        if connection_context.is_new_connection:
            for definition in context.model_definitions:
                self.model_catalog.insert_model_row(
                    connection,
                    context.connection_id,
                    context.values.actor_id,
                    context.now,
                    definition,
                )
            for model_key, _effort in context.selected_models:
                if not model_key or model_key in context.model_keys:
                    continue
                self.model_catalog.insert_model_row(
                    connection,
                    context.connection_id,
                    context.values.actor_id,
                    context.now,
                    {
                        "model_key": model_key,
                        "display_name": model_key,
                        "supported_efforts": DEFAULT_EFFORTS,
                        "active": True,
                    },
                )
        elif context.model_definitions:
            raise ValueError("已有接入请通过模型列表单独维护模型")
        self.model_catalog.ensure_pipeline_models(
            connection,
            context.connection_id,
            context.selected_models,
        )

    @staticmethod
    def _insert_config_version(
        connection: Any,
        context: _CreateVersionContext,
        connection_context: _ConnectionVersionContext,
    ) -> None:
        values = context.values
        connection.execute(
            """
            INSERT INTO api_config_versions(
                id, connection_id, version, base_url, api_key_ciphertext,
                primary_model, primary_effort, cheap_model, cheap_effort,
                secondary_model, secondary_effort, cheap_audit_percent,
                requests_per_minute, max_workers, timeout_seconds,
                change_note, validation_status, created_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      ?, 'draft', ?, ?)
            """,
            (
                context.version_id,
                context.connection_id,
                connection_context.version,
                values.base_url,
                connection_context.api_key_ciphertext,
                values.primary_model,
                values.primary_effort,
                values.cheap_model,
                values.cheap_effort,
                values.secondary_model,
                values.secondary_effort,
                values.cheap_audit_percent,
                values.requests_per_minute,
                values.max_workers,
                values.timeout_seconds,
                values.change_note,
                values.actor_id,
                context.now,
            ),
        )
        connection.execute(
            "UPDATE api_connections SET updated_at = ? WHERE id = ?",
            (context.now, context.connection_id),
        )

    def discard_draft(self, version_id: str, actor_id: str) -> dict[str, Any]:
        """放弃未发布的草稿及其验证记录。"""
        config = self.get_version(version_id)
        if config is None:
            raise ValueError("配置版本不存在")
        if config.get("published_at"):
            raise ValueError("已发布版本不能放弃")
        if config.get("active_version_id") == version_id:
            raise ValueError("当前运行版本不能放弃")

        with self.database.transaction(immediate=True) as connection:
            task_reference = connection.execute(
                "SELECT id FROM tasks WHERE config_version_id = ? LIMIT 1",
                (version_id,),
            ).fetchone()
            if task_reference:
                raise ValueError("已有任务使用该版本，不能放弃")
            active_run = connection.execute(
                """
                SELECT id FROM api_validation_runs
                WHERE config_version_id = ? AND status IN ('queued', 'running')
                LIMIT 1
                """,
                (version_id,),
            ).fetchone()
            if active_run:
                raise ValueError("该草稿正在验证，完成后再放弃")
            connection.execute(
                "DELETE FROM api_validation_runs WHERE config_version_id = ?",
                (version_id,),
            )
            connection.execute(
                "DELETE FROM api_config_versions WHERE id = ?",
                (version_id,),
            )
            connection.execute(
                "UPDATE api_connections SET updated_at = ? WHERE id = ?",
                (utc_now(), config["connection_id"]),
            )
        add_audit(
            self.database,
            "api_connection",
            str(config["connection_id"]),
            "discard_draft",
            actor_id,
            before={
                "version": config["version"],
                "version_id": version_id,
                "note": config["change_note"],
            },
        )
        return {
            "id": version_id,
            "connection_id": config["connection_id"],
            "version": config["version"],
        }

    def validate(self, version_id: str, actor_id: str) -> dict[str, Any]:
        config = self.get_version(version_id, include_secret=True)
        if config is None:
            raise ValueError("配置版本不存在")
        models = [
            (config["primary_model"], config["primary_effort"]),
            (config.get("cheap_model"), config["cheap_effort"]),
            (config.get("secondary_model"), config["secondary_effort"]),
        ]
        with self.database.connect() as connection:
            self.model_catalog.ensure_pipeline_models(
                connection,
                str(config["connection_id"]),
                models,
            )
        tested = []
        try:
            for model, effort in models:
                if not model or model in tested:
                    continue
                catalog_model = self.model_catalog.get_by_key(
                    str(config["connection_id"]),
                    str(model),
                )
                try:
                    self.model_probe.test(config, str(model), str(effort))
                except Exception as exc:
                    if catalog_model:
                        self.model_catalog.set_validation(
                            catalog_model,
                            "failed",
                            str(exc)[:500],
                            actor_id,
                        )
                    raise
                if catalog_model:
                    self.model_catalog.set_validation(
                        catalog_model,
                        "validated",
                        f"使用 {effort} 推理强度测试通过",
                        actor_id,
                    )
                tested.append(model)
            status = "validated"
            message = f"连接与 {len(tested)} 个模型均测试通过"
        except Exception as exc:
            status = "failed"
            message = str(exc)[:500]
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE api_config_versions
                SET validation_status = ?, validation_message = ?,
                    validated_at = ?
                WHERE id = ?
                """,
                (status, message, utc_now(), version_id),
            )
        add_audit(
            self.database,
            "api_config_version",
            version_id,
            "validate",
            actor_id,
            after={"status": status, "message": message},
        )
        result = self.get_version(version_id) or {}
        if status == "failed":
            raise ValueError(message)
        return result

    def publish(self, version_id: str, actor_id: str) -> dict[str, Any]:
        config = self.get_version(version_id)
        if config is None:
            raise ValueError("配置版本不存在")
        if config["validation_status"] != "validated":
            raise ValueError("配置必须先验证通过才能发布")
        with self.database.connect() as connection:
            self.model_catalog.ensure_pipeline_models(
                connection,
                str(config["connection_id"]),
                [
                    (config["primary_model"], config["primary_effort"]),
                    (config.get("cheap_model"), config["cheap_effort"]),
                    (
                        config.get("secondary_model"),
                        config["secondary_effort"],
                    ),
                ],
                require_validated=True,
            )
        already_published = False
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            current = connection.execute(
                "SELECT active_version_id FROM api_connections WHERE id = ?",
                (config["connection_id"],),
            ).fetchone()
            already_published = bool(
                current and current["active_version_id"] == version_id
            )
            if not already_published:
                connection.execute(
                    "UPDATE api_config_versions SET published_at = ? WHERE id = ?",
                    (now, version_id),
                )
                connection.execute(
                    """
                    UPDATE api_connections
                    SET active_version_id = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (version_id, now, config["connection_id"]),
                )
        if already_published:
            return self.get_version(version_id) or {}
        add_audit(
            self.database,
            "api_connection",
            str(config["connection_id"]),
            "publish",
            actor_id,
            after={"version_id": version_id, "version": config["version"]},
        )
        return self.get_version(version_id) or {}

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
