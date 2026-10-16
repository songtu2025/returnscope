from __future__ import annotations

from collections.abc import Callable
from typing import Any

from web_backend.api_contracts.tasks import TaskPlanPreviewRequest, TaskPreflightRequest
from web_backend.task_contracts import TaskPlanConflict


class TaskPlanPreviewMixin:
    prepare: Callable[..., Any]

    def preview_segment(self, payload: TaskPlanPreviewRequest) -> dict[str, Any]:
        prepared = self.prepare(
            **payload.model_dump(include=set(TaskPreflightRequest.model_fields))
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
