from __future__ import annotations

from typing import Any


def result_delivery_state(
    *,
    quality_status: str | None,
    publish_status: str | None,
    parent_version_id: str | None = None,
    source_review_batch_id: str | None = None,
) -> dict[str, Any]:
    raw_quality = str(quality_status or "")
    is_derived = bool(parent_version_id or source_review_batch_id)
    if raw_quality in {"review_required", "needs_review"}:
        delivery_status = "needs_review"
    elif raw_quality == "ready" and is_derived:
        delivery_status = "review-derived"
    elif raw_quality == "ready":
        delivery_status = "ready"
    else:
        delivery_status = "unusable"

    dashboard_blockers: list[dict[str, Any]] = []
    if publish_status != "published":
        reason = {
            "code": "not_published",
            "message": "分类结果版本尚未发布",
        }
        dashboard_blockers.append(reason)

    if delivery_status == "unusable":
        reason = {
            "code": "unusable",
            "message": "分类结果不可交付",
        }
        dashboard_blockers.append(reason)

    return {
        "delivery_status": delivery_status,
        "publish_origin": (
            "review-derived" if is_derived else "original-classification"
        ),
        "dashboard_eligibility": not dashboard_blockers,
        "blocking_reasons": dashboard_blockers,
    }
