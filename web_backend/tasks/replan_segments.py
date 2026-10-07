from __future__ import annotations

from collections.abc import Callable
from typing import Any

from web_backend.common import json_value
from web_backend.task_contracts import TaskPlanConflict, _ReplanSegmentSyncContext
from web_backend.task_creation import _SegmentInsertContext


class TaskReplanSegmentsMixin:
    """保留已完成片段，并按原计划顺序替换剩余范围。"""

    _insert_segment: Callable[..., None]
    _variants_for_keys: Callable[..., list[dict[str, Any]]]

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
        self._insert_replanned_segments(connection, task_id, context)

    def _insert_replanned_segments(
        self,
        connection: Any,
        task_id: str,
        context: _ReplanSegmentSyncContext,
    ) -> None:
        preserved_keys_by_segment = {
            segment_key: set(json_value(segment["classification_keys_json"], []))
            for segment_key, segment in context.preserved.items()
        }
        has_blocked = int(context.prepared.response["blocked_count"]) > 0
        next_execution_order = max(
            (int(value["execution_order"]) for value in context.preserved.values()),
            default=0,
        )
        insert_context = _SegmentInsertContext(
            task_id=task_id,
            unresolved_policy=context.unresolved_policy,
            has_blocked=has_blocked,
            created_at=context.now,
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
                segment=self._remaining_replan_segment(
                    segment,
                    segment_key=segment_key,
                    remaining_keys=remaining_keys,
                    context=context,
                ),
                classification_keys=remaining_keys,
                execution_order=next_execution_order,
                context=insert_context,
            )

    def _remaining_replan_segment(
        self,
        segment: dict[str, Any],
        *,
        segment_key: str,
        remaining_keys: list[str],
        context: _ReplanSegmentSyncContext,
    ) -> dict[str, Any]:
        return {
            **segment,
            "segment_key": segment_key,
            "record_count": int(
                sum(context.record_counts.get(key, 0) for key in remaining_keys)
            ),
            "unique_comments": len(remaining_keys),
            "variants": self._variants_for_keys(
                context.prepared.dataset,
                remaining_keys,
            ),
        }
