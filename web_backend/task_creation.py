from __future__ import annotations

from collections.abc import Callable
from typing import Any

from return_semantics.data import ReturnDataset
from web_backend.common import add_audit, json_text, new_id
from web_backend.database import Database
from web_backend.security import utc_now
from web_backend.task_contracts import SEGMENT_USER_LIMIT, TaskPlanConflict
from web_backend.task_plan_service import TaskPlanService


class TaskCreationMixin:
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
                standard_version_id, model_policy_json, claims_version,
                scope_json, status,
                record_count, unique_comments, progress_total,
                variants_json, classification_keys_json, execution_order,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                segment.get("standard_version_id"),
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
