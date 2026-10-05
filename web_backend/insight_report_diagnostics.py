from __future__ import annotations

from typing import Any

from web_backend.insight_reports.diagnostic_summary import (
    _compact_diagnostic as _compact_diagnostic,
)
from web_backend.insight_reports.diagnostic_summary import (
    _diagnostic_reason_codes as _diagnostic_reason_codes,
)
from web_backend.insight_reports.diagnostic_summary import (
    _product_mapping_check as _product_mapping_check,
)
from web_backend.insight_reports.diagnostic_summary import (
    _rank_hotspots as _rank_hotspots,
)
from web_backend.insight_reports.diagnostic_summary import (
    _trend_summary as _trend_summary,
)
from web_backend.insight_reports.diagnostic_text import (
    _filter_business_issue_text as _filter_business_issue_text,
)
from web_backend.insight_reports.diagnostic_text import (
    _filter_diagnostic_text as _filter_diagnostic_text,
)
from web_backend.insight_reports.diagnostic_text import (
    _filter_issue_case_text as _filter_issue_case_text,
)
from web_backend.insight_reports.diagnostic_text import (
    _has_text_anomaly as _has_text_anomaly,
)


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
