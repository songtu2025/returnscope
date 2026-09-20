from __future__ import annotations

import logging
import threading
import time
from collections import Counter
from dataclasses import is_dataclass, replace
from pathlib import Path
from typing import Any, Callable, cast

import pandas as pd

from return_semantics.analysis_context import analysis_context_from_snapshot
from return_semantics.capabilities import load_capability_registry
from return_semantics.category_pipeline import CategorySegmentRuntime
from return_semantics.claims import NO_CLAIMS_VERSION, ClaimsResolver
from return_semantics.data import ReturnDataset
from return_semantics.exporter import export_results
from return_semantics.model_client import (
    JsonlCache,
    RequestRateLimiter,
    Sub2APIClient,
    Sub2APISettings,
)
from return_semantics.pipeline import (
    ModelServiceUnavailable,
    PipelineCancelled,
    PipelineRun,
    classify_comments,
)
from return_semantics.schemas import TaxonomyConfig, ValidatedClassification
from web_backend.agent_runner_parent_result import ParentResultMixin
from web_backend.agent_runner_result_publication import (
    IncompleteResultCheckpoint as IncompleteResultCheckpoint,
)
from web_backend.agent_runner_result_publication import ResultPublicationMixin
from web_backend.agent_runner_segment_execution import (
    SegmentExecutionMixin,
)
from web_backend.agent_runner_segment_execution import (
    _SegmentRunContext as _SegmentRunContext,
)
from web_backend.agent_runner_segment_outcomes import SegmentOutcomesMixin
from web_backend.classification_result_service import (
    ClassificationResultService,
    ResultPublicationError,
)
from web_backend.classification_standard_service import ClassificationStandardService
from web_backend.common import json_text, json_value
from web_backend.config_service import ConfigService
from web_backend.database import Database
from web_backend.security import utc_now
from web_backend.settings import PROJECT_ROOT, Settings

performance_logger = logging.getLogger("uvicorn.error.performance")


class AgentRunner(
    SegmentExecutionMixin,
    SegmentOutcomesMixin,
    ResultPublicationMixin,
    ParentResultMixin,
):
    def __init__(
        self,
        database: Database,
        settings: Settings,
        config_service: ConfigService,
        result_service: ClassificationResultService | None = None,
        standard_service: ClassificationStandardService | None = None,
    ) -> None:
        self.database = database
        self.settings = settings
        self.config_service = config_service
        self.result_service = result_service or ClassificationResultService(database)
        self.standard_service = standard_service or ClassificationStandardService(
            database
        )
        self.capability_registry = (
            self.standard_service.active_registry()
            if self.standard_service._tables_exist()
            else load_capability_registry(
                PROJECT_ROOT / "config" / "category_capabilities.json"
            )
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

    def _get_cache(self, config_version_id: str) -> JsonlCache:
        with self._caches_lock:
            cache = self._caches.get(config_version_id)
            if cache is None:
                cache = JsonlCache(
                    self.settings.data_dir / "cache" / f"{config_version_id}.jsonl"
                )
                self._caches[config_version_id] = cache
            return cache

    def run_segment(self, task_id: str, segment_id: str) -> None:
        started = time.perf_counter()
        outcome = "completed"
        task = self._load_task(task_id)
        segment = self._load_segment(segment_id)
        if task is None or segment is None or segment["status"] != "running":
            performance_logger.info(
                "segment_performance task_id=%s segment_id=%s outcome=skipped "
                "total_ms=%.2f",
                task_id,
                segment_id,
                (time.perf_counter() - started) * 1000,
            )
            return
        context = self._segment_run_context(task_id, segment_id, task, segment)
        try:
            self._execute_segment(context)
        except PipelineCancelled:
            outcome = "interrupted"
            self._finish_interrupted_segment(
                task_id,
                segment_id,
                context.existing_results,
                context.latest_run,
                context.checkpoint_path,
                *context.runtime_totals(),
            )
        except ModelServiceUnavailable as exc:
            outcome = "model_service_paused"
            self._finish_model_service_paused(
                task_id,
                segment_id,
                str(exc),
                context.existing_results,
                context.latest_run,
                context.checkpoint_path,
                *context.runtime_totals(),
            )
        except ResultPublicationError as exc:
            outcome = "result_publish_failed"
            self._finish_result_publish_failed_segment(
                task_id,
                segment_id,
                str(exc),
                context.latest_run,
                context.checkpoint_path,
                context.existing_results,
                *context.runtime_totals(),
            )
        except Exception as exc:
            outcome = "failed"
            self._finish_failed_segment(
                task_id,
                segment_id,
                str(exc),
                context.latest_run,
                context.checkpoint_path,
                context.existing_results,
                *context.runtime_totals(),
            )
        finally:
            performance_logger.info(
                "segment_performance task_id=%s segment_id=%s outcome=%s total_ms=%.2f",
                task_id,
                segment_id,
                outcome,
                (time.perf_counter() - started) * 1000,
            )

    def _classify_segment(
        self,
        context: _SegmentRunContext,
        selected: pd.DataFrame,
        taxonomy: TaxonomyConfig,
        runtime: CategorySegmentRuntime,
        total: int,
    ) -> PipelineRun:
        completed_base = len(context.existing_results)

        def progress(current: int, _total: int) -> None:
            completed = completed_base + current
            if completed == total or completed == 1 or completed % 5 == 0:
                self._update_segment_progress(
                    context.task_id,
                    context.segment_id,
                    completed,
                    total,
                )

        def checkpoint(run: PipelineRun) -> None:
            self._save_segment_checkpoint(context, run)

        def model_degraded(
            run: PipelineRun,
            consecutive_failures: int,
            error: str,
        ) -> None:
            self._save_segment_checkpoint(context, run)
            if consecutive_failures == 3:
                self._record_model_degraded(
                    context.task_id,
                    context.segment_id,
                    error,
                    consecutive_failures,
                )

        if selected.empty:
            return PipelineRun(
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
        task = context.task
        snapshot = json_value(task.get("snapshot_json"), {})
        return classify_comments(
            unique_comments=selected,
            taxonomy=taxonomy,
            claims=runtime.claims,
            client=runtime.client,
            cache=self._get_cache(f"{task['id']}-{task['config_version_id']}"),
            secondary_model=runtime.secondary_model,
            model_policy_version=str(runtime.model_policy["version"]),
            secondary_is_fallback=bool(
                runtime.model_policy["actual"].get("review")
                and runtime.model_policy["actual"]["review"].get("fallback_from")
                == "secondary"
            ),
            progress=progress,
            should_cancel=lambda: self._segment_should_stop(
                context.task_id,
                context.segment_id,
            ),
            checkpoint=checkpoint,
            on_model_degraded=model_degraded,
            analysis_context=analysis_context_from_snapshot(snapshot),
        )

    def _export_legacy_segment_result(
        self,
        context: _SegmentRunContext,
        output_path: Path,
        dataset: ReturnDataset,
        results: dict[str, ValidatedClassification],
        taxonomy: TaxonomyConfig,
    ) -> None:
        try:
            export_results(
                output_path=output_path,
                dataset=dataset,
                results=results,
                taxonomy=taxonomy,
            )
            self.result_service.attach_legacy_file(
                context.segment_id,
                str(output_path),
            )
        except Exception as exc:
            self.result_service.record_legacy_export_error(
                context.task_id,
                context.segment_id,
                str(exc),
            )

    def classify_taxonomy_sample(
        self,
        *,
        taxonomy: TaxonomyConfig,
        samples: list[dict[str, Any]],
        source: dict[str, Any],
        progress: Callable[[int, int], None] | None = None,
    ) -> PipelineRun:
        unique_comments = pd.DataFrame(
            [
                {
                    "classification_key": str(item["classification_key"]),
                    "comment_normalized": str(item["comment"]),
                    "reason": item.get("reason"),
                    "category_a": str(item.get("category_a") or ""),
                    "category_b": str(item.get("category_b") or ""),
                }
                for item in samples
            ]
        )
        if source.get("kind") in {"raw_dataset", "review_file"}:
            config_version_id = str(source["config_version_id"])
            settings = self.config_service.build_model_settings(config_version_id)
            model_policy = source.get("model_policy")
            if model_policy is not None:
                settings = self._settings_for_model_policy(settings, model_policy)
            claims = self.claims_resolver.resolve(
                str(source.get("store") or ""),
                source.get("listing"),
                str(source["standard_key"]),
                expected_version=NO_CLAIMS_VERSION,
            )
            client = Sub2APIClient(
                settings,
                rate_limiter=self._get_rate_limiter(
                    config_version_id,
                    settings.requests_per_minute,
                ),
            )
            return classify_comments(
                unique_comments=unique_comments,
                taxonomy=taxonomy,
                claims=claims,
                client=client,
                cache=self._get_cache("classification-standard-validation"),
                secondary_model=(
                    str(model_policy["actual"]["review"]["model"])
                    if model_policy and model_policy["actual"].get("review")
                    else settings.secondary_model
                ),
                progress=progress,
                model_policy_version=str(source["model_policy_version"]),
                secondary_is_fallback=bool(
                    model_policy
                    and model_policy["actual"].get("review")
                    and model_policy["actual"]["review"].get("fallback_from")
                    == "secondary"
                ),
                analysis_context=source.get("analysis_context", "returns"),
            )
        task = source["task"]
        segment = source["segment"]
        snapshot = json_value(task.get("snapshot_json"), {})
        base_settings = self._snapshot_model_settings(task, snapshot)
        runtime = self._build_segment_runtime(
            segment,
            base_settings,
            str(task["config_version_id"]),
            str(task["store"]),
            task.get("listing"),
        )
        review = runtime.model_policy["actual"].get("review")
        return classify_comments(
            unique_comments=unique_comments,
            taxonomy=taxonomy,
            claims=runtime.claims,
            client=runtime.client,
            cache=self._get_cache("classification-standard-validation"),
            secondary_model=runtime.secondary_model,
            progress=progress,
            model_policy_version=str(runtime.model_policy["version"]),
            secondary_is_fallback=bool(
                review and review.get("fallback_from") == "secondary"
            ),
            analysis_context=analysis_context_from_snapshot(snapshot),
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
                str(key) for key in json_value(segment["classification_keys_json"], [])
            }
            if not segment_keys.issubset(segment_results):
                raise ValueError(f"已完成 Listing {segment['segment_key']} 结果不完整")
            completed_keys.update(segment_keys)
            results.update(
                {
                    key: value
                    for key, value in segment_results.items()
                    if key in segment_keys
                }
            )
        partial_dataset = self._subset_dataset(dataset, completed_keys)
        standard_version_ids = [
            str(segment.get("standard_version_id") or "")
            for segment in completed_segments
        ]
        snapshot_registry = (
            self.standard_service.registry_for_versions(standard_version_ids)
            if standard_version_ids and all(standard_version_ids)
            else self.capability_registry
        )
        taxonomy = snapshot_registry.combined_taxonomy()
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
            "model_calls": sum(
                int(segment["model_calls"]) for segment in persisted_segments
            ),
            "cache_hits": sum(
                int(segment["cache_hits"]) for segment in persisted_segments
            ),
            "category_registry_version": snapshot.get("execution_plan", {}).get(
                "registry_version",
                snapshot_registry.version,
            ),
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
        capability = self._capability_for_segment(segment)

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
                        "role": ("cheap" if base_settings.cheap_model else "primary"),
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
        review = actual.get("review")
        segment_settings = self._settings_for_model_policy(
            base_settings,
            model_policy,
        )
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

    @staticmethod
    def _settings_for_model_policy(
        base_settings: Any,
        model_policy: dict[str, Any],
    ) -> Any:
        if not is_dataclass(base_settings):
            return base_settings
        settings = cast(Sub2APISettings, base_settings)
        actual = model_policy["actual"]
        primary = actual["primary"]
        first_pass = actual["first_pass"]
        review = actual.get("review")
        return replace(
            settings,
            model=str(primary["model"]),
            reasoning_effort=str(primary["effort"]),
            cheap_model=(
                str(first_pass["model"]) if first_pass["role"] == "cheap" else None
            ),
            cheap_reasoning_effort=str(first_pass["effort"]),
            secondary_model=(str(review["model"]) if review else None),
            secondary_reasoning_effort=(
                str(review["effort"]) if review else str(primary["effort"])
            ),
        )
