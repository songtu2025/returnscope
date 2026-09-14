from __future__ import annotations

from typing import Any

from web_backend.dashboard_service import TEXT_ENCODING_ANOMALY
from web_backend.insight_report_profiles import resolve_insight_report_profile


def _diagnostic_reason_codes(analysis: dict[str, Any]) -> list[str]:
    reasons = list(analysis.get("reasons", []))[:15]
    profile = resolve_insight_report_profile(analysis.get("sources"))
    reason_by_code = {str(reason.get("value") or ""): reason for reason in reasons}
    selected: list[str] = []
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
        reason_by_code[code]
        for code in profile.preferred_reason_codes
        if code in reason_by_code
    ]
    candidates.extend(actionable[:2])
    if broad_reason:
        candidates.append(broad_reason)
    if not candidates and reasons:
        candidates.append(reasons[0])

    for reason in candidates:
        code = str(reason.get("value") or "")
        if code and code not in selected:
            selected.append(code)
    return [code for code in selected if code][:4]


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


def _has_text_anomaly(*values: Any) -> bool:
    text = " ".join(str(value or "") for value in values)
    return bool(TEXT_ENCODING_ANOMALY.search(text))


def _filter_diagnostic_text(
    diagnostic: dict[str, Any],
) -> dict[str, Any]:
    semantic_profile = diagnostic.get("semantic_profile", {})
    opinions = [
        opinion
        for opinion in semantic_profile.get("opinions", [])
        if not _has_text_anomaly(
            opinion.get("opinion"),
            opinion.get("evidence"),
        )
    ]
    samples = [
        sample
        for sample in diagnostic.get("samples", [])
        if not _has_text_anomaly(
            sample.get("comment"),
            sample.get("reason"),
        )
    ]
    return {
        **diagnostic,
        "semantic_profile": {
            **semantic_profile,
            "opinions": opinions,
        },
        "samples": samples,
        "text_evidence": {
            "status": "available" if opinions or samples else "limited",
            "opinion_count": len(opinions),
            "sample_count": len(samples),
        },
    }


def _filter_issue_case_text(case: dict[str, Any]) -> dict[str, Any]:
    semantic_profile = case.get("semantic_profile", {})
    opinions = [
        opinion
        for opinion in semantic_profile.get("opinions", [])
        if not _has_text_anomaly(
            opinion.get("opinion"),
            opinion.get("evidence"),
        )
    ]
    samples = [
        sample
        for sample in case.get("samples", [])
        if not _has_text_anomaly(
            sample.get("comment"),
            sample.get("reason"),
        )
    ]
    return {
        **case,
        "semantic_profile": {
            **semantic_profile,
            "opinions": opinions,
        },
        "samples": samples,
    }


def _filter_business_issue_text(
    issue: dict[str, Any],
) -> dict[str, Any]:
    contexts = issue.get("contexts", {})
    opinions = [
        opinion
        for opinion in contexts.get("opinions", [])
        if not _has_text_anomaly(
            opinion.get("opinion"),
            opinion.get("evidence"),
        )
    ]
    samples = [
        sample
        for sample in contexts.get("samples", [])
        if not _has_text_anomaly(
            sample.get("comment"),
            sample.get("reason"),
        )
    ]
    return {
        **issue,
        "contexts": {
            **contexts,
            "opinions": opinions,
            "samples": samples,
        },
    }


def _build_business_issues(
    diagnostics: list[dict[str, Any]],
    issue_cases: list[dict[str, Any]],
    *,
    profile: Any,
) -> list[dict[str, Any]]:
    preferred_codes = set(profile.preferred_reason_codes)
    cases_by_code: dict[str, list[dict[str, Any]]] = {}
    for case in issue_cases:
        code = str(case.get("reason_code") or "")
        if code:
            cases_by_code.setdefault(code, []).append(case)
    issues = []
    for diagnostic in diagnostics:
        reason = diagnostic.get("selected_reason") or {}
        code = str(diagnostic.get("reason_code") or "")
        if not code:
            continue
        cases = []
        for case in cases_by_code.get(code, [])[:3]:
            trend = list(case.get("trend", []))
            cases.append(
                {
                    **case,
                    "value": str(case.get("product_sku") or ""),
                    "product_reason_rate": float(case.get("issue_rate") or 0),
                    "overall_reason_rate": float(case.get("overall_rate") or 0),
                    "trend_summary": _trend_summary(
                        trend,
                        str(diagnostic.get("date_range", {}).get("date_to") or "")
                        or None,
                    ),
                }
            )

        if cases:
            dimension = "variant"
            hotspots = cases
            primary_case = cases[0]
            trend_summary = primary_case["trend_summary"]
            trend = list(primary_case.get("trend", []))
            semantic_profile = primary_case.get("semantic_profile", {})
            opinions = list(semantic_profile.get("opinions", []))[:3]
            samples = list(primary_case.get("samples", []))[:3]
            parts = list(semantic_profile.get("parts", []))[:4]
            top_opinion = next(iter(opinions), None)
            validation_focus = (
                f"先复核 {primary_case.get('product_sku')} 中"
                f"“{top_opinion.get('opinion')}”对应的评论，"
                "再核对实物规格、页面说明与使用情境"
                if top_opinion
                else (
                    f"先复核 {primary_case.get('product_sku')} 的"
                    f"{reason.get('label') or code}评论，再核对实物和页面说明"
                )
            )
        else:
            dimension = "variant" if diagnostic.get("variants") else "product"
            hotspots = list(
                diagnostic.get(
                    "variants" if dimension == "variant" else "hotspots",
                    [],
                )
            )[:3]
            trend_summary = diagnostic.get("trend_summary", {})
            trend = list(diagnostic.get("trend", []))
            semantic_profile = diagnostic.get("semantic_profile", {})
            opinions = list(semantic_profile.get("opinions", []))[:3]
            samples = list(diagnostic.get("samples", []))[:3]
            parts = list(semantic_profile.get("parts", []))[:4]
            validation_focus = profile.diagnostic_action

        evidence_ids = [f"reason.{code}"]
        if cases:
            evidence_ids.extend(str(case.get("id")) for case in cases)
            primary_id = str(cases[0].get("id"))
            if cases[0].get("trend"):
                evidence_ids.append(f"{primary_id}.trend")
            evidence_ids.extend(
                f"{primary_id}.opinion.{index}" for index in range(1, len(opinions) + 1)
            )
            evidence_ids.extend(
                f"{primary_id}.sample.{index}" for index in range(1, len(samples) + 1)
            )
        elif trend_summary.get("status") == "available":
            evidence_ids.append(f"diagnostic.{code}.trend")
            evidence_ids.extend(
                f"diagnostic.{code}.{dimension}.{index}"
                for index in range(1, len(hotspots) + 1)
            )
            evidence_ids.extend(
                f"diagnostic.{code}.opinion.{index}"
                for index in range(1, len(opinions) + 1)
            )
            evidence_ids.extend(
                f"diagnostic.{code}.sample.{index}"
                for index in range(1, len(samples) + 1)
            )
        issues.append(
            {
                "id": f"business_issue.{code}",
                "reason_code": code,
                "label": str(reason.get("label") or code),
                "label_group": str(reason.get("label_group") or ""),
                "role": (
                    "supporting"
                    if (
                        str(reason.get("label_group") or "") == "其他原因"
                        or len(reason.get("subjects", [])) > 1
                    )
                    else "primary"
                    if not preferred_codes or code in preferred_codes
                    else "supporting"
                ),
                "record_count": int(reason.get("record_count") or 0),
                "percentage": float(reason.get("percentage") or 0),
                "trend_summary": trend_summary,
                "trend": trend,
                "hotspot_dimension": dimension,
                "hotspot_label": (
                    profile.variant_label if dimension == "variant" else "商品"
                ),
                "hotspots": hotspots,
                "cases": cases,
                "contexts": {
                    "parts": parts,
                    "opinions": opinions,
                    "samples": samples,
                },
                "validation_focus": validation_focus,
                "evidence_ids": list(dict.fromkeys(evidence_ids)),
            }
        )
    return issues


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
