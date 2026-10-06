from __future__ import annotations

from typing import Any

from web_backend.insight_report_profiles import resolve_insight_report_profile

_REASON_SCAN_LIMIT = 15
_ACTIONABLE_REASON_LIMIT = 2
_DIAGNOSTIC_REASON_LIMIT = 4


def _mask_product_diagnostics(
    diagnostics: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            **diagnostic,
            "hotspots": [],
            "variants": [],
            "samples": [
                {**sample, "product_name": None, "product_sku": None}
                for sample in diagnostic.get("samples", [])
            ],
        }
        for diagnostic in diagnostics
    ]


def _diagnostic_reason_codes(analysis: dict[str, Any]) -> list[str]:
    reasons = list(analysis.get("reasons", []))[:_REASON_SCAN_LIMIT]
    profile = resolve_insight_report_profile(analysis.get("sources"))
    candidates = _diagnostic_reason_candidates(reasons, profile.preferred_reason_codes)
    codes = [str(reason.get("value") or "") for reason in candidates]
    return list(dict.fromkeys(code for code in codes if code))[
        :_DIAGNOSTIC_REASON_LIMIT
    ]


def _diagnostic_reason_candidates(
    reasons: list[dict[str, Any]], preferred_codes: tuple[str, ...]
) -> list[dict[str, Any]]:
    reason_by_code = {str(reason.get("value") or ""): reason for reason in reasons}
    actionable = [
        reason
        for reason in reasons
        if "PRODUCT" in reason.get("subjects", [])
        and str(reason.get("label_group") or "") != "其他原因"
    ]
    broad_reason = next(
        (
            reason
            for reason in reasons
            if len(reason.get("subjects", [])) > 1
            or str(reason.get("label_group") or "") == "其他原因"
        ),
        None,
    )
    candidates = [
        reason_by_code[code] for code in preferred_codes if code in reason_by_code
    ]
    candidates.extend(actionable[:_ACTIONABLE_REASON_LIMIT])
    if broad_reason:
        candidates.append(broad_reason)
    return candidates or reasons[:1]


def _trend_summary(
    trend: list[dict[str, Any]],
    date_to: str | None,
) -> dict[str, Any]:
    usable = [
        item
        for item in trend
        if not item.get("low_sample")
        and (not date_to or str(item.get("period_end") or "") <= date_to)
    ]
    if len(usable) < 8:
        return {"status": "insufficient", "point_count": len(usable)}

    window = min(4, len(usable) // 2)
    early = sum(float(item.get("percentage") or 0) for item in usable[:window])
    recent = sum(float(item.get("percentage") or 0) for item in usable[-window:])
    early_rate = round(early / window, 1)
    recent_rate = round(recent / window, 1)
    delta = round(recent_rate - early_rate, 1)
    direction = "stable"
    if delta >= 2:
        direction = "rising"
    elif delta <= -2:
        direction = "falling"
    return {
        "status": "available",
        "point_count": len(usable),
        "window_weeks": window,
        "early_rate": early_rate,
        "recent_rate": recent_rate,
        "delta_percentage_points": delta,
        "direction": direction,
        "early_period": {
            "date_from": usable[0].get("period_start"),
            "date_to": usable[window - 1].get("period_end"),
        },
        "recent_period": {
            "date_from": usable[-window].get("period_start"),
            "date_to": usable[-1].get("period_end"),
        },
    }


def _rank_hotspots(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hotspots = []
    for product in products:
        total = int(product.get("total_record_count") or 0)
        related = int(product.get("record_count") or 0)
        baseline = float(product.get("overall_reason_rate") or 0)
        excess = round(related - total * baseline / 100)
        if (
            product.get("reliable")
            and related >= 10
            and float(product.get("lift") or 0) > 1
            and excess > 0
        ):
            hotspots.append({**product, "excess_record_count": excess})
    return sorted(
        hotspots,
        key=lambda item: (
            int(item.get("excess_record_count") or 0),
            float(item.get("lift") or 0),
        ),
        reverse=True,
    )[:4]


def _compact_diagnostic(data: dict[str, Any]) -> dict[str, Any]:
    date_range = data.get("date_range", {})
    trend = list(data.get("trend", []))
    selected_reason = data.get("selected_reason") or {}
    samples = [
        {
            "comment": item.get("comment"),
            "reason": item.get("reason"),
            "product_name": item.get("product_name"),
            "product_sku": item.get("product_sku"),
            "return_date": item.get("return_date"),
            "problem_labels": item.get("problem_labels", []),
        }
        for item in data.get("evidence", {}).get("items", [])[:4]
    ]
    semantic_profile = data.get("semantic_profile", {})
    return {
        "reason_code": selected_reason.get("value"),
        "selected_reason": selected_reason,
        "date_range": date_range,
        "trend": trend[:36],
        "trend_summary": _trend_summary(
            trend,
            str(date_range.get("date_to") or "") or None,
        ),
        "hotspots": _rank_hotspots(list(data.get("products", []))),
        "variants": _rank_hotspots(list(data.get("variants", []))),
        "co_reasons": list(data.get("co_reasons", []))[:6],
        "semantic_profile": {
            "record_count": semantic_profile.get("record_count", 0),
            "coverage": semantic_profile.get("coverage", 0),
            "parts": list(semantic_profile.get("parts", []))[:6],
            "opinions": list(semantic_profile.get("opinions", []))[:4],
        },
        "samples": samples,
    }


def _product_mapping_check(
    summary: dict[str, Any],
    listings: list[str],
) -> dict[str, Any]:
    unmatched = int(summary.get("product_unmatched_count") or 0)
    missing = int(summary.get("product_name_missing_count") or 0)
    listing = str(listings[0]).strip() if len(listings) == 1 else None
    if not unmatched and not missing:
        return {
            "status": "consistent",
            "listing": listing,
            "unmatched_record_count": 0,
            "missing_name_record_count": 0,
            "examples": [],
            "note": "商品关系以已发布商品主数据为准，未发现未匹配记录。",
        }

    return {
        "status": "needs_review",
        "listing": listing,
        "unmatched_record_count": unmatched,
        "missing_name_record_count": missing,
        "examples": [],
        "note": (
            f"当前有 {unmatched} 条未匹配商品记录、{missing} 条缺少商品名称，"
            "商品级行动前需补全已发布商品主数据关系。"
        ),
    }
