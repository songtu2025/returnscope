from __future__ import annotations

import threading
from typing import Any, Callable

from return_semantics.analysis_context import analysis_context_from_snapshot
from return_semantics.data import ReturnDataset
from return_semantics.exporter import REVIEW_STATUSES
from return_semantics.label_statistics import top_problem_labels
from web_backend.common import json_text, json_value
from web_backend.database import Database
from web_backend.dataset_cache import load_cached_dataset
from web_backend.security import utc_now
from web_backend.settings import Settings
from web_backend.task_execution.parent_refresh_state import (
    _parent_refresh_state,
    _ParentRefreshState,
)


class ParentResultMixin:
    database: Database
    settings: Settings
    _build_parent_result: Callable[..., None]
    _load_segments: Callable[..., list[dict[str, Any]]]
    _task_locks: dict[str, threading.Lock]
    _task_locks_lock: threading.Lock

    def _get_task_lock(self, task_id: str) -> threading.Lock:
        with self._task_locks_lock:
            return self._task_locks.setdefault(task_id, threading.Lock())

    def finalize_task(self, task_id: str) -> None:
        with self._get_task_lock(task_id):
            task = self._load_task(task_id)
            if task is None or task["status"] not in {
                "completed",
                "partial",
                "cancelled",
            }:
                return
            dataset = self._load_parent_dataset(task)
            try:
                self._build_parent_result(task_id, dataset, str(task["status"]))
            except Exception as exc:
                self._record_parent_result_error(
                    task_id,
                    str(exc),
                    str(task["status"]),
                )

    def _refresh_parent(
        self,
        task_id: str,
        dataset: ReturnDataset | None = None,
    ) -> None:
        with self._get_task_lock(task_id):
            task = self._load_task(task_id)
            if task is None:
                return
            state = _parent_refresh_state(
                task, self._load_segments(task_id), self._parent_status_text
            )
            if state.terminal and state.has_deliverable:
                if dataset is None:
                    dataset = self._load_parent_dataset(task)
                try:
                    self._build_parent_result(task_id, dataset, state.status)
                except Exception as exc:
                    self._record_parent_result_error(task_id, str(exc), state.status)
                    return
            self._persist_parent_refresh(task_id, task, state)

    def _record_parent_result_error(
        self,
        task_id: str,
        error: str,
        parent_status: str,
    ) -> None:
        now = utc_now()
        clean_error = error[:500]
        safe_status = "cancelled" if parent_status == "cancelled" else "partial"
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                UPDATE tasks
                SET status = ?, stage = '结果汇总异常',
                    message = 'Listing 已完成，但批量结果生成失败；单项结果仍可下载',
                    error = ?, completed_at = ?, heartbeat_at = ?,
                    revision = revision + 1
                WHERE id = ?
                """,
                (safe_status, clean_error, now, now, task_id),
            )
            connection.execute(
                """
                INSERT INTO task_events(
                    task_id, event_type, stage, message, data_json, created_at
                ) VALUES (?, 'result_merge_failed', '结果汇总异常',
                          '批量结果生成失败，已保留 Listing 结果', ?, ?)
                """,
                (task_id, json_text({"error": clean_error}), now),
            )

    def _load_task(self, task_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT t.*, rv.file_path AS return_file_path,
                       pv.file_path AS product_file_path,
                       rv.sha256 AS return_sha256, pv.sha256 AS product_sha256
                FROM tasks t
                JOIN dataset_versions rv ON rv.id = t.dataset_version_id
                JOIN dataset_versions pv ON pv.id = t.product_version_id
                WHERE t.id = ?
                """,
                (task_id,),
            ).fetchone()
        return dict(row) if row else None

    _top_problem_labels = staticmethod(top_problem_labels)

    @staticmethod
    def _public_segment(segment: dict[str, Any]) -> dict[str, Any]:
        output = dict(segment)
        output["variants"] = json_value(output.pop("variants_json"), [])
        output["model_policy"] = json_value(
            output.pop("model_policy_json", None),
            None,
        )
        output["scope"] = json_value(output.pop("scope_json", None), {})
        output.pop("classification_keys_json", None)
        return output

    @staticmethod
    def _parent_status_text(
        status: str,
        review_count: int,
    ) -> tuple[str, str]:
        if status == "completed":
            if review_count:
                return "分析完成", f"分析完成，{review_count} 条结果需要人工复核"
            return "分析完成", "分析完成，无需人工复核"
        if status == "partial":
            return "部分完成", "已有可交付结果，仍有片段待处理"
        if status == "blocked":
            return "等待处理", "当前没有可执行片段，请处理失败或未知品类"
        if status == "running":
            return "语义分析", "Listing 片段正在运行"
        if status == "paused":
            return "已暂停", "未完成 Listing 已暂停"
        if status == "cancelled":
            return "已取消", "未完成 Listing 已取消，已完成结果继续保留"
        if status == "failed":
            return "运行失败", "Listing 片段运行失败，可单独重试"
        return "等待运行", "任务仍有片段等待执行"

    @staticmethod
    def _review_count(results: dict[str, dict[str, Any]]) -> int:
        return sum(
            1 for value in results.values() if value["status"] in REVIEW_STATUSES
        )

    @staticmethod
    def _load_parent_dataset(task: dict[str, Any]) -> ReturnDataset:
        snapshot = json_value(task.get("snapshot_json"), {})
        dataset = load_cached_dataset(
            str(task["return_file_path"]),
            str(task["product_file_path"]),
            str(task["store"]),
            task["listing"],
            str(snapshot.get("scope", {}).get("mode", "manual")),
            str(task["return_sha256"]),
            str(task["product_sha256"]),
            analysis_context_from_snapshot(snapshot),
        )
        return dataset

    def _persist_parent_refresh(
        self, task_id: str, task: dict[str, Any], state: _ParentRefreshState
    ) -> None:
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            before_status = str(task["status"])
            connection.execute(
                """
                    UPDATE tasks
                    SET status = ?, stage = ?, message = ?,
                        progress_current = ?, progress_total = ?,
                        progress_percent = ?,
                        error = ?,
                        completed_at = CASE WHEN ? THEN ? ELSE NULL END,
                        heartbeat_at = ?, revision = revision + 1
                    WHERE id = ?
                    """,
                (
                    state.status,
                    state.stage,
                    state.message,
                    state.current,
                    state.total,
                    state.percent,
                    state.error,
                    state.terminal,
                    now,
                    now,
                    task_id,
                ),
            )
            if before_status != state.status:
                connection.execute(
                    """
                        INSERT INTO task_events(
                            task_id, event_type, stage, message,
                            data_json, created_at
                        ) VALUES (?, 'status_changed', ?, ?, ?, ?)
                        """,
                    (
                        task_id,
                        state.stage,
                        state.message,
                        json_text(
                            {
                                "before": {"status": before_status},
                                "after": {"status": state.status},
                            }
                        ),
                        now,
                    ),
                )
