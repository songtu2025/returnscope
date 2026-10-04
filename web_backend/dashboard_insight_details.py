from __future__ import annotations

from typing import Any, cast

from return_semantics.schemas import TaxonomyConfig
from web_backend.dashboard_insight_overview import InsightQueryScope
from web_backend.dashboard_reason_evidence import (
    EVIDENCE_PAGE_SIZE as EVIDENCE_PAGE_SIZE,
)
from web_backend.dashboard_reason_evidence import (
    list_reason_evidence as list_reason_evidence,
)
from web_backend.dashboard_reason_semantics import _collect_reason_semantics
from web_backend.dashboard_support import percentage
from web_backend.dashboards.reason_products import collect_products, collect_variants
from web_backend.dashboards.reason_statistics import (
    collect_co_reasons,
    collect_trend,
    prepare_selected_records,
)
from web_backend.request_timing import timed_stage


@timed_stage("insight_reason_details")
def collect_reason_details(
    scope: InsightQueryScope,
    selected_reason: dict[str, Any] | None,
    overview: dict[str, Any],
    taxonomy: TaxonomyConfig | None = None,
) -> dict[str, Any]:
    total_records = int(overview["total_records"])
    label_counts = cast(dict[str, int], overview["label_counts"])
    details: dict[str, Any] = {
        "trend": [],
        "products": [],
        "variants": [],
        "co_reasons": [],
        "semantic_parts": [],
        "semantic_opinions": [],
        "semantic_record_count": 0,
        "evidence_items": [],
        "evidence_total": 0,
    }
    if selected_reason:
        selected_code = str(selected_reason["value"])
        prepare_selected_records(scope, selected_code)
        details["trend"] = collect_trend(scope)
        selected_count = int(selected_reason["record_count"])
        details["products"] = collect_products(scope, selected_count, total_records)
        details["variants"] = collect_variants(scope, selected_count, total_records)
        details["co_reasons"] = collect_co_reasons(
            scope,
            selected_code,
            selected_count,
            total_records,
            label_counts,
        )
        (
            details["semantic_parts"],
            details["semantic_opinions"],
            details["semantic_record_count"],
        ) = _collect_reason_semantics(scope, selected_code)
        details["evidence_total"] = selected_count
        details["evidence_items"] = list_reason_evidence(
            scope,
            selected_code,
            taxonomy,
            total=selected_count,
        )["items"]
    return details


def _reason_detail_payload(
    details: dict[str, Any], selected_reason: dict[str, Any] | None
) -> dict[str, Any]:
    semantic_record_count = int(details["semantic_record_count"])
    return {
        "trend": details["trend"],
        "products": details["products"],
        "variants": details["variants"],
        "co_reasons": details["co_reasons"],
        "semantic_profile": {
            "record_count": semantic_record_count,
            "coverage": percentage(
                semantic_record_count,
                int(selected_reason["record_count"]) if selected_reason else 0,
            ),
            "parts": details["semantic_parts"],
            "opinions": details["semantic_opinions"],
        },
        "evidence": {
            "items": details["evidence_items"],
            "total": int(details["evidence_total"]),
            "page": 1,
            "page_size": EVIDENCE_PAGE_SIZE,
        },
    }
