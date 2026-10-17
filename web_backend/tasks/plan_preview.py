from __future__ import annotations

import hashlib
import json
import threading
from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from web_backend.api_contracts.tasks import TaskPlanPreviewRequest, TaskPreflightRequest
from web_backend.task_contracts import TaskPlanConflict
from web_backend.tasks.plan_response import input_versions

if TYPE_CHECKING:
    from return_semantics.capabilities import CapabilityRegistry
    from return_semantics.claims import ClaimsResolver
    from web_backend.classification_standard_service import (
        ClassificationStandardService,
    )
    from web_backend.task_plan_service import PreparedTaskPlan

_PREVIEW_CACHE_CAPACITY = 4


class TaskPlanPreviewMixin:
    prepare: Callable[..., PreparedTaskPlan]
    _load_inputs: Callable[..., tuple[dict[str, Any], dict[str, Any], dict[str, Any]]]
    _apply_model_policy: Callable[..., dict[str, Any]]
    standard_service: ClassificationStandardService
    registry: CapabilityRegistry | None
    claims_resolver: ClaimsResolver
    _preview_cache: OrderedDict[str, PreparedTaskPlan]
    _preview_lock: threading.RLock

    def _preview_identity(self, inputs: dict[str, Any]) -> str:
        returns, products, config = self._load_inputs(
            inputs["dataset_version_id"],
            inputs["product_version_id"],
            inputs["config_version_id"],
        )
        if inputs["model_policy"] is not None:
            config = self._apply_model_policy(config, inputs["model_policy"])
        sources = []
        for source in (returns, products):
            path = Path(source["file_path"])
            stat = path.stat()
            sources.append((str(path), stat.st_mtime_ns, stat.st_size))
        files = {entry.path for entry in self.claims_resolver.entries}
        if self.registry is not None:
            files.update(
                capability.taxonomy_path
                for capability in self.registry.capabilities
                if capability.taxonomy_path is not None
            )
        identity = {
            "request": inputs,
            "versions": input_versions(returns, products, config),
            "sources": sources,
            "standards": self.standard_service.current_version_by_agent(),
            "registry": repr(self.registry.capabilities) if self.registry else None,
            "claims": (
                self.claims_resolver.registry_version,
                repr(self.claims_resolver.entries),
            ),
            "files": [
                (str(path), hashlib.sha256(path.read_bytes()).hexdigest())
                for path in sorted(files)
            ],
        }
        return hashlib.sha256(
            json.dumps(identity, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()

    def _prepared_preview(self, inputs: dict[str, Any]) -> PreparedTaskPlan:
        # 每次检查当前输入；缓存只复用明细读取，不参与任务创建的权威校验。
        key = self._preview_identity(inputs)
        with self._preview_lock:
            cached = self._preview_cache.get(key)
            if cached is not None:
                self._preview_cache.move_to_end(key)
                return cached
        prepared = self.prepare(**inputs)
        with self._preview_lock:
            self._preview_cache[key] = prepared
            self._preview_cache.move_to_end(key)
            while len(self._preview_cache) > _PREVIEW_CACHE_CAPACITY:
                self._preview_cache.popitem(last=False)
        return prepared

    def preview_segment(self, payload: TaskPlanPreviewRequest) -> dict[str, Any]:
        prepared = self._prepared_preview(
            payload.model_dump(include=set(TaskPreflightRequest.model_fields))
        )
        if prepared.response["plan_hash"] != payload.plan_hash:
            raise TaskPlanConflict("执行计划已变化，请关闭明细并重新预检")
        assignments = prepared.execution_plan.classification_keys_by_segment(
            prepared.dataset
        )
        if payload.segment_key not in assignments:
            raise ValueError("执行分组不存在，请重新预检")
        keys = assignments[payload.segment_key]
        groups = prepared.dataset.unique_comments
        groups = groups.loc[groups["classification_key"].isin(keys)].copy()
        group_numbers = {
            key: index + 1 for index, key in enumerate(groups["classification_key"])
        }
        records = prepared.dataset.records
        records = records.loc[records["classification_key"].isin(keys)]
        record_total, group_total = len(records), len(groups)
        if payload.group_no is not None:
            if payload.view != "records" or payload.group_no > group_total:
                raise ValueError("评论组不存在")
            group_key = groups.iloc[payload.group_no - 1]["classification_key"]
            records = records.loc[records["classification_key"].eq(group_key)]
        frame = groups if payload.view == "groups" else records
        offset = (payload.page - 1) * payload.page_size
        items = []
        for row in (
            frame.iloc[offset : offset + payload.page_size]
            .fillna("")
            .to_dict("records")
        ):
            item = {
                "group_no": group_numbers[row["classification_key"]],
                "title": str(row.get("feedback_title", "")),
                "comment": str(
                    row["comment_normalized"]
                    if payload.view == "groups"
                    else row["comment_raw"]
                ),
                "record_count": int(row.get("record_count", 1)),
            }
            if payload.view == "records":
                item.update(
                    {
                        "source_row": int(row["source_row"]),
                        "date": str(row.get("return-date", "")),
                        "sku": str(row.get("source_sku", row.get("sku", ""))),
                        "product_name": str(row.get("product-name", "")),
                    }
                )
            items.append(item)
        return {
            "items": items,
            "total": len(frame),
            "record_total": record_total,
            "group_total": group_total,
            "page": payload.page,
            "page_size": payload.page_size,
        }
