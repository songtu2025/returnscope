from __future__ import annotations

from typing import Any

from web_backend.database import Database
from web_backend.operations.workbench_actions import _actions
from web_backend.operations.workbench_common import ACTION_PRIORITY, _actor, _time_key
from web_backend.operations.workbench_outputs import _recent_outputs


class WorkbenchService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def summary(self, limit: int = 5) -> dict[str, Any]:
        with self.database.connect() as connection:
            actions = self._actions(connection)
            recent_outputs = self._recent_outputs(connection, limit)
            counts = dict(
                connection.execute(
                    """
                    SELECT
                      (SELECT COUNT(*) FROM tasks
                       WHERE status = 'blocked') AS blocked_tasks,
                      (SELECT COUNT(*) FROM task_segments
                       WHERE status = 'blocked') AS blocked_segments,
                      (SELECT COUNT(*) FROM task_segments
                       WHERE status = 'failed') AS failed_segments,
                      (SELECT COUNT(*) FROM tasks
                       WHERE status = 'paused') AS paused_tasks,
                      (SELECT COUNT(*) FROM task_segments
                       WHERE status = 'paused') AS paused_segments,
                      (SELECT COUNT(*) FROM classification_result_versions
                       WHERE publish_status = 'published'
                         AND quality_status = 'review_required')
                        AS review_required_results,
                      (SELECT COUNT(*) FROM classification_result_versions
                       WHERE publish_status = 'published'
                         AND quality_status = 'ready') AS ready_results,
                      (SELECT COUNT(*) FROM analysis_dashboards
                       WHERE status = 'active') AS dashboards,
                      (SELECT COUNT(*) FROM ai_insight_reports
                       WHERE status IN ('queued', 'running')) AS running_reports,
                      (SELECT COUNT(*) FROM ai_insight_reports
                       WHERE status = 'failed') AS failed_reports
                    """
                ).fetchone()
            )
        actions.sort(
            key=lambda item: (
                ACTION_PRIORITY[item["type"]],
                -self._time_key(item.get("updated_at")),
                str(item["object_id"]),
            )
        )
        return {
            "actions": actions[:limit],
            "recent_outputs": recent_outputs,
            "counts": {key: int(value or 0) for key, value in counts.items()},
        }

    _actions = staticmethod(_actions)
    _actor = staticmethod(_actor)
    _time_key = staticmethod(_time_key)
    _recent_outputs = staticmethod(_recent_outputs)
