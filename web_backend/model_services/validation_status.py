from typing import Any

from web_backend.common import add_audit
from web_backend.database import Database
from web_backend.security import utc_now


class ModelValidationStatusMixin:
    database: Database

    def set_validation(
        self,
        model: dict[str, Any],
        status: str,
        message: str,
        actor_id: str,
        *,
        validation_run_id: str | None = None,
    ) -> None:
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            if (
                validation_run_id is not None
                and connection.execute(
                    "SELECT 1 FROM api_validation_runs WHERE id=? AND status='running'",
                    (validation_run_id,),
                ).fetchone()
                is None
            ):
                return
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
