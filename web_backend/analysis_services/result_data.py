"""用已发布数据库结果组装历史分析视图，复用既有导出字段与分析计算。"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from return_analysis.data import AnalysisData, load_analysis_data
from return_semantics.data import ReturnDataset
from return_semantics.export_formatting import _display_key
from return_semantics.exporter import build_analysis_frames
from return_semantics.schemas import ValidatedClassification
from return_semantics.semantic_review import review_route
from web_backend.classification_results.effective_content import load_content
from web_backend.database import Database
from web_backend.result_hierarchy import result_taxonomy


def analysis_version_ids(segments: list[Any], listing: str | None) -> tuple[str, ...]:
    selected = [
        segment
        for segment in segments
        if not listing or json.loads(segment["scope_json"]).get("listing") == listing
    ]
    if any(segment["result_deleted_at"] for segment in selected):
        raise ValueError("分类结果已移除，请先恢复分类结果")
    if not selected or not all(
        segment["result_version_id"] and segment["standard_version_id"]
        for segment in selected
    ):
        return ()
    return tuple(str(segment["result_version_id"]) for segment in selected)


def published_analysis_data(
    database: Database, version_ids: tuple[str, ...]
) -> AnalysisData:
    sheets: dict[str, list[pd.DataFrame]] = {
        "分类明细": [],
        "语义单元": [],
        "未知语义": [],
    }
    with database.transaction() as connection:
        for version_id in version_ids:
            state = connection.execute(
                "SELECT r.deleted_at FROM classification_result_versions v "
                "JOIN classification_results r ON r.id=v.result_id WHERE v.id=?",
                (version_id,),
            ).fetchone()
            if state is None or state[0]:
                raise ValueError("分类结果已移除，请先恢复分类结果")
            taxonomy = result_taxonomy(connection, version_id)
            if taxonomy is None:
                raise ValueError("分类结果缺少标准快照")
            content = load_content(connection, version_id)
            dataset, results = _analysis_inputs(content)
            frames, _routes = build_analysis_frames(dataset, results, taxonomy)
            routes = {
                _display_key(unit["classification_key"]): review_route(
                    unit["classification"], unit["comment"] or "", taxonomy
                )
                for unit in content["units"]
            }
            frames["分类明细"]["复核路由"] = frames["分类明细"]["分类键"].map(routes)
            for name, frame in frames.items():
                sheets[name].append(frame)
    return load_analysis_data(
        {name: pd.concat(frames, ignore_index=True) for name, frames in sheets.items()}
    )


def _analysis_inputs(
    content: dict[str, Any],
) -> tuple[ReturnDataset, dict[str, ValidatedClassification]]:
    results = {
        unit["classification_key"]: ValidatedClassification.model_validate(
            {
                key: value
                for key, value in unit["classification"].items()
                if key in ValidatedClassification.model_fields
            }
        )
        for unit in content["units"]
    }
    records = (
        pd.DataFrame(content["records"])
        .fillna("")
        .rename(
            columns={
                "return_date": "return-date",
                "order_id": "order-id",
                "store_site": "store",
                "comment": "comment_raw",
            }
        )
    )
    units = {unit["classification_key"]: unit for unit in content["units"]}
    records["sku"] = records["matched_msku"]
    records["comment_normalized"] = records["classification_key"].map(
        lambda key: units[key]["comment"] or ""
    )
    records["has_text_evidence"] = records["comment_normalized"].ne("")
    counts = records["classification_key"].value_counts()
    comments = pd.DataFrame(
        [
            {
                "classification_key": key,
                "reason": unit["reason"] or "",
                "comment_normalized": unit["comment"] or "",
                "record_count": int(counts[key]),
            }
            for key, unit in units.items()
        ]
    )
    return ReturnDataset(records, comments, frozenset(records["sku"])), results
