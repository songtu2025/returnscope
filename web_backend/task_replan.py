from __future__ import annotations

from collections.abc import Callable
from typing import Any

from return_semantics.analysis_context import analysis_context_from_snapshot
from web_backend.common import json_text
from web_backend.database import Database
from web_backend.security import utc_now
from web_backend.task_contracts import TaskPlanConflict, _ReplanSegmentSyncContext
from web_backend.task_plan_service import TaskPlanService
from web_backend.task_state import summarize_task_status
from web_backend.tasks.creation_plan import validate_unresolved_policy
from web_backend.tasks.replan_segments import TaskReplanSegmentsMixin


class TaskReplanMixin(TaskReplanSegmentsMixin):
    database: Database
    plan_service: TaskPlanService
    get: Callable[..., dict[str, Any] | None]
    _snapshot_model_policy: Callable[..., dict[str, Any] | None]
    _updated_replan_snapshot: Callable[..., tuple[dict[str, Any], dict[str, Any]]]
    _execution_plan_snapshot: Callable[..., dict[str, Any]]
    _insert_audit: Callable[..., None]
    _status_text: Callable[..., tuple[str, str]]
    _validate_task_revision: Callable[..., None]

    def replan_preflight(
        self,
        task_id: str,
        product_version_id: str,
    ) -> dict[str, Any]:
        task = self.get(task_id)
        if task is None:
            raise ValueError("任务不存在")
        if task["status"] not in {"blocked", "partial"}:
            raise ValueError("仅阻断或部分完成的任务可以重新规划")
        return self.plan_service.preflight(
            **self._replan_plan_inputs(task, product_version_id)
        )

    def replan(
        self,
        task_id: str,
        actor_id: str,
        product_version_id: str,
        expected_revision: int,
        plan_hash: str,
        unresolved_policy: str,
        reason: str,
    ) -> dict[str, Any]:
        clean_reason, model_policy, prepared, current_hash = self._prepare_replan(
            task_id=task_id,
            product_version_id=product_version_id,
            plan_hash=plan_hash,
            unresolved_policy=unresolved_policy,
            reason=reason,
        )
        planned_segments = {
            str(segment["segment_key"]): segment
            for segment in prepared.response["segments"]
        }
        planned_keys = prepared.execution_plan.classification_keys_by_segment(
            prepared.dataset
        )
        record_counts = prepared.dataset.records["classification_key"].value_counts()
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            row = self._replan_task_row(connection, task_id, expected_revision)
            old_segments = connection.execute(
                "SELECT * FROM task_segments WHERE task_id = ?",
                (task_id,),
            ).fetchall()
            preserved = self._preserved_replan_segments(
                old_segments,
                planned_segments,
                planned_keys,
            )
            self._sync_replan_segments(
                connection,
                task_id,
                _ReplanSegmentSyncContext(
                    prepared=prepared,
                    old_segments=old_segments,
                    preserved=preserved,
                    planned_segments=planned_segments,
                    planned_keys=planned_keys,
                    record_counts=record_counts,
                    current_hash=current_hash,
                    unresolved_policy=unresolved_policy,
                    now=now,
                ),
            )

            statuses = [
                str(value["status"])
                for value in connection.execute(
                    "SELECT status FROM task_segments WHERE task_id = ?",
                    (task_id,),
                ).fetchall()
            ]
            task_status = summarize_task_status(statuses) if statuses else "completed"
            stage, message = self._status_text(task_status)
            snapshot, old_plan = self._updated_replan_snapshot(
                row,
                prepared,
                model_policy,
                history_entry={
                    "replanned_at": now,
                    "actor_id": actor_id,
                    "reason": clean_reason,
                },
            )
            segment_order = [
                str(value["segment_key"])
                for value in connection.execute(
                    """
                    SELECT segment_key FROM task_segments
                    WHERE task_id = ?
                    ORDER BY execution_order, segment_key
                    """,
                    (task_id,),
                ).fetchall()
            ]
            snapshot["execution_plan"] = self._execution_plan_snapshot(
                prepared.response,
                current_hash,
                unresolved_policy,
                segment_order,
            )
            connection.execute(
                """
                UPDATE tasks
                SET product_version_id = ?, snapshot_json = ?, status = ?,
                    stage = ?, message = ?, error = NULL,
                    cancel_requested = 0, started_at = NULL,
                    completed_at = CASE WHEN ? IN ('completed', 'partial')
                                        THEN ? ELSE NULL END,
                    revision = revision + 1, heartbeat_at = ?
                WHERE id = ? AND revision = ?
                """,
                (
                    product_version_id,
                    json_text(snapshot),
                    task_status,
                    stage,
                    message,
                    task_status,
                    now,
                    now,
                    task_id,
                    expected_revision,
                ),
            )
            event_data: dict[str, Any] = {
                "before": {
                    "product_version_id": row["product_version_id"],
                    "plan_hash": old_plan.get("plan_hash"),
                },
                "after": {
                    "product_version_id": product_version_id,
                    "plan_hash": current_hash,
                    "status": task_status,
                },
                "reason": clean_reason,
            }
            connection.execute(
                """
                INSERT INTO task_events(
                    task_id, event_type, stage, message, actor_id,
                    data_json, created_at
                ) VALUES (?, 'replanned', ?, '任务执行计划已更新', ?, ?, ?)
                """,
                (task_id, stage, actor_id, json_text(event_data), now),
            )
            self._insert_audit(
                connection,
                task_id,
                "replan",
                actor_id,
                event_data["before"],
                event_data["after"] | {"reason": clean_reason},
                now,
            )
        return self.get(task_id) or {}

    def _prepare_replan(
        self,
        *,
        task_id: str,
        product_version_id: str,
        plan_hash: str,
        unresolved_policy: str,
        reason: str,
    ) -> tuple[str, dict[str, Any] | None, Any, str]:
        clean_reason = reason.strip()
        if not clean_reason:
            raise ValueError("请填写重新规划原因")
        validate_unresolved_policy(unresolved_policy)
        source = self.get(task_id)
        if source is None:
            raise ValueError("任务不存在")
        plan_inputs = self._replan_plan_inputs(source, product_version_id)
        model_policy = plan_inputs["model_policy"]
        prepared = self.plan_service.prepare(**plan_inputs)
        current_hash = str(prepared.response["plan_hash"])
        if current_hash != plan_hash:
            raise TaskPlanConflict("执行计划已变化，请重新预检后再提交")
        return clean_reason, model_policy, prepared, current_hash

    def _replan_plan_inputs(
        self, task: dict[str, Any], product_version_id: str
    ) -> dict[str, Any]:
        snapshot_scope = task.get("snapshot", {}).get("scope", {})
        task_snapshot = task.get("snapshot", {})
        model_policy = self._snapshot_model_policy(task)
        return {
            "dataset_version_id": str(task["dataset_version_id"]),
            "product_version_id": product_version_id,
            "store": (
                None if snapshot_scope.get("mode") == "auto" else str(task["store"])
            ),
            "listing": None
            if snapshot_scope.get("mode") == "auto"
            else task["listing"],
            "config_version_id": str(task["config_version_id"]),
            "model_policy": model_policy,
            "analysis_context": analysis_context_from_snapshot(task_snapshot),
        }

    def _replan_task_row(
        self,
        connection: Any,
        task_id: str,
        expected_revision: int,
    ) -> Any:
        row = connection.execute(
            """
            SELECT revision, status, snapshot_json, product_version_id
            FROM tasks WHERE id = ?
            """,
            (task_id,),
        ).fetchone()
        self._validate_task_revision(row, expected_revision)
        if row["status"] not in {"blocked", "partial"}:
            raise ValueError("仅阻断或部分完成的任务可以重新规划")
        return row
