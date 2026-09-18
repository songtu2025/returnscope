from __future__ import annotations

from collections.abc import Callable
from typing import Any

from return_semantics.analysis_context import analysis_context_from_snapshot
from web_backend.common import json_text, json_value
from web_backend.database import Database
from web_backend.security import utc_now
from web_backend.task_contracts import TaskPlanConflict, _ReplanSegmentSyncContext
from web_backend.task_plan_service import TaskPlanService
from web_backend.task_state import summarize_task_status


class TaskReplanMixin:
    database: Database
    plan_service: TaskPlanService
    get: Callable[..., dict[str, Any] | None]
    _snapshot_model_policy: Callable[..., dict[str, Any] | None]
    _dataset_version_snapshot: Callable[..., dict[str, Any]]
    _model_config_snapshot: Callable[..., dict[str, Any]]
    _execution_plan_snapshot: Callable[..., dict[str, Any]]
    _insert_audit: Callable[..., None]
    _status_text: Callable[..., tuple[str, str]]
    _insert_segment: Callable[..., None]
    _variants_for_keys: Callable[..., list[dict[str, Any]]]
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
        snapshot_scope = task.get("snapshot", {}).get("scope", {})
        task_snapshot = task.get("snapshot", {})
        model_policy = self._snapshot_model_policy(task)
        return self.plan_service.preflight(
            dataset_version_id=str(task["dataset_version_id"]),
            product_version_id=product_version_id,
            store=(
                None if snapshot_scope.get("mode") == "auto" else str(task["store"])
            ),
            listing=(None if snapshot_scope.get("mode") == "auto" else task["listing"]),
            config_version_id=str(task["config_version_id"]),
            model_policy=model_policy,
            analysis_context=analysis_context_from_snapshot(task_snapshot),
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
            snapshot = json_value(row["snapshot_json"], {})
            old_plan = snapshot.get("execution_plan", {})
            history = snapshot.setdefault("execution_plan_history", [])
            history.append(
                {
                    "plan": old_plan,
                    "replanned_at": now,
                    "actor_id": actor_id,
                    "reason": clean_reason,
                }
            )
            snapshot["products"] = self._dataset_version_snapshot(prepared.products)
            snapshot["config"] = self._model_config_snapshot(
                prepared.config,
                model_policy,
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
            event_data = {
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
        if unresolved_policy not in {"block_all", "run_ready"}:
            raise ValueError("未解决品类策略仅支持 block_all 或 run_ready")
        source = self.get(task_id)
        if source is None:
            raise ValueError("任务不存在")
        source_scope = source.get("snapshot", {}).get("scope", {})
        source_snapshot = source.get("snapshot", {})
        model_policy = self._snapshot_model_policy(source)
        prepared = self.plan_service.prepare(
            dataset_version_id=str(source["dataset_version_id"]),
            product_version_id=product_version_id,
            store=(
                None if source_scope.get("mode") == "auto" else str(source["store"])
            ),
            listing=(None if source_scope.get("mode") == "auto" else source["listing"]),
            config_version_id=str(source["config_version_id"]),
            model_policy=model_policy,
            analysis_context=analysis_context_from_snapshot(source_snapshot),
        )
        current_hash = str(prepared.response["plan_hash"])
        if current_hash != plan_hash:
            raise TaskPlanConflict("执行计划已变化，请重新预检后再提交")
        return clean_reason, model_policy, prepared, current_hash

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

    @staticmethod
    def _preserved_replan_segments(
        old_segments: list[Any],
        planned_segments: dict[str, Any],
        planned_keys: dict[str, list[str]],
    ) -> dict[str, Any]:
        preserved: dict[str, Any] = {}
        protected_statuses = {"completed", "completed_with_errors"}
        for old_segment in old_segments:
            agent_key = str(old_segment["agent_key"])
            segment_key = str(old_segment["segment_key"])
            if (
                agent_key == "unknown"
                or old_segment["status"] not in protected_statuses
                or segment_key not in planned_segments
            ):
                continue
            keys = set(json_value(old_segment["classification_keys_json"], []))
            new_keys = set(planned_keys.get(segment_key, []))
            if not keys or not keys.issubset(new_keys):
                raise TaskPlanConflict(
                    f"已完成片段 {segment_key} 的数据范围发生变化，不能覆盖原结果"
                )
            preserved[segment_key] = old_segment
        return preserved

    def _sync_replan_segments(
        self,
        connection: Any,
        task_id: str,
        context: _ReplanSegmentSyncContext,
    ) -> None:
        for old_segment in context.old_segments:
            if str(old_segment["segment_key"]) not in context.preserved:
                connection.execute(
                    "DELETE FROM task_segments WHERE id = ?",
                    (old_segment["id"],),
                )

        preserved_keys_by_segment = {
            segment_key: set(json_value(segment["classification_keys_json"], []))
            for segment_key, segment in context.preserved.items()
        }
        has_blocked = int(context.prepared.response["blocked_count"]) > 0
        next_execution_order = max(
            (int(value["execution_order"]) for value in context.preserved.values()),
            default=0,
        )
        for planned_segment_key, segment in context.planned_segments.items():
            remaining_keys = [
                key
                for key in context.planned_keys.get(planned_segment_key, [])
                if key not in preserved_keys_by_segment.get(planned_segment_key, set())
            ]
            if not remaining_keys:
                continue
            segment_key = planned_segment_key
            if planned_segment_key in context.preserved:
                segment_key = f"{planned_segment_key}:{context.current_hash[:12]}"
            next_execution_order += 1
            self._insert_segment(
                connection,
                task_id=task_id,
                segment=segment,
                segment_key=segment_key,
                classification_keys=remaining_keys,
                record_count=int(
                    sum(context.record_counts.get(key, 0) for key in remaining_keys)
                ),
                unique_comments=len(remaining_keys),
                variants=self._variants_for_keys(
                    context.prepared.dataset,
                    remaining_keys,
                ),
                execution_order=next_execution_order,
                unresolved_policy=context.unresolved_policy,
                has_blocked=has_blocked,
                created_at=context.now,
            )
