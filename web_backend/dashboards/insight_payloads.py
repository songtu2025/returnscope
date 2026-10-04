from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from web_backend.dashboard_insight_details import _reason_detail_payload
from web_backend.dashboard_insight_preparation import PreparedInsightScope
from web_backend.dashboard_support import percentage


@dataclass(frozen=True)
class OverviewContent:
    overview: dict[str, Any]
    summary: dict[str, Any]
    hierarchy_problems: list[dict[str, Any]]
    details: dict[str, Any] | None
    filter_options: dict[str, list[str]]


def hierarchy_conflict_payload(
    dashboard_id: str, version_id: str, context: dict[str, Any]
) -> dict[str, Any]:
    return {
        "dashboard_id": dashboard_id,
        "version_id": version_id,
        "analysis_context": context["analysis_context"],
        "hierarchy_conflict": True,
        "message": "该看板包含不同层级标准版本，请按标准版本分别建立看板。",
        "reasons": [],
        "hierarchy_problems": [],
    }


def _label_group_breakdown(
    group_rows: list[sqlite3.Row], total_records: int
) -> list[dict[str, Any]]:
    return [
        {
            "value": str(row["value"]),
            "record_count": int(row["record_count"]),
            "percentage": percentage(int(row["record_count"]), total_records),
        }
        for row in group_rows
    ]


def overview_payload(
    dashboard_id: str,
    version_id: str,
    context: dict[str, Any],
    prepared: PreparedInsightScope,
    content: OverviewContent,
) -> dict[str, Any]:
    overview = content.overview
    summary = content.summary
    hierarchy_problems = content.hierarchy_problems
    details = content.details
    filter_options = content.filter_options
    taxonomy = prepared.taxonomy
    selected_reason = overview["selected_reason"]
    date_range = overview["date_range"]
    total_records = int(overview["total_records"])
    labeled_record_count = int(overview["labeled_record_count"])
    subject_breakdown = overview["subject_breakdown"]
    group_rows = overview["group_rows"]
    reasons = overview["reasons"]
    product_reason_matrix = overview["product_reason_matrix"]
    return {
        "dashboard_id": dashboard_id,
        "version_id": version_id,
        "analysis_context": context["analysis_context"],
        "counting_basis": context["counting_basis"],
        "summary": summary,
        "group_alignment": "unified-v1"
        if prepared.mixed_versions
        and (not (taxonomy and taxonomy.structure_version == 2))
        else "original",
        "hierarchy_problems": hierarchy_problems,
        "taxonomy": taxonomy.model_dump(mode="json") if taxonomy else None,
        "counting_note": "按反馈组在每个分组内去重；多标签占比之和可能超过100%。"
        if context["counting_basis"] == "feedback_group"
        else "按原始记录在每个分组内去重；多标签占比之和可能超过100%。",
        "date_range": date_range,
        "filter_options": filter_options,
        "category_groups": [str(row["value"]) for row in group_rows],
        "label_group_breakdown": _label_group_breakdown(group_rows, total_records),
        "total_record_count": total_records,
        "labeled_record_count": labeled_record_count,
        "label_coverage": percentage(labeled_record_count, total_records),
        "subject_breakdown": subject_breakdown,
        "reasons": reasons,
        "product_reason_matrix": product_reason_matrix,
        "selected_reason": selected_reason,
        **(_reason_detail_payload(details, selected_reason) if details else {}),
    }
