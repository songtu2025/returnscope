from typing import Any

from web_backend.common import add_audit
from web_backend.database import Database
from web_backend.model_catalog import ModelCatalogService, validate_effort
from web_backend.security import utc_now


class ModelPreferenceService:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.model_catalog = ModelCatalogService(database)

    def get(self, user_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT p.*, c.name AS connection_name, c.active_version_id
                FROM user_model_preferences p
                JOIN api_connections c ON c.id = p.connection_id
                WHERE p.user_id = ?
                """,
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return self._serialize(dict(row))

    def save(self, user_id: str, **payload: Any) -> dict[str, Any]:
        connection_id = str(payload["connection_id"])
        primary_model = str(payload["primary_model"]).strip()
        cheap_model = (payload.get("cheap_model") or "").strip() or None
        secondary_model = (payload.get("secondary_model") or "").strip() or None
        policy = {
            "connection_id": connection_id,
            "cheap_model": cheap_model,
            "cheap_effort": validate_effort(
                str(payload["cheap_effort"]), "低成本初筛推理强度"
            ),
            "primary_model": primary_model,
            "primary_effort": validate_effort(
                str(payload["primary_effort"]), "主分析推理强度"
            ),
            "secondary_model": secondary_model,
            "secondary_effort": validate_effort(
                str(payload["secondary_effort"]), "风险复核推理强度"
            ),
            "cheap_audit_percent": int(payload["cheap_audit_percent"]),
        }
        if not primary_model:
            raise ValueError("主分析模型不能为空")
        if not 0 <= policy["cheap_audit_percent"] <= 100:
            raise ValueError("初筛抽检比例必须在 0 到 100 之间")
        self._validate_policy(policy)
        before = self.get(user_id)
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                INSERT INTO user_model_preferences(
                    user_id, connection_id, cheap_model, cheap_effort,
                    primary_model, primary_effort, secondary_model, secondary_effort,
                    cheap_audit_percent, updated_at, updated_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    connection_id = excluded.connection_id,
                    cheap_model = excluded.cheap_model,
                    cheap_effort = excluded.cheap_effort,
                    primary_model = excluded.primary_model,
                    primary_effort = excluded.primary_effort,
                    secondary_model = excluded.secondary_model,
                    secondary_effort = excluded.secondary_effort,
                    cheap_audit_percent = excluded.cheap_audit_percent,
                    updated_at = excluded.updated_at,
                    updated_by = excluded.updated_by
                """,
                (
                    user_id,
                    policy["connection_id"],
                    policy["cheap_model"],
                    policy["cheap_effort"],
                    policy["primary_model"],
                    policy["primary_effort"],
                    policy["secondary_model"],
                    policy["secondary_effort"],
                    policy["cheap_audit_percent"],
                    now,
                    user_id,
                ),
            )
        value = self.get(user_id) or {}
        add_audit(
            self.database,
            "user_model_preference",
            user_id,
            "save",
            user_id,
            before=self._audit_value(before),
            after=self._audit_value(value),
        )
        return value

    def task_policy(self, user_id: str) -> dict[str, Any] | None:
        preference = self.get(user_id)
        if preference is None:
            return None
        self._validate_policy(preference)
        return preference

    def _validate_policy(self, policy: dict[str, Any]) -> None:
        with self.database.connect() as connection:
            active_version = connection.execute(
                """
                SELECT active_version_id FROM api_connections
                WHERE id = ?
                """,
                (policy["connection_id"],),
            ).fetchone()
            if active_version is None or not active_version["active_version_id"]:
                raise ValueError("请选择已发布的模型服务连接")
            self.model_catalog.ensure_pipeline_models(
                connection,
                policy["connection_id"],
                [
                    (policy["cheap_model"], policy["cheap_effort"]),
                    (policy["primary_model"], policy["primary_effort"]),
                    (policy["secondary_model"], policy["secondary_effort"]),
                ],
                require_validated=True,
            )

    @staticmethod
    def _serialize(value: dict[str, Any]) -> dict[str, Any]:
        value["config_version_id"] = value.pop("active_version_id")
        return value

    @staticmethod
    def _audit_value(value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return None
        return {
            key: value.get(key)
            for key in (
                "connection_id",
                "cheap_model",
                "cheap_effort",
                "primary_model",
                "primary_effort",
                "secondary_model",
                "secondary_effort",
                "cheap_audit_percent",
            )
        }
