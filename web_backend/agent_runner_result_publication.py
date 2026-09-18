from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from return_semantics.analysis_context import analysis_context_from_snapshot
from return_semantics.data import ReturnDataset
from return_semantics.schemas import ValidatedClassification
from return_semantics.semantic_review import requires_system_rerun
from web_backend.classification_result_service import (
    ClassificationResultService,
    ResultPublicationError,
)
from web_backend.common import json_value
from web_backend.dataset_cache import load_cached_dataset


class IncompleteResultCheckpoint(ValueError):
    pass


class ResultPublicationMixin:
    result_service: ClassificationResultService
    _capability_for_segment: Callable[..., Any]
    _load_segment: Callable[..., dict[str, Any] | None]
    _load_task: Callable[..., dict[str, Any] | None]
    _taxonomy_for_segment: Callable[..., Any]

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
            raise IncompleteResultCheckpoint(f"分类检查点缺少 {missing_count} 个分类键")
        capability = self._capability_for_segment(segment)
        taxonomy = self._taxonomy_for_segment(segment, capability)
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
        return any(requires_system_rerun(value, "") for value in results.values())

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
            key: value.model_dump(mode="json") for key, value in results.items()
        }
        temporary = path.with_suffix(f"{path.suffix}.tmp")
        temporary.write_text(
            json.dumps(serialized, ensure_ascii=False),
            encoding="utf-8",
        )
        temporary.replace(path)

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
