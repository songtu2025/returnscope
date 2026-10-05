from __future__ import annotations

from typing import Any

from web_backend.insight_reports.business_issue_context import _BusinessIssueContext


def _business_issue_evidence(code: str, context: _BusinessIssueContext) -> list[str]:
    evidence_ids = [f"reason.{code}"]
    if context.cases:
        evidence_ids.extend((str(case.get("id")) for case in context.cases))
        primary_id = str(context.cases[0].get("id"))
        if context.cases[0].get("trend"):
            evidence_ids.append(f"{primary_id}.trend")
        evidence_ids.extend(
            (
                f"{primary_id}.opinion.{index}"
                for index in range(1, len(context.opinions) + 1)
            )
        )
        evidence_ids.extend(
            (
                f"{primary_id}.sample.{index}"
                for index in range(1, len(context.samples) + 1)
            )
        )
    elif context.trend_summary.get("status") == "available":
        evidence_ids.append(f"diagnostic.{code}.trend")
        evidence_ids.extend(
            (
                f"diagnostic.{code}.{context.dimension}.{index}"
                for index in range(1, len(context.hotspots) + 1)
            )
        )
        evidence_ids.extend(
            (
                f"diagnostic.{code}.opinion.{index}"
                for index in range(1, len(context.opinions) + 1)
            )
        )
        evidence_ids.extend(
            (
                f"diagnostic.{code}.sample.{index}"
                for index in range(1, len(context.samples) + 1)
            )
        )
    return list(dict.fromkeys(evidence_ids))


def _build_business_issue(
    code: str,
    reason: dict[str, Any],
    context: _BusinessIssueContext,
    profile: Any,
    preferred_codes: set[str],
) -> dict[str, Any]:
    evidence_ids = _business_issue_evidence(code, context)
    return {
        "id": f"business_issue.{code}",
        "reason_code": code,
        "label": str(reason.get("label") or code),
        "label_group": str(reason.get("label_group") or ""),
        "role": "supporting"
        if str(reason.get("label_group") or "") == "其他原因"
        or len(reason.get("subjects", [])) > 1
        else "primary"
        if not preferred_codes or code in preferred_codes
        else "supporting",
        "record_count": int(reason.get("record_count") or 0),
        "percentage": float(reason.get("percentage") or 0),
        "trend_summary": context.trend_summary,
        "trend": context.trend,
        "hotspot_dimension": context.dimension,
        "hotspot_label": profile.variant_label
        if context.dimension == "variant"
        else "商品",
        "hotspots": context.hotspots,
        "cases": context.cases,
        "contexts": {
            "parts": context.parts,
            "opinions": context.opinions,
            "samples": context.samples,
        },
        "validation_focus": context.validation_focus,
        "evidence_ids": evidence_ids,
    }
