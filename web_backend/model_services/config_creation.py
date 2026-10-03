from __future__ import annotations

from typing import Any

from web_backend.database import Database
from web_backend.model_catalog import DEFAULT_EFFORTS, ModelCatalogService
from web_backend.model_services.config_inputs import (
    _ConnectionVersionContext,
    _CreateVersionContext,
)
from web_backend.security import SecretBox


class _ConfigVersionCreation:
    """在同一事务中创建连接、模型目录和配置版本。"""

    database: Database
    secret_box: SecretBox
    model_catalog: ModelCatalogService

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
