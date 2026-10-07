from __future__ import annotations

from datetime import date
from typing import Any

from return_semantics.schemas import TaxonomyConfig
from web_backend.classification_result_payload import prepare_semantic_record
from web_backend.common import json_value
from web_backend.dashboard_common import PAGE_SIZE_MAX
from web_backend.dashboards.record_filters import (
    feedback_group_scope as feedback_group_scope,
)
from web_backend.dashboards.record_filters import (
    normalize_filters as normalize_filters,
)
from web_backend.dashboards.record_filters import (
    record_where as record_where,
)
from web_backend.dashboards.version_context import (
    DASHBOARD_SOURCE_COLUMNS_SQL as DASHBOARD_SOURCE_COLUMNS_SQL,
)
from web_backend.dashboards.version_context import (
    DASHBOARD_SOURCE_JOINS_SQL as DASHBOARD_SOURCE_JOINS_SQL,
)
from web_backend.dashboards.version_context import (
    mixed_hierarchy as mixed_hierarchy,
)
from web_backend.dashboards.version_context import (
    serialize_dashboard_list as serialize_dashboard_list,
)
from web_backend.dashboards.version_context import (
    serialize_version as serialize_version,
)
from web_backend.dashboards.version_context import (
    version_context as version_context,
)
from web_backend.dashboards.version_context import (
    version_row as version_row,
)
from web_backend.dashboards.version_context import (
    version_select as version_select,
)

# 保留既有辅助入口的导入与序列化路径。
for _helper in (
    feedback_group_scope,
    normalize_filters,
    record_where,
    mixed_hierarchy,
    serialize_dashboard_list,
    serialize_version,
    version_context,
    version_row,
    version_select,
):
    _helper.__module__ = __name__
del _helper


def serialize_record(
    value: dict[str, Any], taxonomy: TaxonomyConfig | None = None
) -> dict[str, Any]:
    value["problem_labels"] = json_value(
        value.pop("problem_labels_json", None),
        [],
    )
    classification = json_value(value.pop("classification_json", None), {})
    value["classification"] = classification
    prepare_semantic_record(value, taxonomy)
    value["evidence"] = [
        unit.get("evidence")
        for unit in classification.get("semantic_units", [])
        if unit.get("evidence")
    ]
    return value


def clean_date(value: str | None) -> str:
    clean_value = (value or "").strip()
    if not clean_value:
        return ""
    try:
        return date.fromisoformat(clean_value).isoformat()
    except ValueError as exc:
        raise ValueError("日期必须使用 YYYY-MM-DD 格式") from exc


def percentage(numerator: int, denominator: int) -> float:
    return round(numerator * 100 / denominator, 1) if denominator else 0.0


def validate_page(page: int, page_size: int) -> tuple[int, int]:
    if page < 1:
        raise ValueError("page 必须大于等于 1")
    if not 1 <= page_size <= PAGE_SIZE_MAX:
        raise ValueError(f"page_size 必须在 1 到 {PAGE_SIZE_MAX} 之间")
    return page, page_size


def contains_pattern(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%")
    escaped = escaped.replace("_", "\\_")
    return f"%{escaped}%"
