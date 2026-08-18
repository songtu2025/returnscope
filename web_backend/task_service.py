from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from return_semantics.data import ReturnDataset
from web_backend.common import add_audit, json_text, json_value, new_id
from web_backend.database import Database
from web_backend.security import utc_now
from web_backend.task_plan_service import TaskPlanService
from web_backend.task_state import summarize_task_status

ACTIVE_STATUSES = {"queued", "running", "paused"}
FINAL_STATUSES = {"completed", "failed", "cancelled", "blocked", "partial"}
WAITING_SEGMENT_STATUSES = {"queued", "retry_pending"}
SEGMENT_USER_LIMIT = 3


class TaskRevisionConflict(ValueError):
    pass


class TaskPlanConflict(ValueError):
    pass


class TaskResultPublishConflict(ValueError):
    pass


class TaskService:
    def __init__(
        self,
        database: Database,
        plan_service: TaskPlanService | None = None,
        result_publisher: Callable[[str, str], dict[str, Any]] | None = None,
    ) -> None:
        self.database = database
        self.plan_service = plan_service or TaskPlanService(database)
        self.result_publisher = result_publisher

    def preflight(
        self,
        dataset_version_id: str,
        product_version_id: str,
        store: str | None,
        listing: str | None,
        config_version_id: str | None = None,
        model_policy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.plan_service.preflight(
            dataset_version_id=dataset_version_id,
            product_version_id=product_version_id,
            store=store,
            listing=listing,
            config_version_id=config_version_id,
            model_policy=model_policy,
        )

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
        clean_reason = reason.strip()
        if not clean_reason:
            raise ValueError("请填写重新规划原因")
        if unresolved_policy not in {"block_all", "run_ready"}:
            raise ValueError("未解决品类策略仅支持 block_all 或 run_ready")
        source = self.get(task_id)
        if source is None:
            raise ValueError("任务不存在")
        source_scope = source.get("snapshot", {}).get("scope", {})
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
        )
        current_hash = str(prepared.response["plan_hash"])
        if current_hash != plan_hash:
            raise TaskPlanConflict("执行计划已变化，请重新预检后再提交")
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
            row = connection.execute(
                """
                SELECT revision, status, snapshot_json, product_version_id
                FROM tasks WHERE id = ?
                """,
                (task_id,),
            ).fetchone()
            if row is None:
                raise ValueError("任务不存在")
            if int(row["revision"]) != expected_revision:
                raise TaskRevisionConflict("任务已被他人修改，请刷新后重试")
            if row["status"] not in {"blocked", "partial"}:
                raise ValueError("仅阻断或部分完成的任务可以重新规划")
            old_segments = connection.execute(
                "SELECT * FROM task_segments WHERE task_id = ?",
                (task_id,),
            ).fetchall()
            preserved: dict[str, Any] = {}
            protected_statuses = {
                "completed",
                "completed_with_errors",
            }
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
                if old_segment["status"] in {
                    "completed",
                    "completed_with_errors",
                } and (not keys or not keys.issubset(new_keys)):
                    raise TaskPlanConflict(
                        f"已完成片段 {segment_key} 的数据范围发生变化，不能覆盖原结果"
                    )
                preserved[str(old_segment["segment_key"])] = old_segment

            for old_segment in old_segments:
                if str(old_segment["segment_key"]) not in preserved:
                    connection.execute(
                        "DELETE FROM task_segments WHERE id = ?",
                        (old_segment["id"],),
                    )

            preserved_keys_by_segment: dict[str, set[str]] = {}
            for old_segment in preserved.values():
                preserved_keys_by_segment.setdefault(
                    str(old_segment["segment_key"]), set()
                ).update(json_value(old_segment["classification_keys_json"], []))

            has_blocked = int(prepared.response["blocked_count"]) > 0
            next_execution_order = max(
                (int(value["execution_order"]) for value in preserved.values()),
                default=0,
            )
            for planned_segment_key, segment in planned_segments.items():
                remaining_keys = [
                    key
                    for key in planned_keys.get(planned_segment_key, [])
                    if key
                    not in preserved_keys_by_segment.get(planned_segment_key, set())
                ]
                if not remaining_keys:
                    continue
                segment_key = planned_segment_key
                if any(
                    str(value["segment_key"]) == planned_segment_key
                    for value in preserved.values()
                ):
                    segment_key = f"{planned_segment_key}:{current_hash[:12]}"
                next_execution_order += 1
                self._insert_segment(
                    connection,
                    task_id=task_id,
                    segment=segment,
                    segment_key=segment_key,
                    classification_keys=remaining_keys,
                    record_count=int(
                        sum(record_counts.get(key, 0) for key in remaining_keys)
                    ),
                    unique_comments=len(remaining_keys),
                    variants=self._variants_for_keys(
                        prepared.dataset,
                        remaining_keys,
                    ),
                    execution_order=next_execution_order,
                    unresolved_policy=unresolved_policy,
                    has_blocked=has_blocked,
                    created_at=now,
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

    def reorder_segments(
        self,
        task_id: str,
        actor_id: str,
        expected_revision: int,
        segment_keys: list[str],
    ) -> dict[str, Any]:
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            task = connection.execute(
                "SELECT revision, status, stage FROM tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
            if task is None:
                raise ValueError("任务不存在")
            if int(task["revision"]) != expected_revision:
                raise TaskRevisionConflict("任务已被他人修改，请刷新后重试")
            if task["status"] not in ACTIVE_STATUSES:
                raise ValueError("仅排队中或运行中的任务可以调整片段顺序")

            rows = connection.execute(
                """
                SELECT id, segment_key, status, execution_order
                FROM task_segments
                WHERE task_id = ?
                ORDER BY execution_order, segment_key
                """,
                (task_id,),
            ).fetchall()
            movable_statuses = {"queued", "retry_pending", "paused"}
            movable_keys = [
                str(row["segment_key"])
                for row in rows
                if row["status"] in movable_statuses
            ]
            if len(segment_keys) != len(set(segment_keys)) or set(segment_keys) != set(
                movable_keys
            ):
                raise TaskRevisionConflict("等待片段已经变化，请刷新后重新排序")
            if segment_keys == movable_keys:
                return self.get(task_id) or {}

            history_rows = [
                row
                for row in rows
                if row["status"] not in movable_statuses and row["status"] != "blocked"
            ]
            movable_by_key = {
                str(row["segment_key"]): row
                for row in rows
                if row["status"] in movable_statuses
            }
            blocked_rows = [row for row in rows if row["status"] == "blocked"]
            ordered_rows = (
                history_rows
                + [movable_by_key[segment_key] for segment_key in segment_keys]
                + blocked_rows
            )
            for position, row in enumerate(ordered_rows, start=1):
                connection.execute(
                    "UPDATE task_segments SET execution_order = ? WHERE id = ?",
                    (position, row["id"]),
                )
            connection.execute(
                "UPDATE tasks SET revision = revision + 1 WHERE id = ?",
                (task_id,),
            )
            event_data = {"before": movable_keys, "after": segment_keys}
            connection.execute(
                """
                INSERT INTO task_events(
                    task_id, event_type, stage, message, actor_id,
                    data_json, created_at
                ) VALUES (?, 'segments_reordered', ?, '用户调整了片段执行顺序', ?, ?, ?)
                """,
                (
                    task_id,
                    task["stage"],
                    actor_id,
                    json_text(event_data),
                    now,
                ),
            )
            self._insert_audit(
                connection,
                task_id,
                "reorder_segments",
                actor_id,
                {"segment_order": movable_keys},
                {"segment_order": segment_keys},
                now,
            )
        return self.get(task_id) or {}

    def retry_segment(
        self,
        task_id: str,
        segment_key: str,
        actor_id: str,
        expected_revision: int,
        reason: str,
    ) -> dict[str, Any]:
        clean_reason = reason.strip()
        if not clean_reason:
            raise ValueError("请填写片段重试原因")
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            task = connection.execute(
                "SELECT revision, status, snapshot_json FROM tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
            if task is None:
                raise ValueError("任务不存在")
            if int(task["revision"]) != expected_revision:
                raise TaskRevisionConflict("任务已被他人修改，请刷新后重试")
            segment = connection.execute(
                """
                SELECT * FROM task_segments
                WHERE task_id = ? AND segment_key = ?
                """,
                (task_id, segment_key),
            ).fetchone()
            if segment is None:
                raise ValueError("任务片段不存在")
            if segment["agent_key"] == "unknown" or segment["status"] == "blocked":
                raise ValueError("未知品类仍未解决，不能直接重试")
            allowed = {"failed", "completed_with_errors", "not_started"}
            if segment["status"] not in allowed:
                raise ValueError("该片段当前状态不允许重试")
            if (
                segment["status"] == "completed_with_errors"
                and segment["result_version_id"] is not None
            ):
                raise ValueError("该片段已有分类结果版本，请通过复核批次生成新版本")
            if segment["status"] == "not_started":
                snapshot = json_value(task["snapshot_json"], {})
                policy = snapshot.get("execution_plan", {}).get(
                    "unresolved_policy",
                    "block_all",
                )
                blocked_exists = connection.execute(
                    """
                    SELECT 1 FROM task_segments
                    WHERE task_id = ? AND status = 'blocked' LIMIT 1
                    """,
                    (task_id,),
                ).fetchone()
                if policy == "block_all" and blocked_exists is not None:
                    raise ValueError("当前策略仍阻断全部片段，请先重新规划")
            connection.execute(
                """
                UPDATE task_segments
                SET status = 'retry_pending', progress_current = 0,
                    error = NULL, requested_action = NULL,
                    started_at = NULL, completed_at = NULL,
                    retry_count = retry_count + 1, revision = revision + 1
                WHERE id = ?
                """,
                (segment["id"],),
            )
            connection.execute(
                """
                UPDATE tasks
                SET status = CASE WHEN status = 'running' THEN status ELSE 'queued' END,
                    stage = '等待重试',
                    message = '任务片段已重新排队', error = NULL,
                    cancel_requested = 0, pause_requested = 0,
                    completed_at = NULL, revision = revision + 1,
                    heartbeat_at = ?
                WHERE id = ? AND revision = ?
                """,
                (now, task_id, expected_revision),
            )
            event_data = {
                "segment_key": segment_key,
                "agent_key": segment["agent_key"],
                "before_status": segment["status"],
                "after_status": "retry_pending",
                "reason": clean_reason,
            }
            connection.execute(
                """
                INSERT INTO task_events(
                    task_id, event_type, stage, message, actor_id,
                    data_json, created_at
                ) VALUES (?, 'segment_retry', '等待重试',
                          '任务片段已重新排队', ?, ?, ?)
                """,
                (task_id, actor_id, json_text(event_data), now),
            )
            self._insert_audit(
                connection,
                task_id,
                "segment_retry",
                actor_id,
                {
                    "segment_key": segment_key,
                    "status": segment["status"],
                },
                {
                    "segment_key": segment_key,
                    "status": "retry_pending",
                    "reason": clean_reason,
                },
                now,
            )
        return self.get(task_id) or {}

    def retry_result_publish(
        self,
        task_id: str,
        segment_id: str,
        actor_id: str,
        expected_revision: int,
        reason: str,
    ) -> dict[str, Any]:
        clean_reason = reason.strip()
        if not clean_reason:
            raise ValueError("请填写结果发布重试原因")
        if self.result_publisher is None:
            raise TaskResultPublishConflict("结果发布重试服务未配置")
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            task = connection.execute(
                "SELECT revision, stage FROM tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
            if task is None:
                raise ValueError("任务不存在")
            if int(task["revision"]) != expected_revision:
                raise TaskRevisionConflict("任务已被他人修改，请刷新后重试")
            segment = connection.execute(
                """
                SELECT * FROM task_segments
                WHERE task_id = ? AND id = ?
                """,
                (task_id, segment_id),
            ).fetchone()
            if segment is None:
                raise ValueError("Listing 片段不存在")
            publish_status = str(segment["result_publish_status"] or "")
            if publish_status == "publishing":
                raise TaskResultPublishConflict(
                    "Listing 分类结果正在发布，请勿重复提交"
                )
            if publish_status == "published" or segment["result_version_id"]:
                raise TaskResultPublishConflict("Listing 分类结果已经发布")
            if publish_status != "failed":
                raise TaskResultPublishConflict("Listing 分类结果不处于发布失败状态")
            if segment["status"] not in {"completed", "completed_with_errors"}:
                raise TaskResultPublishConflict("仅分类已完成的 Listing 可以重试发布")
            checkpoint_path = str(segment["result_json_path"] or "").strip()
            if not checkpoint_path or not Path(checkpoint_path).is_file():
                raise TaskResultPublishConflict("没有可用的分类检查点，不能重试发布")

            connection.execute(
                """
                UPDATE task_segments
                SET result_publish_status = 'publishing',
                    result_publish_error = NULL, revision = revision + 1,
                    heartbeat_at = ?
                WHERE id = ? AND task_id = ?
                """,
                (now, segment_id, task_id),
            )
            connection.execute(
                """
                UPDATE tasks
                SET revision = revision + 1, heartbeat_at = ?
                WHERE id = ? AND revision = ?
                """,
                (now, task_id, expected_revision),
            )
            event_data = {
                "segment_id": segment_id,
                "segment_key": segment["segment_key"],
                "before_status": "failed",
                "after_status": "publishing",
                "reason": clean_reason,
            }
            connection.execute(
                """
                INSERT INTO task_events(
                    task_id, event_type, stage, message, actor_id,
                    data_json, created_at
                ) VALUES (?, 'result_publish_retry', '生成结果',
                          '正在重试发布 Listing 分类结果', ?, ?, ?)
                """,
                (task_id, actor_id, json_text(event_data), now),
            )
            self._insert_audit(
                connection,
                task_id,
                "retry_result_publish",
                actor_id,
                {
                    "segment_id": segment_id,
                    "result_publish_status": "failed",
                },
                {
                    "segment_id": segment_id,
                    "result_publish_status": "publishing",
                    "reason": clean_reason,
                },
                now,
            )

        self.result_publisher(task_id, segment_id)
        return self.get(task_id) or {}

    def set_parallelism(
        self,
        task_id: str,
        actor_id: str,
        expected_revision: int,
        max_parallel_segments: int,
    ) -> dict[str, Any]:
        if not 1 <= max_parallel_segments <= SEGMENT_USER_LIMIT:
            raise ValueError("Listing 并行数必须在 1 到 3 之间")
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            task = connection.execute(
                """
                SELECT revision, status, max_parallel_segments, stage
                FROM tasks WHERE id = ?
                """,
                (task_id,),
            ).fetchone()
            if task is None:
                raise ValueError("任务不存在")
            if int(task["revision"]) != expected_revision:
                raise TaskRevisionConflict("任务已被他人修改，请刷新后重试")
            if task["status"] not in ACTIVE_STATUSES:
                raise ValueError("仅排队中、运行中或已暂停的任务可以调整并行数")
            before_value = int(task["max_parallel_segments"])
            if before_value == max_parallel_segments:
                return self.get(task_id) or {}
            connection.execute(
                """
                UPDATE tasks
                SET max_parallel_segments = ?, revision = revision + 1
                WHERE id = ? AND revision = ?
                """,
                (max_parallel_segments, task_id, expected_revision),
            )
            event_data = {
                "before": {"max_parallel_segments": before_value},
                "after": {"max_parallel_segments": max_parallel_segments},
            }
            connection.execute(
                """
                INSERT INTO task_events(
                    task_id, event_type, stage, message, actor_id,
                    data_json, created_at
                ) VALUES (?, 'parallelism_changed', ?, 'Listing 并行数已调整', ?, ?, ?)
                """,
                (
                    task_id,
                    task["stage"],
                    actor_id,
                    json_text(event_data),
                    now,
                ),
            )
            self._insert_audit(
                connection,
                task_id,
                "parallelism_changed",
                actor_id,
                event_data["before"],
                event_data["after"],
                now,
            )
        return self.get(task_id) or {}

    def segment_action(
        self,
        task_id: str,
        segment_key: str,
        action: str,
        actor_id: str,
        expected_revision: int,
        note: str = "",
    ) -> dict[str, Any]:
        if action not in {"pause", "resume", "cancel"}:
            raise ValueError("不支持的 Listing 操作")
        clean_note = note.strip()
        if action == "cancel" and not clean_note:
            raise ValueError("请填写取消原因")
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            task = connection.execute(
                "SELECT revision, stage, pause_requested FROM tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
            if task is None:
                raise ValueError("任务不存在")
            if int(task["revision"]) != expected_revision:
                raise TaskRevisionConflict("任务已被他人修改，请刷新后重试")
            segment = connection.execute(
                """
                SELECT id, status, requested_action, agent_key
                FROM task_segments
                WHERE task_id = ? AND segment_key = ?
                """,
                (task_id, segment_key),
            ).fetchone()
            if segment is None:
                raise ValueError("Listing 片段不存在")
            if segment["agent_key"] == "unknown" or segment["status"] == "blocked":
                raise ValueError("未配置品类不会进入 Listing 执行队列")

            before_status = str(segment["status"])
            requested_action: str | None = None
            if action == "pause":
                if before_status in WAITING_SEGMENT_STATUSES:
                    after_status = "paused"
                elif before_status == "running":
                    after_status = "running"
                    requested_action = "pause"
                else:
                    raise ValueError("当前状态不能暂停")
            elif action == "resume":
                if before_status != "paused":
                    raise ValueError("仅已暂停的 Listing 可以继续")
                after_status = "queued"
            else:
                if before_status == "running":
                    after_status = "running"
                    requested_action = "cancel"
                elif before_status in WAITING_SEGMENT_STATUSES | {"paused", "failed"}:
                    after_status = "cancelled"
                else:
                    raise ValueError("当前状态不能取消")

            connection.execute(
                """
                UPDATE task_segments
                SET status = ?, requested_action = ?,
                    completed_at = CASE WHEN ? = 'cancelled' THEN ? ELSE completed_at END,
                    revision = revision + 1
                WHERE id = ?
                """,
                (
                    after_status,
                    requested_action,
                    after_status,
                    now,
                    segment["id"],
                ),
            )
            statuses = [
                str(row["status"])
                for row in connection.execute(
                    "SELECT status FROM task_segments WHERE task_id = ?",
                    (task_id,),
                ).fetchall()
            ]
            task_status = summarize_task_status(statuses)
            stage, message = self._status_text(task_status)
            pause_requested = 0 if action == "resume" else int(task["pause_requested"])
            connection.execute(
                """
                UPDATE tasks
                SET status = ?, stage = ?, message = ?,
                    pause_requested = ?,
                    completed_at = CASE
                        WHEN ? IN ('completed', 'partial', 'cancelled', 'failed') THEN ?
                        ELSE NULL
                    END,
                    revision = revision + 1, heartbeat_at = ?
                WHERE id = ? AND revision = ?
                """,
                (
                    task_status,
                    stage,
                    message,
                    pause_requested,
                    task_status,
                    now,
                    now,
                    task_id,
                    expected_revision,
                ),
            )
            event_data = {
                "segment_key": segment_key,
                "before_status": before_status,
                "after_status": (
                    f"{action}_requested" if requested_action else after_status
                ),
                "note": clean_note,
            }
            connection.execute(
                """
                INSERT INTO task_events(
                    task_id, event_type, stage, message, actor_id,
                    data_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    f"segment_{action}",
                    stage,
                    {
                        "pause": "Listing 暂停请求已提交",
                        "resume": "Listing 已重新进入等待队列",
                        "cancel": "Listing 取消请求已提交",
                    }[action],
                    actor_id,
                    json_text(event_data),
                    now,
                ),
            )
            self._insert_audit(
                connection,
                task_id,
                f"segment_{action}",
                actor_id,
                {"segment_key": segment_key, "status": before_status},
                {
                    "segment_key": segment_key,
                    "status": event_data["after_status"],
                    "note": clean_note,
                },
                now,
            )
        return self.get(task_id) or {}

    def create(
        self,
        actor_id: str,
        title: str,
        dataset_version_id: str,
        product_version_id: str,
        store: str | None,
        listing: str | None,
        config_version_id: str | None = None,
        model_policy: dict[str, Any] | None = None,
        plan_hash: str | None = None,
        unresolved_policy: str | None = None,
        segment_order: list[str] | None = None,
        max_parallel_segments: int = 3,
    ) -> dict[str, Any]:
        policy = unresolved_policy or "block_all"
        if policy not in {"block_all", "run_ready"}:
            raise ValueError("未解决品类策略仅支持 block_all 或 run_ready")
        if not 1 <= max_parallel_segments <= SEGMENT_USER_LIMIT:
            raise ValueError("Listing 并行数必须在 1 到 3 之间")
        prepared = self.plan_service.prepare(
            dataset_version_id=dataset_version_id,
            product_version_id=product_version_id,
            store=store,
            listing=listing,
            config_version_id=config_version_id,
            model_policy=model_policy,
        )
        current_hash = str(prepared.response["plan_hash"])
        if plan_hash is not None and plan_hash != current_hash:
            raise TaskPlanConflict("执行计划已变化，请重新预检后再创建任务")
        missing_category_comments = int(
            prepared.response.get("missing_category_comment_count", 0)
        )
        if missing_category_comments:
            raise ValueError(
                "所选数据中有 "
                f"{missing_category_comments} 条有效评论对应商品缺少品类A或品类B，"
                "请先补齐商品目录后再创建任务"
            )
        returns = prepared.returns
        products = prepared.products
        config = prepared.config
        clean_store = str(prepared.response["inputs"]["scope"]["store"])
        clean_listing = prepared.response["inputs"]["scope"]["listing"]
        keys_by_segment = prepared.execution_plan.classification_keys_by_segment(
            prepared.dataset
        )
        planned_segments = list(prepared.response["segments"])
        has_blocked = int(prepared.response["blocked_count"]) > 0
        block_all = policy == "block_all" and has_blocked
        if not planned_segments:
            initial_status = "completed"
            initial_stage = "分析完成"
            initial_message = "本次数据均为不分析记录，未创建 Listing 执行片段"
        else:
            initial_status = "blocked" if block_all else "queued"
            initial_stage = "等待品类处理" if block_all else "等待运行"
            initial_message = (
                "存在未解决品类，等待补充或调整处理策略"
                if block_all
                else "任务已进入 Listing 队列"
            )
        ordered_segment_keys = self._validated_segment_order(
            planned_segments,
            segment_order,
        )
        order_by_key = {
            segment_key: position
            for position, segment_key in enumerate(ordered_segment_keys, start=1)
        }
        with self.database.transaction(immediate=True) as connection:
            task_id = new_id("task")
            now = utc_now()
            snapshot = {
                "returns": self._dataset_version_snapshot(returns),
                "products": self._dataset_version_snapshot(products),
                "config": self._model_config_snapshot(config, model_policy),
                "scope": prepared.response["inputs"]["scope"],
                "execution_plan": self._execution_plan_snapshot(
                    prepared.response,
                    current_hash,
                    policy,
                    ordered_segment_keys,
                ),
            }
            connection.execute(
                """
                INSERT INTO tasks(
                    id, title, owner_id, dataset_version_id,
                    product_version_id, config_version_id, store, listing,
                    status, stage, message, snapshot_json,
                    max_parallel_segments, created_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    title.strip()
                    or f"{'自动识别' if clean_store == 'AUTO' else clean_store} 退货语义分析",
                    actor_id,
                    dataset_version_id,
                    product_version_id,
                    config["id"],
                    clean_store,
                    clean_listing,
                    initial_status,
                    initial_stage,
                    initial_message,
                    json_text(snapshot),
                    max_parallel_segments,
                    now,
                    now if initial_status == "completed" else None,
                ),
            )
            for segment in sorted(
                planned_segments,
                key=lambda value: order_by_key[str(value["segment_key"])],
            ):
                segment_key = str(segment["segment_key"])
                self._insert_segment(
                    connection,
                    task_id=task_id,
                    segment=segment,
                    segment_key=segment_key,
                    classification_keys=keys_by_segment[segment_key],
                    record_count=int(segment["record_count"]),
                    unique_comments=int(segment["unique_comments"]),
                    variants=segment["variants"],
                    execution_order=order_by_key[segment_key],
                    unresolved_policy=policy,
                    has_blocked=has_blocked,
                    created_at=now,
                )
            connection.execute(
                """
                INSERT INTO task_events(
                    task_id, event_type, stage, message, actor_id, created_at
                ) VALUES (?, 'created', ?, ?, ?, ?)
                """,
                (task_id, initial_stage, initial_message, actor_id, now),
            )
        add_audit(
            self.database,
            "task",
            task_id,
            "create",
            actor_id,
            after=snapshot,
        )
        return self.get(task_id) or {}

    @staticmethod
    def _dataset_version_snapshot(version: dict[str, Any]) -> dict[str, Any]:
        return {
            "dataset_id": version["dataset_id"],
            "version_id": version["id"],
            "version": version["version"],
            "name": version["dataset_name"],
            "sha256": version["sha256"],
        }

    @staticmethod
    def _model_config_snapshot(
        config: dict[str, Any],
        model_policy: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return {
            "version_id": config["id"],
            "version": config["version"],
            "connection_id": config["connection_id"],
            "connection": config["connection_name"],
            "strategy_source": "task" if model_policy else "connection",
            "primary_model": config["primary_model"],
            "primary_effort": config["primary_effort"],
            "cheap_model": config["cheap_model"],
            "cheap_effort": config["cheap_effort"],
            "cheap_audit_percent": config["cheap_audit_percent"],
            "secondary_model": config["secondary_model"],
            "secondary_effort": config["secondary_effort"],
        }

    @staticmethod
    def _execution_plan_snapshot(
        response: dict[str, Any],
        plan_hash: str,
        unresolved_policy: str,
        segment_order: list[str],
    ) -> dict[str, Any]:
        summary = {
            key: value
            for key, value in response.items()
            if key
            not in {
                "inputs",
                "plan_hash",
                "registry_version",
                "unresolved_product_count",
                "unresolved_products",
                "category_options",
            }
        }
        return {
            "registry_version": response["registry_version"],
            "plan_hash": plan_hash,
            "unresolved_policy": unresolved_policy,
            "segment_order": segment_order,
            "summary": summary,
        }

    @staticmethod
    def _snapshot_model_policy(task: dict[str, Any]) -> dict[str, Any] | None:
        config = task.get("snapshot", {}).get("config", {})
        if config.get("strategy_source") != "task":
            return None
        connection_id = config.get("connection_id")
        primary_model = config.get("primary_model")
        if not connection_id or not primary_model:
            return None
        return {
            "connection_id": connection_id,
            "cheap_model": config.get("cheap_model"),
            "cheap_effort": config.get("cheap_effort") or "low",
            "primary_model": primary_model,
            "primary_effort": config.get("primary_effort") or "medium",
            "secondary_model": config.get("secondary_model"),
            "secondary_effort": config.get("secondary_effort") or "high",
            "cheap_audit_percent": config.get("cheap_audit_percent", 5),
        }

    def list(
        self,
        status: str | None = None,
        owner_id: str | None = None,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT t.*, u.display_name AS owner_name,
                   rd.name AS dataset_name, rv.version AS dataset_version,
                   pd.name AS product_name, pv.version AS product_version,
                   c.name AS connection_name, cv.version AS config_version,
                   cv.primary_model,
                   CASE WHEN t.status = 'queued' THEN (
                       SELECT COUNT(*) + 1 FROM tasks q
                       WHERE q.status = 'queued' AND q.created_at < t.created_at
                   ) END AS queue_position
            FROM tasks t
            JOIN users u ON u.id = t.owner_id
            JOIN dataset_versions rv ON rv.id = t.dataset_version_id
            JOIN datasets rd ON rd.id = rv.dataset_id
            JOIN dataset_versions pv ON pv.id = t.product_version_id
            JOIN datasets pd ON pd.id = pv.dataset_id
            JOIN api_config_versions cv ON cv.id = t.config_version_id
            JOIN api_connections c ON c.id = cv.connection_id
            WHERE 1 = 1
        """
        params: list[object] = []
        if status:
            query += " AND t.status = ?"
            params.append(status)
        if owner_id:
            query += " AND t.owner_id = ?"
            params.append(owner_id)
        query += " ORDER BY t.created_at DESC"
        with self.database.connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [self._serialize(dict(row)) for row in rows]

    def get(self, task_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT t.*, u.display_name AS owner_name,
                       rd.name AS dataset_name, rv.version AS dataset_version,
                       pd.name AS product_name, pv.version AS product_version,
                       c.name AS connection_name, cv.version AS config_version,
                       cv.primary_model, cv.primary_effort,
                       cv.cheap_model, cv.secondary_model,
                       CASE WHEN t.status = 'queued' THEN (
                           SELECT COUNT(*) + 1 FROM tasks q
                           WHERE q.status = 'queued'
                             AND q.created_at < t.created_at
                       ) END AS queue_position
                FROM tasks t
                JOIN users u ON u.id = t.owner_id
                JOIN dataset_versions rv ON rv.id = t.dataset_version_id
                JOIN datasets rd ON rd.id = rv.dataset_id
                JOIN dataset_versions pv ON pv.id = t.product_version_id
                JOIN datasets pd ON pd.id = pv.dataset_id
                JOIN api_config_versions cv ON cv.id = t.config_version_id
                JOIN api_connections c ON c.id = cv.connection_id
                WHERE t.id = ?
                """,
                (task_id,),
            ).fetchone()
            segment_rows = connection.execute(
                """
                SELECT * FROM task_segments
                WHERE task_id = ?
                ORDER BY execution_order, segment_key
                """,
                (task_id,),
            ).fetchall()
            owner_running = 0
            task_running = 0
            waiting_positions: dict[str, int] = {}
            if row is not None:
                owner_running_row = connection.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM task_segments s
                    JOIN tasks t ON t.id = s.task_id
                    WHERE t.owner_id = ? AND s.status = 'running'
                    """,
                    (row["owner_id"],),
                ).fetchone()
                owner_running = int(owner_running_row["count"])
                task_running_row = connection.execute(
                    """
                    SELECT COUNT(*) AS count FROM task_segments
                    WHERE task_id = ? AND status = 'running'
                    """,
                    (task_id,),
                ).fetchone()
                task_running = int(task_running_row["count"])
                waiting_rows = connection.execute(
                    """
                    SELECT s.id
                    FROM task_segments s
                    JOIN tasks t ON t.id = s.task_id
                    WHERE t.owner_id = ?
                      AND s.status IN ('queued', 'retry_pending')
                    ORDER BY
                      (SELECT COUNT(*) FROM task_segments active
                       WHERE active.task_id = t.id AND active.status = 'running'),
                      COALESCE(t.last_scheduled_at, t.created_at),
                      s.execution_order, s.created_at
                    """,
                    (row["owner_id"],),
                ).fetchall()
                waiting_positions = {
                    str(value["id"]): position
                    for position, value in enumerate(waiting_rows, start=1)
                }
        if row is None:
            return None
        item = self._serialize(dict(row))
        item["segments"] = [
            self._serialize_segment(dict(value)) for value in segment_rows
        ]
        max_parallel = int(item.get("max_parallel_segments", 3))
        for segment in item["segments"]:
            status = str(segment["status"])
            if status not in WAITING_SEGMENT_STATUSES:
                if status == "paused":
                    if int(segment.get("model_failures") or 0) >= 3 and segment.get(
                        "error"
                    ):
                        segment["wait_reason"] = "模型服务异常，任务已暂停"
                    else:
                        segment["wait_reason"] = "已由用户暂停"
                continue
            if item.get("pause_requested"):
                reason = "批量任务已暂停"
            elif task_running >= max_parallel:
                reason = f"本批量并发已满：{task_running}/{max_parallel}"
            elif owner_running >= SEGMENT_USER_LIMIT:
                reason = f"个人运行槽位已满：{owner_running}/{SEGMENT_USER_LIMIT}"
            else:
                reason = f"我的队列第 {waiting_positions.get(str(segment['id']), 1)} 位"
            segment["wait_reason"] = reason
        item["running_segments"] = task_running
        item["owner_running_segments"] = owner_running
        item["owner_segment_limit"] = SEGMENT_USER_LIMIT
        return item

    def events(self, task_id: str, after_id: int = 0) -> list[dict[str, Any]]:
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

    def cancel(
        self,
        task_id: str,
        actor_id: str,
        note: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        clean_note = note.strip()
        if not clean_note:
            raise ValueError("请填写取消原因")
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute(
                "SELECT status, stage, revision FROM tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
            if row is None:
                raise ValueError("任务不存在")
            if int(row["revision"]) != expected_revision:
                raise TaskRevisionConflict("任务已被他人修改，请刷新后重试")
            if row["status"] in FINAL_STATUSES:
                raise ValueError("任务已经结束")
            now = utc_now()
            connection.execute(
                """
                UPDATE task_segments
                SET status = 'cancelled', requested_action = NULL,
                    completed_at = ?, revision = revision + 1
                WHERE task_id = ?
                  AND status IN ('queued', 'retry_pending', 'paused',
                                 'failed', 'not_started')
                """,
                (now, task_id),
            )
            running_count = connection.execute(
                """
                UPDATE task_segments
                SET requested_action = 'cancel', revision = revision + 1
                WHERE task_id = ? AND status = 'running'
                """,
                (task_id,),
            ).rowcount
            status = "running" if running_count else "cancelled"
            stage = "正在取消" if running_count else "已取消"
            completed_at = None if running_count else now
            connection.execute(
                """
                UPDATE tasks
                SET cancel_requested = 1, pause_requested = 0,
                    status = ?, stage = ?, message = '正在取消未完成 Listing',
                    completed_at = COALESCE(?, completed_at), revision = revision + 1
                WHERE id = ?
                """,
                (status, stage, completed_at, task_id),
            )
            connection.execute(
                """
                INSERT INTO task_events(
                    task_id, event_type, stage, message, actor_id,
                    data_json, created_at
                ) VALUES (?, 'cancel', ?, '用户请求取消任务', ?, ?, ?)
                """,
                (
                    task_id,
                    stage,
                    actor_id,
                    json_text(
                        {
                            "before": {
                                "status": row["status"],
                                "stage": row["stage"],
                            },
                            "after": {"status": status, "stage": stage},
                            "note": clean_note,
                        }
                    ),
                    now,
                ),
            )
        add_audit(
            self.database,
            "task",
            task_id,
            "cancel",
            actor_id,
            before={"status": row["status"], "stage": row["stage"]},
            after={"status": status, "stage": stage, "note": clean_note},
        )
        return self.get(task_id) or {}

    def pause(
        self,
        task_id: str,
        actor_id: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            task = connection.execute(
                "SELECT status, stage, revision FROM tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
            if task is None:
                raise ValueError("任务不存在")
            if int(task["revision"]) != expected_revision:
                raise TaskRevisionConflict("任务已被他人修改，请刷新后重试")
            if task["status"] not in {"queued", "running"}:
                raise ValueError("当前任务不能暂停")
            connection.execute(
                """
                UPDATE task_segments
                SET status = 'paused', requested_action = NULL,
                    revision = revision + 1
                WHERE task_id = ? AND status IN ('queued', 'retry_pending')
                """,
                (task_id,),
            )
            running_count = connection.execute(
                """
                UPDATE task_segments
                SET requested_action = 'pause', revision = revision + 1
                WHERE task_id = ? AND status = 'running'
                """,
                (task_id,),
            ).rowcount
            status = "running" if running_count else "paused"
            stage = "正在暂停" if running_count else "已暂停"
            connection.execute(
                """
                UPDATE tasks
                SET pause_requested = 1, status = ?, stage = ?,
                    message = '等待运行中的 Listing 保存检查点',
                    revision = revision + 1, heartbeat_at = ?
                WHERE id = ? AND revision = ?
                """,
                (status, stage, now, task_id, expected_revision),
            )
            event_data = {
                "before": {"status": task["status"], "stage": task["stage"]},
                "after": {"status": status, "stage": stage},
            }
            connection.execute(
                """
                INSERT INTO task_events(
                    task_id, event_type, stage, message, actor_id,
                    data_json, created_at
                ) VALUES (?, 'pause', ?, '用户暂停全部未完成 Listing', ?, ?, ?)
                """,
                (task_id, stage, actor_id, json_text(event_data), now),
            )
            self._insert_audit(
                connection,
                task_id,
                "pause",
                actor_id,
                event_data["before"],
                event_data["after"],
                now,
            )
        return self.get(task_id) or {}

    def resume(
        self,
        task_id: str,
        actor_id: str,
        expected_revision: int,
        note: str,
    ) -> dict[str, Any]:
        clean_note = note.strip()
        if not clean_note:
            raise ValueError("请填写继续执行原因")
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            task = connection.execute(
                "SELECT status, stage, revision FROM tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
            if task is None:
                raise ValueError("任务不存在")
            if int(task["revision"]) != expected_revision:
                raise TaskRevisionConflict("任务已被他人修改，请刷新后重试")
            if task["status"] not in {"paused", "cancelled"}:
                raise ValueError("仅已暂停或已取消任务可以继续执行")
            source_status = str(task["status"])
            resumable = connection.execute(
                """
                SELECT COUNT(*) AS count FROM task_segments
                WHERE task_id = ?
                  AND status IN (
                      'cancelled', 'not_started', 'running',
                      'queued', 'retry_pending', 'paused'
                  )
                """,
                (task_id,),
            ).fetchone()
            if resumable is None or int(resumable["count"]) == 0:
                raise ValueError("当前任务没有未完成片段")
            connection.execute(
                """
                UPDATE task_segments
                SET status = CASE
                        WHEN status IN ('cancelled', 'running') THEN 'retry_pending'
                        ELSE 'queued'
                    END,
                    progress_current = CASE
                        WHEN status IN ('cancelled', 'running') THEN 0
                        ELSE progress_current
                    END,
                    error = NULL, requested_action = NULL,
                    started_at = NULL, completed_at = NULL,
                    revision = revision + 1
                WHERE task_id = ?
                  AND status IN (
                      'cancelled', 'not_started', 'running',
                      'queued', 'retry_pending', 'paused'
                  )
                """,
                (task_id,),
            )
            connection.execute(
                """
                UPDATE tasks
                SET status = 'queued', stage = '等待继续执行',
                    message = '未完成片段已重新排队', error = NULL,
                    cancel_requested = 0, pause_requested = 0, completed_at = NULL,
                    revision = revision + 1, heartbeat_at = ?
                WHERE id = ? AND revision = ?
                """,
                (now, task_id, expected_revision),
            )
            event_data = {
                "before": {"status": source_status, "stage": task["stage"]},
                "after": {"status": "queued", "stage": "等待继续执行"},
                "note": clean_note,
            }
            connection.execute(
                """
                INSERT INTO task_events(
                    task_id, event_type, stage, message, actor_id,
                    data_json, created_at
                ) VALUES (?, 'resumed', '等待继续执行',
                          '用户继续执行未完成片段', ?, ?, ?)
                """,
                (task_id, actor_id, json_text(event_data), now),
            )
            self._insert_audit(
                connection,
                task_id,
                "resume",
                actor_id,
                event_data["before"],
                event_data["after"] | {"note": clean_note},
                now,
            )
        return self.get(task_id) or {}

    def retry(self, task_id: str, actor_id: str) -> dict[str, Any]:
        source = self.get(task_id)
        if source is None:
            raise ValueError("任务不存在")
        if source["status"] == "partial":
            raise ValueError("部分完成任务请使用片段重试或重新规划")
        if source["status"] not in FINAL_STATUSES:
            raise ValueError("任务结束后才能再次运行")
        suffix = "（重试）" if source["status"] != "completed" else "（再次运行）"
        result = self.create(
            actor_id=actor_id,
            title=f"{source['title']}{suffix}"[:120],
            dataset_version_id=str(source["dataset_version_id"]),
            product_version_id=str(source["product_version_id"]),
            config_version_id=str(source["config_version_id"]),
            store=str(source["store"]),
            listing=source["listing"],
            unresolved_policy=(
                source["snapshot"]
                .get("execution_plan", {})
                .get("unresolved_policy", "block_all")
            ),
            segment_order=(
                [str(segment["segment_key"]) for segment in source["segments"]]
                if source["segments"]
                else None
            ),
            max_parallel_segments=int(source.get("max_parallel_segments", 3)),
        )
        add_audit(
            self.database,
            "task",
            task_id,
            "retry",
            actor_id,
            after={"new_task_id": result["id"]},
        )
        return result

    def rename(
        self,
        task_id: str,
        title: str,
        note: str,
        expected_revision: int,
        actor_id: str,
    ) -> dict[str, Any]:
        clean_title = title.strip()
        if not clean_title:
            raise ValueError("任务名称不能为空")
        clean_note = note.strip()
        if not clean_note:
            raise ValueError("请填写修改原因")
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute(
                "SELECT title, revision, stage FROM tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
            if row is None:
                raise ValueError("任务不存在")
            if int(row["revision"]) != expected_revision:
                raise TaskRevisionConflict("任务已被其他用户修改，请刷新后重试")
            before = {"title": str(row["title"]), "revision": expected_revision}
            new_revision = expected_revision + 1
            now = utc_now()
            connection.execute(
                """
                UPDATE tasks SET title = ?, revision = ? WHERE id = ?
                """,
                (clean_title, new_revision, task_id),
            )
            connection.execute(
                """
                INSERT INTO task_events(
                    task_id, event_type, stage, message, actor_id,
                    data_json, created_at
                ) VALUES (?, 'updated', ?, '任务名称已修改', ?, ?, ?)
                """,
                (
                    task_id,
                    row["stage"],
                    actor_id,
                    json_text(
                        {
                            "before": before,
                            "after": {
                                "title": clean_title,
                                "revision": new_revision,
                            },
                            "note": clean_note,
                        }
                    ),
                    now,
                ),
            )
        add_audit(
            self.database,
            "task",
            task_id,
            "rename",
            actor_id,
            before=before,
            after={
                "title": clean_title,
                "revision": new_revision,
                "note": clean_note,
            },
        )
        return self.get(task_id) or {}

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

    @staticmethod
    def _status_text(status: str) -> tuple[str, str]:
        values = {
            "queued": ("等待运行", "任务执行计划已更新并进入队列"),
            "running": ("语义分析", "Listing 片段正在运行"),
            "paused": ("已暂停", "未完成 Listing 已暂停"),
            "completed": ("分析完成", "全部任务片段已经完成"),
            "partial": ("部分完成", "已有可交付结果，仍有片段待处理"),
            "blocked": ("等待品类处理", "当前没有可执行的任务片段"),
            "cancelled": ("已取消", "未完成 Listing 已取消"),
            "failed": ("运行失败", "Listing 片段运行失败"),
        }
        return values[status]

    @staticmethod
    def _segment_status(
        segment: dict[str, Any],
        unresolved_policy: str,
        has_blocked: bool,
    ) -> str:
        if segment["status"] == "blocked":
            return "blocked"
        if unresolved_policy == "block_all" and has_blocked:
            return "not_started"
        return "queued"

    @classmethod
    def _insert_segment(
        cls,
        connection: Any,
        *,
        task_id: str,
        segment: dict[str, Any],
        segment_key: str,
        classification_keys: list[str],
        record_count: int,
        unique_comments: int,
        variants: list[dict[str, Any]],
        execution_order: int,
        unresolved_policy: str,
        has_blocked: bool,
        created_at: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO task_segments(
                id, task_id, segment_key, agent_key, agent_family,
                logic_version, taxonomy_version, model_policy_version,
                model_policy_json, claims_version, scope_json, status,
                record_count, unique_comments, progress_total,
                variants_json, classification_keys_json, execution_order,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id("segment"),
                task_id,
                segment_key,
                segment["agent_key"],
                segment["agent_family"],
                segment["logic_version"],
                segment["taxonomy_version"],
                segment["model_policy_version"],
                json_text(segment["model_policy"]),
                segment["claims_version"],
                json_text(segment.get("scope", {})),
                cls._segment_status(
                    segment,
                    unresolved_policy,
                    has_blocked,
                ),
                record_count,
                unique_comments,
                unique_comments,
                json_text(variants),
                json_text(classification_keys),
                execution_order,
                created_at,
            ),
        )

    @staticmethod
    def _variants_for_keys(
        dataset: ReturnDataset,
        classification_keys: list[str],
    ) -> list[dict[str, Any]]:
        selected = dataset.unique_comments.loc[
            dataset.unique_comments["classification_key"].isin(classification_keys)
        ]
        variants = []
        for (category_a, category_b), rows in selected.groupby(
            ["category_a", "category_b"],
            sort=True,
            dropna=False,
        ):
            variants.append(
                {
                    "category_a": str(category_a),
                    "category_b": str(category_b),
                    "record_count": int(rows["record_count"].sum()),
                    "unique_comments": len(rows),
                }
            )
        return variants

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
        connection.execute(
            """
            INSERT INTO audit_logs(
                id, entity_type, entity_id, action, before_json,
                after_json, actor_id, created_at
            ) VALUES (?, 'task', ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id("audit"),
                task_id,
                action,
                json_text(before),
                json_text(after),
                actor_id,
                created_at,
            ),
        )

    @staticmethod
    def _validated_segment_order(
        segments: list[dict[str, Any]],
        requested_order: list[str] | None,
    ) -> list[str]:
        planned_keys = [str(segment["segment_key"]) for segment in segments]
        if requested_order is None:
            return planned_keys
        if len(requested_order) != len(set(requested_order)) or set(
            requested_order
        ) != set(planned_keys):
            raise TaskPlanConflict("片段执行顺序与最新执行计划不一致，请重新预检")
        return requested_order

    @staticmethod
    def _serialize(item: dict[str, Any]) -> dict[str, Any]:
        item["snapshot"] = json_value(item.pop("snapshot_json", None), {})
        item["metrics"] = json_value(item.pop("metrics_json", None), {})
        item["cancel_requested"] = bool(item.get("cancel_requested"))
        item["pause_requested"] = bool(item.get("pause_requested"))
        return item

    @staticmethod
    def _serialize_segment(item: dict[str, Any]) -> dict[str, Any]:
        item["variants"] = json_value(item.pop("variants_json", None), [])
        item["scope"] = json_value(item.pop("scope_json", None), {})
        item["model_policy"] = json_value(
            item.pop("model_policy_json", None),
            None,
        )
        item.pop("classification_keys_json", None)
        requested_action = item.get("requested_action")
        item["display_status"] = (
            f"{requested_action}_pending"
            if item.get("status") == "running" and requested_action
            else item.get("status")
        )
        return item
