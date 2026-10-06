from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from return_semantics.capabilities import (
    CapabilityRegistry,
)
from return_semantics.data import ReturnDataset
from return_semantics.exporter import export_results
from return_semantics.schemas import TaxonomyConfig, ValidatedClassification
from web_backend.classification_result_service import (
    ClassificationResultService,
)
from web_backend.classification_standard_service import ClassificationStandardService
from web_backend.common import json_text, json_value
from web_backend.database import Database
from web_backend.security import utc_now
from web_backend.settings import Settings
from web_backend.task_execution.contracts import (
    COMPLETED_SEGMENT_STATUSES,
    _SegmentRunContext,
)


@dataclass(frozen=True, kw_only=True)
class _ParentResultData:
    task_id: str
    segments: list[dict[str, Any]]
    results: dict[str, ValidatedClassification]
    dataset: ReturnDataset
    registry: CapabilityRegistry
    taxonomy: TaxonomyConfig


def _parent_delivery_metrics(
    dataset: ReturnDataset,
    data: _ParentResultData,
    parent_status: str,
    plan_summary: dict[str, Any],
) -> dict[str, Any]:
    return {
        "records": len(dataset.records),
        "valid_comments": int(dataset.records["has_text_evidence"].sum()),
        "unique_comments": len(dataset.unique_comments),
        "delivered_records": len(data.dataset.records),
        "delivered_comments": len(data.dataset.unique_comments),
        "partial_result": parent_status != "completed",
        "completed_segment_count": len(data.segments),
        "excluded_comments": int(plan_summary.get("excluded_count", 0)),
        "excluded_records": int(plan_summary.get("excluded_record_count", 0)),
    }


class LegacyResultExportMixin:
    _load_checkpoint: Callable[..., dict[str, ValidatedClassification]]
    _load_segments: Callable[..., list[dict[str, Any]]]
    _load_task: Callable[..., dict[str, Any] | None]
    _public_segment: Callable[..., dict[str, Any]]
    _review_count: Callable[..., int]
    _subset_dataset: Callable[..., ReturnDataset]
    _top_problem_labels: Callable[..., list[dict[str, Any]]]
    _write_checkpoint: Callable[..., None]
    capability_registry: CapabilityRegistry
    database: Database
    result_service: ClassificationResultService
    settings: Settings
    standard_service: ClassificationStandardService

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

    def _build_parent_result(
        self,
        task_id: str,
        dataset: ReturnDataset,
        parent_status: str,
    ) -> None:
        task = self._load_task(task_id)
        if task is None:
            return
        data = self._completed_parent_data(task_id, dataset)
        result_dir = self.settings.data_dir / "results" / task_id
        result_dir.mkdir(parents=True, exist_ok=True)
        result_version = int(task["result_version"] or 0) + 1
        suffix = "analysis" if parent_status == "completed" else "analysis-partial"
        output_path = result_dir / f"{suffix}-v{result_version}.xlsx"
        results_path = result_dir / "classifications-v1.json"
        self._write_checkpoint(results_path, data.results)
        export_results(
            output_path=output_path,
            dataset=data.dataset,
            results=data.results,
            taxonomy=data.taxonomy,
        )
        metrics = self._parent_export_metrics(task, dataset, parent_status, data)
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

    def _completed_parent_data(
        self, task_id: str, dataset: ReturnDataset
    ) -> _ParentResultData:
        completed_segments = [
            segment
            for segment in self._load_segments(task_id)
            if segment["status"] in COMPLETED_SEGMENT_STATUSES
        ]
        results, completed_keys = self._completed_segment_results(completed_segments)
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
        return _ParentResultData(
            task_id=task_id,
            segments=completed_segments,
            results=results,
            dataset=partial_dataset,
            registry=snapshot_registry,
            taxonomy=taxonomy,
        )

    def _completed_segment_results(
        self, completed_segments: list[dict[str, Any]]
    ) -> tuple[dict[str, ValidatedClassification], set[str]]:
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
        return results, completed_keys

    def _parent_export_metrics(
        self,
        task: dict[str, Any],
        dataset: ReturnDataset,
        parent_status: str,
        data: _ParentResultData,
    ) -> dict[str, Any]:
        serialized = {
            key: value.model_dump(mode="json") for key, value in data.results.items()
        }
        review_count = self._review_count(serialized)
        persisted_segments = self._load_segments(data.task_id)
        statuses = Counter((value["status"] for value in serialized.values()))
        snapshot = json_value(task.get("snapshot_json"), {})
        plan_summary = snapshot.get("execution_plan", {}).get("summary", {})
        return {
            **json_value(task.get("metrics_json"), {}),
            **_parent_delivery_metrics(dataset, data, parent_status, plan_summary),
            "review_count": review_count,
            "statuses": dict(statuses),
            "model_calls": sum(
                (int(segment["model_calls"]) for segment in persisted_segments)
            ),
            "cache_hits": sum(
                (int(segment["cache_hits"]) for segment in persisted_segments)
            ),
            "category_registry_version": snapshot.get("execution_plan", {}).get(
                "registry_version", data.registry.version
            ),
            "category_segments": [
                self._public_segment(segment) for segment in persisted_segments
            ],
            "top_problem_labels": self._top_problem_labels(
                data.dataset, data.results, data.taxonomy
            ),
        }
