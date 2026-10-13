from __future__ import annotations

from collections.abc import Callable
from typing import Any

from web_backend.common import json_text
from web_backend.database import Database
from web_backend.security import utc_now
from web_backend.task_execution.parent_refresh_state import _parent_refresh_state


class TaskSegmentRemovalMixin:
    database: Database
    get: Callable[..., dict[str, Any] | None]
    _segment_action_target: Callable[..., tuple[Any, Any]]
    _status_text: Callable[..., tuple[str, str]]
    _insert_audit: Callable[..., None]

    def set_segment_deleted(
        self,
        task_id: str,
        segment_key: str,
        actor_id: str,
        expected_revision: int,
        *,
        deleted: bool,
    ) -> dict[str, Any]:
        now = utc_now()
        action = "delete" if deleted else "restore"
        with self.database.transaction(immediate=True) as connection:
            task, segment = self._segment_action_target(
                connection,
                task_id,
                segment_key,
                expected_revision,
                include_deleted=True,
            )
            if bool(segment["deleted_at"]) == deleted:
                raise ValueError("Listing 已删除" if deleted else "Listing 未删除")
            if deleted and (
                segment["status"]
                not in {"failed", "cancelled", "completed", "completed_with_errors"}
                or segment["requested_action"]
            ):
                raise ValueError("请先取消并等待 Listing 停止后再删除")
            connection.execute(
                "UPDATE task_segments SET deleted_at=?, revision=revision+1 WHERE id=?",
                (now if deleted else None, segment["id"]),
            )
            segments = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM task_segments WHERE task_id=?",
                    (task_id,),
                )
            ]
            state = _parent_refresh_state(
                dict(task),
                segments,
                lambda status, _: self._status_text(status),
            )
            connection.execute(
                """UPDATE tasks SET status=?,stage=?,message=?,error=NULL,
                   progress_current=?,progress_total=?,progress_percent=?,
                   result_file_path=NULL,completed_at=?,heartbeat_at=?,
                   revision=revision+1 WHERE id=?""",
                (
                    state.status,
                    state.stage,
                    state.message,
                    state.current,
                    state.total,
                    state.percent,
                    now if state.terminal else None,
                    now,
                    task_id,
                ),
            )
            message = (
                "Listing 已删除，结果和看板保留"
                if deleted
                else "Listing 已恢复，不会自动执行"
            )
            connection.execute(
                """INSERT INTO task_events(task_id,event_type,stage,message,actor_id,data_json,created_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (
                    task_id,
                    f"segment_{action}",
                    state.stage,
                    message,
                    actor_id,
                    json_text({"segment_key": segment_key}),
                    now,
                ),
            )
            self._insert_audit(
                connection,
                task_id,
                f"segment_{action}",
                actor_id,
                {"segment_key": segment_key, "deleted_at": segment["deleted_at"]},
                {"segment_key": segment_key, "deleted_at": now if deleted else None},
                now,
            )
        return self.get(task_id) or {}
