from __future__ import annotations

from pathlib import Path
from typing import Any

from return_semantics.capabilities import resolve_model_policy
from return_semantics.model_client import (
    Sub2APIClient,
    create_model_client,
    load_dotenv,
)
from return_semantics.schemas import TaxonomyConfig
from web_backend.agent_runner import AgentRunner
from web_backend.classification_standard_service import (
    ClassificationStandardNotFound,
    ClassificationStandardService,
)
from web_backend.config_service import ConfigService
from web_backend.database import Database
from web_backend.model_preference_service import ModelPreferenceService
from web_backend.security import SecretBox
from web_backend.settings import Settings


def load_standard_taxonomy(
    database_path: Path,
    standard_id: str,
    standard_version_id: str | None,
) -> tuple[TaxonomyConfig, dict[str, object]]:
    database = Database(database_path)
    database.initialize()
    service = ClassificationStandardService(database)
    if standard_version_id:
        version = service.get_version(standard_version_id)
        if version["status"] != "published":
            raise ClassificationStandardNotFound("分类标准版本尚未发布")
    else:
        version = service.current_version_for_standard(standard_id)
    taxonomy = service.taxonomy_for_version(str(version["id"]))
    return taxonomy, version


def resolve_database_path(database_path: Path | None, dotenv_path: Path) -> Path:
    load_dotenv(dotenv_path)
    return (database_path or Settings.from_env().database_path).resolve()


def _model_config(settings: Any) -> dict[str, Any]:
    return {
        "primary_model": settings.model,
        "primary_effort": settings.reasoning_effort,
        "cheap_model": settings.cheap_model,
        "cheap_effort": settings.cheap_reasoning_effort,
        "secondary_model": settings.secondary_model,
        "secondary_effort": settings.secondary_reasoning_effort,
    }


def _web_model_preference(
    database: Database,
    user_id: str | None,
) -> dict[str, Any]:
    preferences = ModelPreferenceService(database)
    if user_id:
        preference = preferences.task_policy(user_id)
        if preference is None:
            raise ValueError("指定用户尚未配置 Web 模型偏好")
        return preference
    with database.connect() as connection:
        rows = connection.execute(
            "SELECT user_id FROM user_model_preferences ORDER BY updated_at DESC"
        ).fetchall()
    if not rows:
        raise ValueError(
            "尚未配置 Web 模型偏好；请先在 Web 中配置，或显式使用 "
            "--model-config-source env"
        )
    if len(rows) > 1:
        raise ValueError("存在多个 Web 模型偏好，请指定 --model-preference-user-id")
    preference = preferences.task_policy(str(rows[0]["user_id"]))
    if preference is None:
        raise ValueError("Web 模型偏好不可用")
    return preference


def build_model_runtime(
    *,
    database_path: Path,
    dotenv_path: Path,
    source: str,
    user_id: str | None,
    standard_version: dict[str, Any],
    secondary_model: str | None,
) -> tuple[Sub2APIClient, dict[str, Any]]:
    capability = ClassificationStandardService._capability_from_snapshot(
        standard_version["snapshot"]
    )
    if source == "env":
        print("警告: 当前显式使用环境变量模型配置，不与 Web 用户偏好联动")
        base_settings = create_model_client(dotenv_path).settings
        config = _model_config(base_settings)
    else:
        app_settings = Settings.from_env()
        database = Database(database_path)
        preference = _web_model_preference(database, user_id)
        config_service = ConfigService(
            database,
            SecretBox(app_settings.encryption_key),
        )
        base_settings = config_service.build_model_settings(
            str(preference["config_version_id"])
        )
        config = preference
    if secondary_model:
        config = {**config, "secondary_model": secondary_model}
    model_policy = resolve_model_policy(capability, config)
    effective_settings = AgentRunner._settings_for_model_policy(
        base_settings,
        model_policy,
    )
    return Sub2APIClient(effective_settings), model_policy
