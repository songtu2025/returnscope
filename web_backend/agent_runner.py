from __future__ import annotations

import json
import threading
from collections import Counter
from dataclasses import is_dataclass, replace
from functools import lru_cache
from pathlib import Path
from typing import Any

from return_semantics.capabilities import load_capability_registry
from return_semantics.category_pipeline import CategorySegmentRuntime
from return_semantics.claims import NO_CLAIMS_VERSION, ClaimsResolver
from return_semantics.data import (
    ReturnDataset,
    load_return_dataset,
    load_return_dataset_auto,
)
from return_semantics.exporter import REVIEW_STATUSES, export_results
from return_semantics.model_client import (
    JsonlCache,
    RequestRateLimiter,
    Sub2APIClient,
)
from return_semantics.pipeline import (
    ModelServiceUnavailable,
    PipelineCancelled,
    PipelineRun,
    classify_comments,
)
from return_semantics.schemas import (
    ProcessingStatus,
    TaxonomyConfig,
    ValidatedClassification,
)
from web_backend.classification_result_service import (
    ClassificationResultService,
    ResultPublicationError,
)
from web_backend.common import json_text, json_value
from web_backend.config_service import ConfigService
from web_backend.database import Database
from web_backend.security import utc_now
from web_backend.settings import PROJECT_ROOT, Settings
from web_backend.task_state import summarize_task_status


class IncompleteResultCheckpoint(ValueError):
    pass


class AgentRunner:
    def __init__(
        self,
        database: Database,
        settings: Settings,
        config_service: ConfigService,
        result_service: ClassificationResultService | None = None,
    ) -> None:
        self.database = database
        self.settings = settings
        self.config_service = config_service
        self.result_service = result_service or ClassificationResultService(database)
        self.capability_registry = load_capability_registry(
            PROJECT_ROOT / "config" / "category_capabilities.json"
        )
        self.claims_resolver = ClaimsResolver(
            PROJECT_ROOT / "config" / "listing_claims_registry.json"
        )
        self._rate_limiters: dict[str, RequestRateLimiter] = {}
        self._rate_limiters_lock = threading.Lock()
        self._caches: dict[str, JsonlCache] = {}
        self._caches_lock = threading.Lock()
        self._task_locks: dict[str, threading.Lock] = {}
        self._task_locks_lock = threading.Lock()

    @staticmethod
    @lru_cache(maxsize=8)
    def _cached_dataset(
        return_file_path: str,
        product_file_path: str,
        store: str,
        listing: str | None,
        scope_mode: str,
    ) -> ReturnDataset:
        if scope_mode == "auto":
            return load_return_dataset_auto(
                Path(return_file_path),
                Path(product_file_path),
            )
        return load_return_dataset(
            Path(return_file_path),
            Path(product_file_path),
            store=store,
            listing=listing,
        )

    def _get_cache(self, config_version_id: str) -> JsonlCache:
        with self._caches_lock:
            return self._caches.setdefault(
                config_version_id,
                JsonlCache(
                    self.settings.data_dir / "cache" / f"{config_version_id}.jsonl"
                ),
            )

    def _get_task_lock(self, task_id: str) -> threading.Lock:
        with self._task_locks_lock:
            return self._task_locks.setdefault(task_id, threading.Lock())

    def run_segment(self, task_id: str, segment_id: str) -> None:
        task = self._load_task(task_id)
        segment = self._load_segment(segment_id)
        if task is None or segment is None or segment["status"] != "running":
            return
        segment_dir = self.settings.data_dir / "results" / task_id / "segments"
        segment_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_path = Path(
            segment["result_json_path"]
            or segment_dir / f"{segment_id}-classifications.json"
        )
        existing_results = {
            key: value
            for key, value in self._load_checkpoint(checkpoint_path).items()
            if value.status != ProcessingStatus.MODEL_ERROR
        }
        base_model_calls = int(segment.get("model_calls") or 0)
        base_cache_hits = int(segment.get("cache_hits") or 0)
        base_model_failures = int(segment.get("model_failures") or 0)
        latest_run: PipelineRun | None = None

        def runtime_totals(run: PipelineRun | None) -> tuple[int, int, int]:
            return (
                base_model_calls + (run.model_calls if run else 0),
                base_cache_hits + (run.cache_hits if run else 0),
                base_model_failures + (run.model_failures if run else 0),
            )
        try:
            snapshot = json_value(task.get("snapshot_json"), {})
            scope_mode = str(snapshot.get("scope", {}).get("mode", "manual"))
            dataset = self._cached_dataset(
                str(task["return_file_path"]),
                str(task["product_file_path"]),
                str(task["store"]),
                task["listing"],
                scope_mode,
            )
            all_keys = {
                str(key)
                for key in json_value(segment["classification_keys_json"], [])
            }
            existing_results = {
                key: value for key, value in existing_results.items() if key in all_keys
            }
            remaining_keys = all_keys - set(existing_results)
            selected = dataset.unique_comments.loc[
                dataset.unique_comments["classification_key"].astype(str).isin(
                    remaining_keys
                )
            ].reset_index(drop=True)

            capability = next(
                (
                    item
                    for item in self.capability_registry.capabilities
                    if item.key == str(segment["agent_key"])
                ),
                None,
            )
            if capability is None:
                raise ValueError(f"品类能力不存在: {segment['agent_key']}")
            taxonomy = self.capability_registry.load_taxonomy(capability)
            base_settings = self._snapshot_model_settings(task, snapshot)
            runtime = self._build_segment_runtime(
                segment,
                base_settings,
                str(task["config_version_id"]),
                str(task["store"]),
                task["listing"],
            )
            completed_base = len(existing_results)
            total = len(all_keys)

            def progress(current: int, _total: int) -> None:
                completed = completed_base + current
                if completed == total or completed == 1 or completed % 5 == 0:
                    self._update_segment_progress(
                        task_id,
                        segment_id,
                        completed,
                        total,
                    )

            def checkpoint(run: PipelineRun) -> None:
                nonlocal latest_run
                latest_run = run
                combined = {**existing_results, **run.classifications}
                self._write_checkpoint(checkpoint_path, combined)
                self._update_segment_runtime_metrics(
                    segment_id,
                    *runtime_totals(run),
                )

            def model_degraded(
                run: PipelineRun,
                consecutive_failures: int,
                error: str,
            ) -> None:
                nonlocal latest_run
                latest_run = run
                combined = {**existing_results, **run.classifications}
                self._write_checkpoint(checkpoint_path, combined)
                self._update_segment_runtime_metrics(
                    segment_id,
                    *runtime_totals(run),
                )
                if consecutive_failures == 3:
                    self._record_model_degraded(
                        task_id,
                        segment_id,
                        error,
                        consecutive_failures,
                    )

            if selected.empty:
                run = PipelineRun(
                    classifications={},
                    usage={},
                    usage_by_model={},
                    cache_hits=0,
                    cache_hits_by_model={},
                    model_calls=0,
                    model_calls_by_model={},
                    request_metrics={},
                    routing={},
                )
            else:
                run = classify_comments(
                    unique_comments=selected,
                    taxonomy=taxonomy,
                    claims=runtime.claims,
                    client=runtime.client,
                    cache=self._get_cache(
                        f"{task['id']}-{task['config_version_id']}"
                    ),
                    secondary_model=runtime.secondary_model,
                    model_policy_version=str(runtime.model_policy["version"]),
                    secondary_is_fallback=bool(
                        runtime.model_policy["actual"].get("review")
                        and runtime.model_policy["actual"]["review"].get(
                            "fallback_from"
                        )
                        == "secondary"
                    ),
                    progress=progress,
                    should_cancel=lambda: self._segment_should_stop(
                        task_id,
                        segment_id,
                    ),
                    checkpoint=checkpoint,
                    on_model_degraded=model_degraded,
                )
            latest_run = run
            results = {**existing_results, **run.classifications}
            if set(results) != all_keys:
                missing_count = len(all_keys - set(results))
                raise ValueError(f"Listing 片段仍缺少 {missing_count} 组分类结果")
            self._write_checkpoint(checkpoint_path, results)
            segment_dataset = self._subset_dataset(dataset, all_keys)
            result_version = int(segment["result_version"] or 0) + 1
            output_path = segment_dir / f"{segment_id}-analysis-v{result_version}.xlsx"
            has_errors = self._results_have_quality_errors(results)
            model_calls, cache_hits, model_failures = runtime_totals(run)
            self._complete_segment(
                task_id=task_id,
                segment_id=segment_id,
                status="completed_with_errors" if has_errors else "completed",
                progress_total=total,
                model_calls=model_calls,
                cache_hits=cache_hits,
                model_failures=model_failures,
                checkpoint_path=checkpoint_path,
                result_version=result_version,
                dataset=segment_dataset,
                results=results,
                taxonomy=taxonomy,
            )
            try:
                export_results(
                    output_path=output_path,
                    dataset=segment_dataset,
                    results=results,
                    taxonomy=taxonomy,
                )
                self.result_service.attach_legacy_file(
                    segment_id,
                    str(output_path),
                )
            except Exception as exc:
                self.result_service.record_legacy_export_error(
                    task_id,
                    segment_id,
                    str(exc),
                )
            self._refresh_parent(task_id, dataset)
        except PipelineCancelled:
            model_calls, cache_hits, model_failures = runtime_totals(latest_run)
            self._finish_interrupted_segment(
                task_id,
                segment_id,
                existing_results,
                latest_run,
                checkpoint_path,
                model_calls,
                cache_hits,
                model_failures,
            )
        except ModelServiceUnavailable as exc:
            model_calls, cache_hits, model_failures = runtime_totals(latest_run)
            self._finish_model_service_paused(
                task_id,
                segment_id,
                str(exc),
                existing_results,
                latest_run,
                checkpoint_path,
                model_calls,
                cache_hits,
                model_failures,
            )
        except ResultPublicationError as exc:
            model_calls, cache_hits, model_failures = runtime_totals(latest_run)
            self._finish_result_publish_failed_segment(
                task_id,
                segment_id,
                str(exc),
                latest_run,
                checkpoint_path,
                existing_results,
                model_calls,
                cache_hits,
                model_failures,
            )
        except Exception as exc:
            model_calls, cache_hits, model_failures = runtime_totals(latest_run)
            self._finish_failed_segment(
                task_id,
                segment_id,
                str(exc),
                latest_run,
                checkpoint_path,
                existing_results,
                model_calls,
                cache_hits,
                model_failures,
            )

    def retry_result_publish(
        self,
        task_id: str,
        segment_id: str,
    ) -> dict[str, Any]:
        try:
            task = self._load_task(task_id)
            segment = self._load_segment(segment_id)
            if task is None or segment is None:
                raise ValueError("任务或 Listing 片段不存在")
            if segment["result_publish_status"] != "publishing":
                raise ValueError("Listing 分类结果没有进入发布重试状态")
            prepared = self._prepare_completed_result(task, segment)
            return self.result_service.publish_v1(
                task_id=task_id,
                segment_id=segment_id,
                dataset=prepared["dataset"],
                results=prepared["results"],
                taxonomy=prepared["taxonomy"],
                segment_status=str(segment["status"]),
                progress_total=int(prepared["classification_key_count"]),
                model_calls=int(segment["model_calls"] or 0),
                cache_hits=int(segment["cache_hits"] or 0),
                checkpoint_path=str(prepared["checkpoint_path"]),
                legacy_result_version=int(segment["result_version"] or 0) + 1,
                model_failures=int(segment["model_failures"] or 0),
            )
        except ResultPublicationError as exc:
            current = self._load_segment(segment_id)
            if current and current["result_publish_status"] != "failed":
                self.result_service.mark_publish_failed(
                    task_id,
                    segment_id,
                    str(exc),
                )
            raise
        except Exception as exc:
            self.result_service.mark_publish_failed(task_id, segment_id, str(exc))
            raise ResultPublicationError(str(exc)) from exc

    def inspect_completed_result(
        self,
        task_id: str,
        segment_id: str,
    ) -> dict[str, Any]:
        task = self._load_task(task_id)
        segment = self._load_segment(segment_id)
        if task is None or segment is None:
            raise ValueError("任务或 Listing 片段不存在")
        prepared = self._prepare_completed_result(task, segment)
        return {
            "classification_key_count": prepared["classification_key_count"],
            "record_count": len(prepared["dataset"].records),
            "checkpoint_path": str(prepared["checkpoint_path"]),
            "taxonomy_version": prepared["taxonomy"].version,
        }

    def _prepare_completed_result(
        self,
        task: dict[str, Any],
        segment: dict[str, Any],
    ) -> dict[str, Any]:
        if segment["status"] not in {"completed", "completed_with_errors"}:
            raise ValueError("Listing 语义分类尚未完成")
        raw_keys = json_value(segment["classification_keys_json"], [])
        if not isinstance(raw_keys, list):
            raise IncompleteResultCheckpoint("Listing 片段分类键格式无效")
        all_keys = {str(key) for key in raw_keys}
        if not all_keys:
            raise IncompleteResultCheckpoint("Listing 片段没有分类键")
        checkpoint_path = Path(str(segment["result_json_path"] or ""))
        if not checkpoint_path.is_file():
            raise ValueError("没有可用的分类检查点")
        checkpoint = self._load_checkpoint(checkpoint_path)
        results = {key: value for key, value in checkpoint.items() if key in all_keys}
        if set(results) != all_keys:
            missing_count = len(all_keys - set(results))
            raise IncompleteResultCheckpoint(
                f"分类检查点缺少 {missing_count} 个分类键"
            )
        capability = next(
            (
                item
                for item in self.capability_registry.capabilities
                if item.key == str(segment["agent_key"])
            ),
            None,
        )
        if capability is None:
            raise ValueError(f"品类能力不存在: {segment['agent_key']}")
        taxonomy = self.capability_registry.load_taxonomy(capability)
        snapshot = json_value(task.get("snapshot_json"), {})
        dataset = self._cached_dataset(
            str(task["return_file_path"]),
            str(task["product_file_path"]),
            str(task["store"]),
            task["listing"],
            str(snapshot.get("scope", {}).get("mode", "manual")),
        )
        segment_dataset = self._subset_dataset(dataset, all_keys)
        dataset_keys = {
            str(value)
            for value in segment_dataset.unique_comments["classification_key"]
        }
        if dataset_keys != all_keys:
            missing_count = len(all_keys - dataset_keys)
            raise IncompleteResultCheckpoint(
                f"任务数据快照缺少 {missing_count} 个分类键"
            )
        return {
            "dataset": segment_dataset,
            "results": results,
            "taxonomy": taxonomy,
            "checkpoint_path": checkpoint_path,
            "classification_key_count": len(all_keys),
        }

    @staticmethod
    def _results_have_quality_errors(
        results: dict[str, ValidatedClassification],
    ) -> bool:
        if any(
            value.status == ProcessingStatus.MODEL_ERROR
            for value in results.values()
        ):
            return True
        has_semantics = any(
            value.semantic_units or value.unknown_semantics
            for value in results.values()
        )
        has_review_result = any(
            value.status.value in REVIEW_STATUSES
            for value in results.values()
        )
        return bool(results) and has_review_result and not has_semantics

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
            dataset = self._cached_dataset(
                str(task["return_file_path"]),
                str(task["product_file_path"]),
                str(task["store"]),
                task["listing"],
                str(snapshot.get("scope", {}).get("mode", "manual")),
            )
            try:
                self._build_parent_result(task_id, dataset, str(task["status"]))
            except Exception as exc:
                self._record_parent_result_error(
                    task_id,
                    str(exc),
                    str(task["status"]),
                )

    def _snapshot_model_settings(
        self,
        task: dict[str, Any],
        snapshot: dict[str, Any],
    ) -> Any:
        model_settings = self.config_service.build_model_settings(
            str(task["config_version_id"])
        )
        snapshot_config = snapshot.get("config", {})
        if snapshot_config.get("primary_model") and is_dataclass(model_settings):
            return replace(
                model_settings,
                model=str(snapshot_config["primary_model"]),
                reasoning_effort=str(
                    snapshot_config.get(
                        "primary_effort",
                        model_settings.reasoning_effort,
                    )
                ),
                cheap_model=snapshot_config.get("cheap_model"),
                cheap_reasoning_effort=str(
                    snapshot_config.get(
                        "cheap_effort",
                        model_settings.cheap_reasoning_effort,
                    )
                ),
                cheap_model_audit_percent=int(
                    snapshot_config.get(
                        "cheap_audit_percent",
                        model_settings.cheap_model_audit_percent,
                    )
                ),
                secondary_model=snapshot_config.get("secondary_model"),
                secondary_reasoning_effort=str(
                    snapshot_config.get(
                        "secondary_effort",
                        model_settings.secondary_reasoning_effort,
                    )
                ),
            )
        return model_settings

    def _load_segment(self, segment_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM task_segments WHERE id = ?",
                (segment_id,),
            ).fetchone()
        return dict(row) if row else None

    def _segment_should_stop(self, task_id: str, segment_id: str) -> bool:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT s.requested_action, t.cancel_requested, t.pause_requested
                FROM task_segments s
                JOIN tasks t ON t.id = s.task_id
                WHERE s.id = ? AND s.task_id = ?
                """,
                (segment_id, task_id),
            ).fetchone()
        return bool(
            row
            and (
                row["requested_action"]
                or row["cancel_requested"]
                or row["pause_requested"]
            )
        )

    def _update_segment_progress(
        self,
        task_id: str,
        segment_id: str,
        current: int,
        total: int,
    ) -> None:
        now = utc_now()
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE task_segments
                SET progress_current = ?, progress_total = ?, heartbeat_at = ?
                WHERE id = ? AND status = 'running'
                """,
                (current, total, now, segment_id),
            )
            totals = connection.execute(
                """
                SELECT COALESCE(SUM(progress_current), 0) AS current,
                       COALESCE(SUM(progress_total), 0) AS total
                FROM task_segments
                WHERE task_id = ? AND agent_key != 'unknown'
                """,
                (task_id,),
            ).fetchone()
            task_current = int(totals["current"])
            task_total = int(totals["total"])
            percent = round(task_current / task_total * 100, 2) if task_total else 0
            connection.execute(
                """
                UPDATE tasks
                SET progress_current = ?, progress_total = ?,
                    progress_percent = ?, heartbeat_at = ?
                WHERE id = ?
                """,
                (task_current, task_total, percent, now, task_id),
            )
            connection.execute(
                """
                INSERT INTO task_events(
                    task_id, event_type, stage, message,
                    progress_current, progress_total, data_json, created_at
                ) VALUES (?, 'segment_progress', '语义分析', ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    f"Listing 已完成 {current}/{total} 组评论",
                    task_current,
                    task_total,
                    json_text({"segment_id": segment_id}),
                    now,
                ),
            )

    def _update_segment_runtime_metrics(
        self,
        segment_id: str,
        model_calls: int,
        cache_hits: int,
        model_failures: int,
    ) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE task_segments
                SET model_calls = MAX(model_calls, ?),
                    cache_hits = MAX(cache_hits, ?),
                    model_failures = MAX(model_failures, ?)
                WHERE id = ? AND status = 'running'
                """,
                (model_calls, cache_hits, model_failures, segment_id),
            )

    def _record_model_degraded(
        self,
        task_id: str,
        segment_id: str,
        error: str,
        consecutive_failures: int,
    ) -> None:
        now = utc_now()
        message = (
            f"模型服务已连续失败 {consecutive_failures} 次，正在重试；"
            "达到 5 次将自动暂停"
        )
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                UPDATE task_segments
                SET error = ?, heartbeat_at = ?, revision = revision + 1
                WHERE id = ? AND task_id = ? AND status = 'running'
                """,
                (message, now, segment_id, task_id),
            )
            connection.execute(
                """
                UPDATE tasks
                SET stage = '模型服务异常', message = ?, heartbeat_at = ?,
                    revision = revision + 1
                WHERE id = ?
                """,
                (message, now, task_id),
            )
            connection.execute(
                """
                INSERT INTO task_events(
                    task_id, event_type, stage, message, data_json, created_at
                ) VALUES (?, 'model_service_degraded', '模型服务异常', ?, ?, ?)
                """,
                (
                    task_id,
                    message,
                    json_text(
                        {
                            "segment_id": segment_id,
                            "consecutive_failures": consecutive_failures,
                            "error": error[:500],
                        }
                    ),
                    now,
                ),
            )

    def _complete_segment(
        self,
        task_id: str,
        segment_id: str,
        status: str,
        progress_total: int,
        model_calls: int,
        cache_hits: int,
        checkpoint_path: Path,
        result_version: int,
        dataset: ReturnDataset,
        results: dict[str, ValidatedClassification],
        taxonomy: TaxonomyConfig,
        model_failures: int = 0,
    ) -> None:
        self.result_service.publish_v1(
            task_id=task_id,
            segment_id=segment_id,
            dataset=dataset,
            results=results,
            taxonomy=taxonomy,
            segment_status=status,
            progress_total=progress_total,
            model_calls=model_calls,
            cache_hits=cache_hits,
            model_failures=model_failures,
            checkpoint_path=str(checkpoint_path),
            legacy_result_version=result_version,
        )

    def _save_partial_checkpoint(
        self,
        checkpoint_path: Path,
        existing_results: dict[str, ValidatedClassification],
        latest_run: PipelineRun | None,
    ) -> dict[str, ValidatedClassification]:
        partial_results = {
            **existing_results,
            **(latest_run.classifications if latest_run else {}),
        }
        if partial_results:
            self._write_checkpoint(checkpoint_path, partial_results)
        return partial_results

    def _finish_interrupted_segment(
        self,
        task_id: str,
        segment_id: str,
        existing_results: dict[str, ValidatedClassification],
        latest_run: PipelineRun | None,
        checkpoint_path: Path,
        model_calls: int,
        cache_hits: int,
        model_failures: int,
    ) -> None:
        partial_results = self._save_partial_checkpoint(
            checkpoint_path,
            existing_results,
            latest_run,
        )
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute(
                """
                SELECT s.requested_action, t.cancel_requested, t.pause_requested
                FROM task_segments s
                JOIN tasks t ON t.id = s.task_id
                WHERE s.id = ? AND s.task_id = ?
                """,
                (segment_id, task_id),
            ).fetchone()
            requested = str(row["requested_action"] or "") if row else ""
            if requested == "cancel" or (row and row["cancel_requested"]):
                status = "cancelled"
                message = "Listing 已取消，完成片段不受影响"
            elif requested == "pause" or (row and row["pause_requested"]):
                status = "paused"
                message = "Listing 已保存检查点并暂停"
            else:
                status = "retry_pending"
                message = "Listing 已中断，等待从检查点恢复"
            connection.execute(
                """
                UPDATE task_segments
                SET status = ?, progress_current = ?,
                    model_calls = ?, cache_hits = ?, model_failures = ?,
                    requested_action = NULL, result_json_path = ?,
                    started_at = CASE WHEN ? = 'retry_pending' THEN NULL
                                      ELSE started_at END,
                    completed_at = CASE WHEN ? = 'cancelled' THEN ? ELSE NULL END,
                    heartbeat_at = ?, revision = revision + 1
                WHERE id = ? AND task_id = ?
                """,
                (
                    status,
                    len(partial_results),
                    model_calls,
                    cache_hits,
                    model_failures,
                    str(checkpoint_path),
                    status,
                    status,
                    now,
                    now,
                    segment_id,
                    task_id,
                ),
            )
            connection.execute(
                """
                INSERT INTO task_events(
                    task_id, event_type, stage, message, data_json, created_at
                ) VALUES (?, ?, '语义分析', ?, ?, ?)
                """,
                (
                    task_id,
                    f"segment_{status}",
                    message,
                    json_text({"segment_id": segment_id}),
                    now,
                ),
            )
        self._refresh_parent(task_id)

    def _finish_model_service_paused(
        self,
        task_id: str,
        segment_id: str,
        error: str,
        existing_results: dict[str, ValidatedClassification],
        latest_run: PipelineRun | None,
        checkpoint_path: Path,
        model_calls: int,
        cache_hits: int,
        model_failures: int,
    ) -> None:
        partial_results = self._save_partial_checkpoint(
            checkpoint_path,
            existing_results,
            latest_run,
        )
        now = utc_now()
        message = "模型服务连续失败，任务已自动暂停；请检查连接后继续执行"
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                UPDATE task_segments
                SET status = 'paused', progress_current = ?,
                    model_calls = ?, cache_hits = ?, model_failures = ?,
                    error = ?, requested_action = NULL, result_json_path = ?,
                    heartbeat_at = ?, revision = revision + 1
                WHERE id = ? AND task_id = ?
                """,
                (
                    len(partial_results),
                    model_calls,
                    cache_hits,
                    model_failures,
                    message,
                    str(checkpoint_path),
                    now,
                    segment_id,
                    task_id,
                ),
            )
            connection.execute(
                """
                UPDATE task_segments
                SET status = 'paused', requested_action = NULL,
                    revision = revision + 1
                WHERE task_id = ? AND id != ?
                  AND status IN ('queued', 'retry_pending')
                """,
                (task_id, segment_id),
            )
            connection.execute(
                """
                UPDATE task_segments
                SET requested_action = 'pause', revision = revision + 1
                WHERE task_id = ? AND id != ? AND status = 'running'
                """,
                (task_id, segment_id),
            )
            connection.execute(
                """
                UPDATE tasks
                SET pause_requested = 1, stage = '模型服务异常',
                    message = ?, error = ?, heartbeat_at = ?,
                    revision = revision + 1
                WHERE id = ?
                """,
                (message, error[:2000], now, task_id),
            )
            connection.execute(
                """
                INSERT INTO task_events(
                    task_id, event_type, stage, message, data_json, created_at
                ) VALUES (?, 'model_service_paused', '模型服务异常', ?, ?, ?)
                """,
                (
                    task_id,
                    message,
                    json_text(
                        {
                            "segment_id": segment_id,
                            "model_failures": model_failures,
                            "error": error[:500],
                        }
                    ),
                    now,
                ),
            )
        self._refresh_parent(task_id)

    def _finish_failed_segment(
        self,
        task_id: str,
        segment_id: str,
        error: str,
        latest_run: PipelineRun | None,
        checkpoint_path: Path,
        existing_results: dict[str, ValidatedClassification],
        model_calls: int,
        cache_hits: int,
        model_failures: int,
    ) -> None:
        partial_results = self._save_partial_checkpoint(
            checkpoint_path,
            existing_results,
            latest_run,
        )
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                UPDATE task_segments
                SET status = 'failed', progress_current = ?,
                    model_calls = ?, cache_hits = ?, model_failures = ?,
                    error = ?, requested_action = NULL, result_json_path = ?,
                    completed_at = ?, heartbeat_at = ?, revision = revision + 1
                WHERE id = ? AND task_id = ?
                """,
                (
                    len(partial_results),
                    model_calls,
                    cache_hits,
                    model_failures,
                    error[:2000],
                    str(checkpoint_path),
                    now,
                    now,
                    segment_id,
                    task_id,
                ),
            )
            connection.execute(
                """
                INSERT INTO task_events(
                    task_id, event_type, stage, message, data_json, created_at
                ) VALUES (?, 'segment_failed', '运行失败', ?, ?, ?)
                """,
                (
                    task_id,
                    error[:500],
                    json_text({"segment_id": segment_id}),
                    now,
                ),
            )
        self._refresh_parent(task_id)

    def _finish_result_publish_failed_segment(
        self,
        task_id: str,
        segment_id: str,
        error: str,
        latest_run: PipelineRun | None,
        checkpoint_path: Path,
        existing_results: dict[str, ValidatedClassification],
        model_calls: int,
        cache_hits: int,
        model_failures: int,
    ) -> None:
        results = self._save_partial_checkpoint(
            checkpoint_path,
            existing_results,
            latest_run,
        )
        status = (
            "completed_with_errors"
            if self._results_have_quality_errors(results)
            else "completed"
        )
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                UPDATE task_segments
                SET status = ?, progress_current = progress_total,
                    model_calls = ?, cache_hits = ?, model_failures = ?,
                    error = NULL, requested_action = NULL,
                    result_json_path = ?, result_publish_status = 'failed',
                    result_publish_error = COALESCE(result_publish_error, ?),
                    completed_at = ?, heartbeat_at = ?, revision = revision + 1
                WHERE id = ? AND task_id = ?
                """,
                (
                    status,
                    model_calls,
                    cache_hits,
                    model_failures,
                    str(checkpoint_path),
                    error[:500],
                    now,
                    now,
                    segment_id,
                    task_id,
                ),
            )
            connection.execute(
                """
                INSERT INTO task_events(
                    task_id, event_type, stage, message, data_json, created_at
                ) VALUES (?, 'segment_classified_publish_failed', '生成结果',
                          'Listing 语义分类已完成，但结果发布失败', ?, ?)
                """,
                (
                    task_id,
                    json_text({"segment_id": segment_id, "error": error[:500]}),
                    now,
                ),
            )
        self._refresh_parent(task_id)

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
                    dataset = self._cached_dataset(
                        str(task["return_file_path"]),
                        str(task["product_file_path"]),
                        str(task["store"]),
                        task["listing"],
                        str(snapshot.get("scope", {}).get("mode", "manual")),
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

    def _build_parent_result(
        self,
        task_id: str,
        dataset: ReturnDataset,
        parent_status: str,
    ) -> None:
        task = self._load_task(task_id)
        if task is None:
            return
        completed_segments = [
            segment
            for segment in self._load_segments(task_id)
            if segment["status"] in {"completed", "completed_with_errors"}
        ]
        results: dict[str, ValidatedClassification] = {}
        completed_keys: set[str] = set()
        for segment in completed_segments:
            path_text = segment.get("result_json_path")
            if not path_text:
                raise ValueError(
                    f"已完成 Listing {segment['segment_key']} 缺少结果检查点"
                )
            segment_results = self._load_checkpoint(Path(str(path_text)))
            segment_keys = {
                str(key)
                for key in json_value(segment["classification_keys_json"], [])
            }
            if not segment_keys.issubset(segment_results):
                raise ValueError(
                    f"已完成 Listing {segment['segment_key']} 结果不完整"
                )
            completed_keys.update(segment_keys)
            results.update(
                {key: value for key, value in segment_results.items() if key in segment_keys}
            )
        partial_dataset = self._subset_dataset(dataset, completed_keys)
        taxonomy = self.capability_registry.combined_taxonomy()
        result_dir = self.settings.data_dir / "results" / task_id
        result_dir.mkdir(parents=True, exist_ok=True)
        result_version = int(task["result_version"] or 0) + 1
        suffix = "analysis" if parent_status == "completed" else "analysis-partial"
        output_path = result_dir / f"{suffix}-v{result_version}.xlsx"
        results_path = result_dir / "classifications-v1.json"
        self._write_checkpoint(results_path, results)
        export_results(
            output_path=output_path,
            dataset=partial_dataset,
            results=results,
            taxonomy=taxonomy,
        )
        serialized = {
            key: value.model_dump(mode="json") for key, value in results.items()
        }
        review_count = self._review_count(serialized)
        persisted_segments = self._load_segments(task_id)
        statuses = Counter(value["status"] for value in serialized.values())
        snapshot = json_value(task.get("snapshot_json"), {})
        plan_summary = snapshot.get("execution_plan", {}).get("summary", {})
        metrics = {
            **json_value(task.get("metrics_json"), {}),
            "records": len(dataset.records),
            "valid_comments": int(dataset.records["has_text_evidence"].sum()),
            "unique_comments": len(dataset.unique_comments),
            "delivered_records": len(partial_dataset.records),
            "delivered_comments": len(partial_dataset.unique_comments),
            "partial_result": parent_status != "completed",
            "completed_segment_count": len(completed_segments),
            "excluded_comments": int(plan_summary.get("excluded_count", 0)),
            "excluded_records": int(plan_summary.get("excluded_record_count", 0)),
            "review_count": review_count,
            "statuses": dict(statuses),
            "model_calls": sum(int(segment["model_calls"]) for segment in persisted_segments),
            "cache_hits": sum(int(segment["cache_hits"]) for segment in persisted_segments),
            "category_registry_version": self.capability_registry.version,
            "category_segments": [
                self._public_segment(segment) for segment in persisted_segments
            ],
            "top_problem_labels": self._top_problem_labels(
                partial_dataset,
                results,
                taxonomy,
            ),
        }
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                UPDATE tasks
                SET metrics_json = ?, result_file_path = ?,
                    results_json_path = ?, result_version = ?, heartbeat_at = ?
                WHERE id = ?
                """,
                (
                    json_text(metrics),
                    str(output_path),
                    str(results_path),
                    result_version,
                    now,
                    task_id,
                ),
            )

    def _load_task(self, task_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT t.*, rv.file_path AS return_file_path,
                       pv.file_path AS product_file_path
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

    def _get_rate_limiter(
        self,
        config_version_id: str,
        requests_per_minute: int,
    ) -> RequestRateLimiter:
        with self._rate_limiters_lock:
            return self._rate_limiters.setdefault(
                config_version_id,
                RequestRateLimiter(requests_per_minute),
            )

    def _build_segment_runtime(
        self,
        segment: dict[str, Any],
        base_settings: Any,
        config_version_id: str,
        store: str,
        listing: str | None,
    ) -> CategorySegmentRuntime:
        agent_key = str(segment["agent_key"])
        capability = next(
            (
                item
                for item in self.capability_registry.capabilities
                if item.key == agent_key
            ),
            None,
        )
        if capability is None:
            raise ValueError(f"品类能力不存在: {agent_key}")

        model_policy = json_value(segment.get("model_policy_json"), None)
        if model_policy is None:
            model_policy = {
                "version": "legacy-model-policy-v1",
                "configured": {
                    "first_pass_role": (
                        "cheap" if base_settings.cheap_model else "primary"
                    ),
                    "review_role": (
                        "secondary" if base_settings.secondary_model else None
                    ),
                },
                "actual": {
                    "primary": {
                        "role": "primary",
                        "model": base_settings.model,
                        "effort": base_settings.reasoning_effort,
                    },
                    "first_pass": {
                        "role": (
                            "cheap" if base_settings.cheap_model else "primary"
                        ),
                        "model": base_settings.cheap_model or base_settings.model,
                        "effort": (
                            base_settings.cheap_reasoning_effort
                            if base_settings.cheap_model
                            else base_settings.reasoning_effort
                        ),
                    },
                    "review": (
                        {
                            "role": "secondary",
                            "model": base_settings.secondary_model,
                            "effort": base_settings.secondary_reasoning_effort,
                        }
                        if base_settings.secondary_model
                        else None
                    ),
                },
            }
        elif str(model_policy.get("version")) != capability.model_policy.version:
            raise ValueError(
                f"片段 {segment['segment_key']} 的模型策略版本已不可用，请重新规划"
            )

        actual = model_policy["actual"]
        primary = actual["primary"]
        first_pass = actual["first_pass"]
        review = actual.get("review")
        if is_dataclass(base_settings):
            segment_settings = replace(
                base_settings,
                model=str(primary["model"]),
                reasoning_effort=str(primary["effort"]),
                cheap_model=(
                    str(first_pass["model"])
                    if first_pass["role"] == "cheap"
                    else None
                ),
                cheap_reasoning_effort=str(first_pass["effort"]),
                secondary_model=(str(review["model"]) if review else None),
                secondary_reasoning_effort=(
                    str(review["effort"])
                    if review
                    else str(primary["effort"])
                ),
            )
        else:
            segment_settings = base_settings
        expected_claims_version = (
            str(segment["claims_version"])
            if segment.get("claims_version")
            else NO_CLAIMS_VERSION
        )
        scope = json_value(segment.get("scope_json"), {})
        claims = self.claims_resolver.resolve(
            str(scope.get("store") or store),
            scope.get("listing") or listing,
            agent_key,
            expected_version=expected_claims_version,
        )
        client = Sub2APIClient(
            segment_settings,
            rate_limiter=self._get_rate_limiter(
                config_version_id,
                segment_settings.requests_per_minute,
            ),
        )
        return CategorySegmentRuntime(
            client=client,
            claims=claims,
            secondary_model=(str(review["model"]) if review else None),
            model_policy=model_policy,
        )

    def _load_segments(self, task_id: str) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM task_segments
                WHERE task_id = ? ORDER BY execution_order, segment_key
                """,
                (task_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _load_checkpoint(
        path: Path,
    ) -> dict[str, ValidatedClassification]:
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return {
            str(key): ValidatedClassification.model_validate(value)
            for key, value in data.items()
        }

    @staticmethod
    def _write_checkpoint(
        path: Path,
        results: dict[str, ValidatedClassification],
    ) -> None:
        serialized = {
            key: value.model_dump(mode="json")
            for key, value in results.items()
        }
        temporary = path.with_suffix(f"{path.suffix}.tmp")
        temporary.write_text(
            json.dumps(serialized, ensure_ascii=False),
            encoding="utf-8",
        )
        temporary.replace(path)

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
    def _subset_dataset(
        dataset: ReturnDataset,
        classification_keys: set[str],
    ) -> ReturnDataset:
        records = dataset.records.loc[
            dataset.records["classification_key"].astype(str).isin(classification_keys)
        ].copy()
        unique_comments = dataset.unique_comments.loc[
            dataset.unique_comments["classification_key"]
            .astype(str)
            .isin(classification_keys)
        ].copy()
        scopes = []
        for (store, listing), group in records.groupby(
            ["store", "listing"],
            dropna=False,
        ):
            scopes.append(
                {
                    "store": str(store),
                    "listing": str(listing),
                    "record_count": len(group),
                    "unique_comments": int(group["classification_key"].nunique()),
                }
            )
        return ReturnDataset(
            records=records,
            unique_comments=unique_comments,
            mskus=frozenset(str(value) for value in records["sku"] if value),
            scopes=tuple(scopes),
            primary_store=dataset.primary_store,
            scope_mode=dataset.scope_mode,
        )
