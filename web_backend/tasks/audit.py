from __future__ import annotations

from typing import Any

from web_backend.common import insert_audit


class TaskAuditMixin:
    @staticmethod
    def _insert_audit(
        connection: Any,
        task_id: str,
        action: str,
        actor_id: str,
        before: dict[str, Any],
        after: dict[str, Any],
        created_at: str,
    ) -> None:
        insert_audit(
            connection,
            "task",
            task_id,
            action,
            actor_id,
            before,
            after,
            created_at,
        )
