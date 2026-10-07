from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from return_semantics.data import ReturnDataset
from web_backend.common import add_audit, json_text, new_id
from web_backend.database import Database
from web_backend.security import utc_now
from web_backend.task_contracts import TaskPlanConflict
from web_backend.task_plan_service import TaskPlanService
from web_backend.tasks.creation_plan import (
    initial_creation_state,
    validate_creation_options,
    validate_creation_plan,
)
from web_backend.tasks.snapshots import TaskSnapshotsMixin


@dataclass(frozen=True, kw_only=True)
class _SegmentInsertContext:
    task_id: str
    unresolved_policy: str
    has_blocked: bool
    created_at: str


class TaskCreationMixin(TaskSnapshotsMixin):
    database: Database
    plan_service: TaskPlanService
    get: Callable[..., dict[str, Any] | None]
    _segment_status: Callable[..., str]

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
        validate_creation_options(policy, max_parallel_segments)
        prepared = self.plan_service.prepare(
            dataset_version_id=dataset_version_id,
            product_version_id=product_version_id,
            store=store,
            listing=listing,
            config_version_id=config_version_id,
            model_policy=model_policy,
        )
        current_hash = validate_creation_plan(prepared.response, plan_hash)
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
        initial_status, initial_stage, initial_message = initial_creation_state(
            planned_segments, block_all
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
                "analysis_context": prepared.response["inputs"]["analysis_context"],
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
                    title.strip() or f"{returns['dataset_name']} · 分析任务",
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
            insert_context = _SegmentInsertContext(
                task_id=task_id,
                unresolved_policy=policy,
                has_blocked=has_blocked,
                created_at=now,
            )
            for segment in sorted(
                planned_segments,
                key=lambda value: order_by_key[str(value["segment_key"])],
            ):
                segment_key = str(segment["segment_key"])
                self._insert_segment(
                    connection,
                    segment={
                        **segment,
                        "segment_key": segment_key,
                        "record_count": int(segment["record_count"]),
                        "unique_comments": int(segment["unique_comments"]),
                    },
                    classification_keys=keys_by_segment[segment_key],
                    execution_order=order_by_key[segment_key],
                    context=insert_context,
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

    @classmethod
    def _insert_segment(
        cls,
        connection: Any,
        *,
        segment: dict[str, Any],
        classification_keys: list[str],
        execution_order: int,
        context: _SegmentInsertContext,
    ) -> None:
        connection.execute(
            """
            INSERT INTO task_segments(
                id, task_id, segment_key, agent_key, agent_family,
                logic_version, taxonomy_version, model_policy_version,
                standard_version_id, model_policy_json, claims_version,
                scope_json, status,
                record_count, unique_comments, progress_total,
                variants_json, classification_keys_json, execution_order,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id("segment"),
                context.task_id,
                segment["segment_key"],
                segment["agent_key"],
                segment["agent_family"],
                segment["logic_version"],
                segment["taxonomy_version"],
                segment["model_policy_version"],
                segment.get("standard_version_id"),
                json_text(segment["model_policy"]),
                segment["claims_version"],
                json_text(segment.get("scope", {})),
                cls._segment_status(
                    segment,
                    context.unresolved_policy,
                    context.has_blocked,
                ),
                segment["record_count"],
                segment["unique_comments"],
                segment["unique_comments"],
                json_text(segment["variants"]),
                json_text(classification_keys),
                execution_order,
                context.created_at,
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
