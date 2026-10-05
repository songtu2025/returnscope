from __future__ import annotations

from web_backend.insight_report_diagnostics import (
    _filter_business_issue_text,
    _filter_diagnostic_text,
    _filter_issue_case_text,
    _has_text_anomaly,
)
from web_backend.insight_reports.quality_context import _LiveQualityEvaluation


def _sanitize_analysis(context: _LiveQualityEvaluation) -> None:
    analysis = context.analysis
    if not context.mapping_trusted:
        analysis["product_reason_matrix"] = []
        analysis["business_issues"] = []
        analysis["issue_cases"] = []
        analysis["diagnostics"] = [
            {
                **diagnostic,
                "hotspots": [],
                "variants": [],
                "samples": [
                    {
                        **sample,
                        "product_name": None,
                        "product_sku": None,
                    }
                    for sample in diagnostic.get("samples", [])
                ],
            }
            for diagnostic in analysis.get("diagnostics", [])
        ]
        analysis["samples"] = [
            {
                **sample,
                "product_name": None,
                "product_sku": None,
            }
            for sample in analysis.get("samples", [])
        ]
    if context.text_trusted:
        return
    analysis["diagnostics"] = [
        _filter_diagnostic_text(diagnostic)
        for diagnostic in analysis.get("diagnostics", [])
    ]
    analysis["issue_cases"] = [
        _filter_issue_case_text(case) for case in analysis.get("issue_cases", [])
    ]
    analysis["business_issues"] = [
        _filter_business_issue_text(issue)
        for issue in analysis.get("business_issues", [])
    ]
    analysis["samples"] = [
        sample
        for sample in analysis.get("samples", [])
        if not _has_text_anomaly(sample.get("comment"), sample.get("reason"))
    ]


def _sanitize_catalog(context: _LiveQualityEvaluation) -> None:
    blocked_markers = (
        (".hotspot.", ".variant.", "business_issue.", "issue_case.")
        if not context.mapping_trusted
        else ()
    )
    for evidence_id in list(context.catalog):
        if any(marker in evidence_id for marker in blocked_markers):
            context.catalog.pop(evidence_id, None)
            continue
        if context.text_trusted:
            continue
        if any(marker in evidence_id for marker in (".sample.", ".opinion.")):
            data = context.catalog[evidence_id].get("data", {})
            if _has_text_anomaly(
                data.get("opinion"),
                data.get("evidence"),
                data.get("comment"),
                data.get("reason"),
            ):
                context.catalog.pop(evidence_id, None)
        elif evidence_id.startswith("business_issue."):
            context.catalog[evidence_id]["data"] = _filter_business_issue_text(
                context.catalog[evidence_id].get("data", {})
            )
