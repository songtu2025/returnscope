from __future__ import annotations

from typing import TYPE_CHECKING, Any

from web_backend.common import add_audit
from web_backend.database import Database
from web_backend.model_catalog import (
    MODEL_VALIDATION_MESSAGE_LIMIT,
    ModelCatalogService,
)
from web_backend.model_probe import ModelProbe
from web_backend.security import utc_now


class _ConfigVersionLifecycle:
    """维护草稿放弃、同步验证及已发布配置的生命周期。"""

    database: Database
    model_catalog: ModelCatalogService
    model_probe: ModelProbe

    if TYPE_CHECKING:

        def get_version(
            self, version_id: str, include_secret: bool = False
        ) -> dict[str, Any] | None: ...

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
        try:
            tested_count = self._validate_pipeline_models(config, models, actor_id)
            status = "validated"
            message = f"连接与 {tested_count} 个模型均测试通过"
        except Exception as exc:
            status = "failed"
            message = str(exc)[:MODEL_VALIDATION_MESSAGE_LIMIT]
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

    def _validate_pipeline_models(
        self,
        config: dict[str, Any],
        models: list[tuple[str | None, str]],
        actor_id: str,
    ) -> int:
        tested: list[str] = []
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
                        str(exc)[:MODEL_VALIDATION_MESSAGE_LIMIT],
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
        return len(tested)

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
