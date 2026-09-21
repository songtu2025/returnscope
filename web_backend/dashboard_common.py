from __future__ import annotations

import re
from typing import Any

PAGE_SIZE_DEFAULT = 50
PAGE_SIZE_MAX = 200
PLAN_VERSION = "dashboard-dataset-plan-v2"
FEEDBACK_GROUP_BASIS = "feedback_group"
QUALITY_STATUSES = {"ready", "review_required", "unusable", "excluded"}
COMMENT_SUMMARY_STATUSES = (
    "POSITIVE",
    "NEGATIVE",
    "MIXED",
    "CONFLICT",
    "NO_CONFIRMED",
)
FILTER_COLUMNS = {
    "listing": "listing",
    "product_name": "product_name",
    "product_sku": "product_sku",
    "order_id": "order_id",
    "quality_status": "quality_status",
}
ALLOWED_FILTERS = {"problem", *FILTER_COLUMNS}
GROUP_COLUMNS = {
    "listing": "r.listing",
    "product_name": "r.product_name",
    "product_sku": "r.product_sku",
    "order_id": "r.order_id",
}
SUBJECT_LABELS = {
    "PRODUCT": "商品相关",
    "CUSTOMER": "顾客相关",
    "ORDER": "订单相关",
    "DELIVERY": "配送相关",
    "SERVICE": "服务相关",
}
TEXT_ENCODING_ANOMALY = re.compile(
    r"(?:[A-Za-z][\u4e00-\u9fff]|[\u4e00-\u9fff][A-Za-z]|\ufffd)"
)


def classification_comment_status(payload: dict[str, Any]) -> str:
    summary = payload.get("comment_summary")
    if isinstance(summary, dict):
        status = str(summary.get("status") or "")
        is_explicit = status != "NO_CONFIRMED" or any(
            summary.get(field)
            for field in ("fact_ids", "positive_label_codes", "negative_label_codes")
        )
        if is_explicit and status in COMMENT_SUMMARY_STATUSES:
            return status

    legacy_status = str(payload.get("comment_summary_status") or "")
    if legacy_status in COMMENT_SUMMARY_STATUSES:
        return legacy_status

    sentiments = {
        str(unit.get("sentiment") or "")
        for unit in payload.get("semantic_units", [])
        if isinstance(unit, dict)
        and str(unit.get("assertion") or "AFFIRMED") == "AFFIRMED"
    }
    if {"POSITIVE", "NEGATIVE"}.issubset(sentiments):
        relation_types = {
            str(relation.get("relation_type") or "")
            for relation in payload.get("semantic_relations", [])
            if isinstance(relation, dict)
        }
        return "CONFLICT" if "CONFLICT" in relation_types else "MIXED"
    if "NEGATIVE" in sentiments:
        return "NEGATIVE"
    if "POSITIVE" in sentiments:
        return "POSITIVE"
    return "NO_CONFIRMED"


class DashboardConflict(ValueError):
    pass


class DashboardNotFound(ValueError):
    pass
