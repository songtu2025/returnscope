from __future__ import annotations

import builtins
from typing import Any

from web_backend.common import json_value
from web_backend.database import Database
from web_backend.tasks.audit import TaskAuditMixin
from web_backend.tasks.detail_queries import TaskDetailQueriesMixin
from web_backend.tasks.list_queries import TaskListQueriesMixin
from web_backend.tasks.query_state import TaskQueryStateMixin


class TaskQueriesMixin(
    TaskListQueriesMixin,
    TaskDetailQueriesMixin,
    TaskQueryStateMixin,
    TaskAuditMixin,
):
    database: Database

    def events(self, task_id: str, after_id: int = 0) -> builtins.list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT e.*, u.display_name AS actor_name
                FROM task_events e
                LEFT JOIN users u ON u.id = e.actor_id
                WHERE e.task_id = ? AND e.id > ?
                ORDER BY e.id ASC
                """,
                (task_id, after_id),
            ).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            item["data"] = json_value(item.pop("data_json"), {})
            output.append(item)
        return output

    def running_count(self, owner_id: str) -> int:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM task_segments s
                JOIN tasks t ON t.id = s.task_id
                WHERE t.owner_id = ? AND s.status = 'running'
                """,
                (owner_id,),
            ).fetchone()
        return int(row["count"])
