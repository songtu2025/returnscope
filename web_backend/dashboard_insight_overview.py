from __future__ import annotations

from typing import Any

from web_backend.dashboard_insight_scope import (
    InsightQueryScope as InsightQueryScope,
)
from web_backend.dashboard_insight_scope import (
    prepare_scope_semantics as prepare_scope_semantics,
)
from web_backend.dashboard_insight_scope import (
    subject_label_filter as subject_label_filter,
)
from web_backend.dashboard_reason_context import (
    collect_label_counts as collect_label_counts,
)
from web_backend.dashboard_reason_context import (
    collect_reason_context as collect_reason_context,
)
from web_backend.dashboard_semantic_breakdown import (
    _collect_semantic_breakdown,
)
from web_backend.dashboard_semantic_breakdown import (
    collect_subject_breakdown as collect_subject_breakdown,
)
from web_backend.dashboards.overview_products import collect_product_reason_matrix
from web_backend.dashboards.overview_statistics import (
    collect_date_range,
    collect_group_rows,
    collect_reasons,
    prepare_weighted_scope,
)
from web_backend.request_timing import timed_stage


@timed_stage("insight_overview")
def collect_insight_overview(
    scope: InsightQueryScope, *, total_record_count: int | None = None
) -> dict[str, Any]:
    date_range = collect_date_range(scope)
    total_records, labeled_record_count = collect_label_counts(scope)
    if total_record_count is not None:
        total_records = total_record_count
    weighted_scope = prepare_weighted_scope(scope)
    subject_breakdown, reason_subjects = _collect_semantic_breakdown(
        weighted_scope, total_records
    )
    group_rows = collect_group_rows(scope)
    reasons, label_names, label_counts = collect_reasons(
        scope,
        weighted_scope,
        total_records,
        reason_subjects,
    )
    product_reason_matrix = collect_product_reason_matrix(
        scope,
        total_records,
        label_names,
        label_counts,
    )
    selected_reason = (
        None
        if scope.report_mode
        else next(
            (item for item in reasons if item["value"] == scope.requested_problem),
            reasons[0] if reasons else None,
        )
    )

    return {
        "date_range": date_range,
        "total_records": total_records,
        "labeled_record_count": labeled_record_count,
        "subject_breakdown": subject_breakdown,
        "group_rows": group_rows,
        "label_names": label_names,
        "label_counts": label_counts,
        "reasons": reasons,
        "product_reason_matrix": product_reason_matrix,
        "selected_reason": selected_reason,
    }
