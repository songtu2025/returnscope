from __future__ import annotations

import threading
from collections import Counter
from typing import Any, Callable

from return_semantics.data import ReturnDataset
from return_semantics.exporter import REVIEW_STATUSES
from return_semantics.schemas import TaxonomyConfig, ValidatedClassification
from web_backend.common import json_text, json_value
from web_backend.database import Database
from web_backend.dataset_cache import load_cached_dataset
from web_backend.security import utc_now
from web_backend.settings import Settings
from web_backend.task_state import summarize_task_status


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
            snapshot = json_value(task.get("snapshot_json"), {})
            dataset = load_cached_dataset(
                str(task["return_file_path"]),
                str(task["product_file_path"]),
                str(task["store"]),
                task["listing"],
                str(snapshot.get("scope", {}).get("mode", "manual")),
                str(task["return_sha256"]),
                str(task["product_sha256"]),
            )
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
            segments = self._load_segments(task_id)
            executable = [
                segment for segment in segments if segment["agent_key"] != "unknown"
            ]
            statuses = [str(segment["status"]) for segment in executable]
            has_running = "running" in statuses
            if task["cancel_requested"] and not has_running:
                parent_status = "cancelled"
            elif task["pause_requested"] and not has_running:
                parent_status = "paused"
            else:
                parent_status = summarize_task_status(statuses)
            degraded_segment = next(
                (
                    segment
                    for segment in executable
                    if int(segment.get("model_failures") or 0) >= 5
                    and segment.get("error")
                ),
                None,
            )
            if degraded_segment is not None and task["pause_requested"]:
                stage = "模型服务异常"
                message = (
                    "模型服务连续失败，正在保存其他运行中 Listing 的检查点"
                    if has_running
                    else "模型服务连续失败，任务已自动暂停；请检查连接后继续执行"
                )
                parent_error = str(degraded_segment["error"])
            else:
                stage, message = self._parent_status_text(parent_status, 0)
                parent_error = None
            current = sum(int(segment["progress_current"]) for segment in executable)
            total = sum(int(segment["progress_total"]) for segment in executable)
            percent = round(current / total * 100, 2) if total else 0
            terminal = parent_status in {
                "completed",
                "partial",
                "cancelled",
                "failed",
                "blocked",
            }
            has_deliverable = any(
                segment["status"] in {"completed", "completed_with_errors"}
                for segment in executable
            )
            if terminal and has_deliverable:
                if dataset is None:
                    snapshot = json_value(task.get("snapshot_json"), {})
                    dataset = load_cached_dataset(
                        str(task["return_file_path"]),
                        str(task["product_file_path"]),
                        str(task["store"]),
                        task["listing"],
                        str(snapshot.get("scope", {}).get("mode", "manual")),
                        str(task["return_sha256"]),
                        str(task["product_sha256"]),
                    )
                try:
                    self._build_parent_result(task_id, dataset, parent_status)
                except Exception as exc:
                    self._record_parent_result_error(
                        task_id,
                        str(exc),
                        parent_status,
                    )
                    return
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
                        parent_status,
                        stage,
                        message,
                        current,
                        total,
                        percent,
                        parent_error,
                        terminal,
                        now,
                        now,
                        task_id,
                    ),
                )
                if before_status != parent_status:
                    connection.execute(
                        """
                        INSERT INTO task_events(
                            task_id, event_type, stage, message,
                            data_json, created_at
                        ) VALUES (?, 'status_changed', ?, ?, ?, ?)
                        """,
                        (
                            task_id,
                            stage,
                            message,
                            json_text(
                                {
                                    "before": {"status": before_status},
                                    "after": {"status": parent_status},
                                }
                            ),
                            now,
                        ),
                    )

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

    @staticmethod
    def _top_problem_labels(
        dataset: ReturnDataset,
        results: dict[str, ValidatedClassification],
        taxonomy: TaxonomyConfig,
    ) -> list[dict[str, Any]]:
        labels = {label.code: label for label in taxonomy.labels}
        record_counts = dataset.records["classification_key"].value_counts()
        counts: Counter[str] = Counter()
        for key, result in results.items():
            weight = int(record_counts.get(key, 0))
            counts.update({code: weight for code in result.problem_label_codes})
        denominator = max(int(dataset.records["has_text_evidence"].sum()), 1)
        return [
            {
                "code": code,
                "name": labels[code].name,
                "group": labels[code].group,
                "count": count,
                "share": round(count / denominator * 100, 2),
            }
            for code, count in counts.most_common(8)
            if code in labels
        ]

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
