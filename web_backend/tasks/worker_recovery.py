from __future__ import annotations

from typing import Any

from web_backend.task_state import summarize_task_status


class TaskWorkerRecoveryMixin:
    """在同一恢复事务中处理片段请求及父任务状态。"""

    @staticmethod
    def _interrupted_segment_state(segment: Any) -> tuple[str, str | None]:
        requested_action = str(segment["requested_action"] or "")
        if requested_action == "cancel" or segment["cancel_requested"]:
            status = "cancelled"
            error = None
        elif requested_action == "pause" or segment["pause_requested"]:
            status = "paused"
            error = None
        else:
            status = "retry_pending"
            error = "服务重启，Listing 等待从检查点恢复"
        return status, error

    def _recover_running_segments(
        self,
        connection: Any,
        interrupted: list[Any],
        task_ids: set[str],
        now: str,
    ) -> None:
        for segment in interrupted:
            status, error = self._interrupted_segment_state(segment)
            connection.execute(
                """
                    UPDATE task_segments
                    SET status = ?, requested_action = NULL, error = ?,
                        started_at = CASE WHEN ? = 'retry_pending' THEN NULL
                                          ELSE started_at END,
                        completed_at = CASE WHEN ? = 'cancelled' THEN ? ELSE NULL END,
                        heartbeat_at = ?, revision = revision + 1
                    WHERE id = ?
                    """,
                (status, error, status, status, now, now, segment["id"]),
            )
            task_ids.add(str(segment["task_id"]))

    @staticmethod
    def _apply_pending_task_requests(
        connection: Any,
        flagged_tasks: list[Any],
        task_ids: set[str],
        now: str,
    ) -> None:
        for task in flagged_tasks:
            task_id = str(task["id"])
            if task["cancel_requested"]:
                connection.execute(
                    """
                        UPDATE task_segments
                        SET status = 'cancelled', requested_action = NULL,
                            error = NULL, completed_at = ?, heartbeat_at = ?,
                            revision = revision + 1
                        WHERE task_id = ?
                          AND status IN (
                              'queued', 'retry_pending', 'paused',
                              'not_started', 'blocked', 'failed'
                          )
                        """,
                    (now, now, task_id),
                )
            elif task["pause_requested"]:
                connection.execute(
                    """
                        UPDATE task_segments
                        SET status = 'paused', requested_action = NULL,
                            heartbeat_at = ?, revision = revision + 1
                        WHERE task_id = ?
                          AND status IN ('queued', 'retry_pending', 'not_started')
                        """,
                    (now, task_id),
                )
            task_ids.add(task_id)

    @staticmethod
    def _recovered_task_state(connection: Any, task_id: str) -> tuple[str, str]:
        task = connection.execute(
            """
                    SELECT cancel_requested, pause_requested
                    FROM tasks WHERE id = ?
                    """,
            (task_id,),
        ).fetchone()
        statuses = [
            str(row["status"])
            for row in connection.execute(
                "SELECT status FROM task_segments WHERE task_id = ?",
                (task_id,),
            ).fetchall()
        ]
        has_running = "running" in statuses
        if task and task["cancel_requested"] and not has_running:
            task_status = "cancelled"
        elif task and task["pause_requested"] and not has_running:
            task_status = "paused"
        else:
            task_status = summarize_task_status(statuses)
        stage = {
            "queued": "等待恢复",
            "paused": "已暂停",
            "cancelled": "已取消",
            "partial": "部分完成",
            "failed": "运行失败",
            "blocked": "等待品类处理",
            "completed": "分析完成",
            "running": "语义分析",
        }[task_status]
        return task_status, stage

    def _refresh_recovered_task(
        self,
        connection: Any,
        task_id: str,
        now: str,
    ) -> None:
        task_status, stage = self._recovered_task_state(connection, task_id)
        connection.execute(
            """
                    UPDATE tasks
                    SET status = ?, stage = ?,
                        message = '服务重启后已恢复 Listing 状态',
                        completed_at = CASE
                            WHEN ? IN ('cancelled', 'completed', 'partial',
                                       'failed', 'blocked')
                            THEN COALESCE(completed_at, ?)
                            ELSE NULL
                        END,
                        heartbeat_at = ?, revision = revision + 1
                    WHERE id = ?
                    """,
            (task_status, stage, task_status, now, now, task_id),
        )
        connection.execute(
            """
                    INSERT INTO task_events(
                        task_id, event_type, stage, message, created_at
                    ) VALUES (?, 'recovered', ?,
                              '服务重启后 Listing 状态已恢复', ?)
                    """,
            (task_id, stage, now),
        )
