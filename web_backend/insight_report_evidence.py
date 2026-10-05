from __future__ import annotations

from copy import deepcopy
from typing import Any

from web_backend.insight_report_contracts import PROMPT_VERSION, V5_PROMPT_VERSION
from web_backend.insight_report_decision_blueprint import _build_decision_blueprint
from web_backend.insight_report_diagnostics import (
    _build_business_issues,
    _filter_diagnostic_text,
    _filter_issue_case_text,
    _product_mapping_check,
)
from web_backend.insight_report_legacy_blueprint import _build_blueprint
from web_backend.insight_report_profiles import (
    InsightReportProfile,
    resolve_insight_report_profile,
)
from web_backend.insight_reports.evidence_catalog import _build_catalog


def _build_evidence(
    analysis: dict[str, Any], *, prompt_version: str = V5_PROMPT_VERSION
) -> dict[str, Any]:
    profile = resolve_insight_report_profile(list(analysis.get("sources", [])))
    product_mapping = _product_mapping_check(
        analysis.get("summary", {}),
        list(analysis.get("filter_options", {}).get("listings", [])),
    )
    report_analysis = _prepare_report_analysis(analysis, product_mapping, profile)
    evidence = {
        "source": _build_source(analysis, product_mapping, profile),
        "catalog": _build_catalog(
            report_analysis,
            product_mapping,
            profile,
            analysis_context=analysis.get("analysis_context", "returns"),
        ),
        "analysis": report_analysis,
    }
    evidence["blueprint"] = (
        _build_decision_blueprint(evidence)
        if prompt_version == PROMPT_VERSION
        else _build_blueprint(evidence)
    )
    return evidence


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


def _prepare_report_analysis(
    analysis: dict[str, Any],
    product_mapping: dict[str, Any],
    profile: InsightReportProfile,
) -> dict[str, Any]:
    summary = analysis.get("summary", {})
    groups = list(analysis.get("label_group_breakdown", []))[:12]
    reasons = list(analysis.get("reasons", []))[:15]
    subjects = list(analysis.get("subject_breakdown", []))[:10]
    products = list(analysis.get("product_reason_matrix", []))[:8]
    diagnostics = list(analysis.get("diagnostics", []))[:4]
    issue_cases = list(analysis.get("issue_cases", []))[:12]
    review_bias = analysis.get("review_bias", {})
    text_quality = analysis.get("text_quality", {})
    mapping_trusted = product_mapping.get("status") != "needs_review"
    text_trusted = text_quality.get("status") != "needs_review"
    safe_products = products if mapping_trusted else []
    safe_diagnostics = deepcopy(diagnostics)
    safe_issue_cases = deepcopy(issue_cases) if mapping_trusted else []
    if not mapping_trusted:
        safe_diagnostics = _mask_product_diagnostics(diagnostics)
    if not text_trusted:
        safe_diagnostics = [
            _filter_diagnostic_text(diagnostic) for diagnostic in safe_diagnostics
        ]
        safe_issue_cases = [_filter_issue_case_text(case) for case in safe_issue_cases]
    business_issues = _build_business_issues(
        safe_diagnostics, safe_issue_cases, profile=profile
    )
    samples = _representative_samples(safe_diagnostics)
    return {
        "summary": summary,
        "label_group_breakdown": groups,
        "reasons": reasons,
        "subject_breakdown": subjects,
        "product_reason_matrix": safe_products,
        "diagnostics": safe_diagnostics,
        "issue_cases": safe_issue_cases,
        "business_issues": business_issues,
        "review_bias": review_bias,
        "text_quality": text_quality,
        "report_profile": profile.snapshot(),
        "samples": samples,
    }


def _representative_samples(diagnostics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    seen_samples: set[str] = set()
    for diagnostic in diagnostics:
        code = str(diagnostic.get("reason_code") or "unknown")
        for index, sample in enumerate(diagnostic.get("samples", []), 1):
            text = str(sample.get("comment") or sample.get("reason") or "").strip()
            if text and text not in seen_samples and (len(samples) < 8):
                samples.append(
                    {
                        **sample,
                        "reason_code": code,
                        "evidence_id": f"diagnostic.{code}.sample.{index}",
                    }
                )
                seen_samples.add(text)
    return samples


def _build_source(
    analysis: dict[str, Any],
    product_mapping: dict[str, Any],
    profile: InsightReportProfile,
) -> dict[str, Any]:
    summary = analysis.get("summary", {})
    text_quality = analysis.get("text_quality", {})
    listings = list(analysis.get("filter_options", {}).get("listings", []))
    product_names = list(analysis.get("filter_options", {}).get("product_names", []))
    sources = list(analysis.get("sources", []))
    mapping_trusted = product_mapping.get("status") != "needs_review"
    text_trusted = text_quality.get("status") != "needs_review"
    total_record_count = int(
        summary.get("total_record_count") or summary.get("record_count") or 0
    )
    pending_review_count = int(summary.get("pending_review_record_count") or 0)
    coverage_rate = float(
        summary.get("coverage_rate")
        if summary.get("coverage_rate") is not None
        else 100
        if total_record_count
        else 0
    )
    checked_comment_count = int(text_quality.get("checked_record_count") or 0)
    anomaly_comment_count = int(text_quality.get("anomaly_record_count") or 0)
    clean_comment_count = max(checked_comment_count - anomaly_comment_count, 0)
    clean_comment_rate = (
        round(clean_comment_count / checked_comment_count * 100, 1)
        if checked_comment_count
        else 0.0
    )
    quality_issue_codes = []
    if pending_review_count:
        quality_issue_codes.append("pending_review")
    if not text_trusted:
        quality_issue_codes.append("text_quality")
    if not mapping_trusted:
        quality_issue_codes.append("product_mapping")
    return {
        "dashboard_id": analysis.get("dashboard_id"),
        "dashboard_version_id": analysis.get("version_id"),
        "analysis_context": analysis.get("analysis_context", "returns"),
        "date_range": analysis.get("date_range", {}),
        "label_coverage": analysis.get("label_coverage", 0),
        "listings": listings,
        "product_count": len(product_names),
        "total_record_count": total_record_count,
        "included_record_count": int(summary.get("record_count") or 0),
        "pending_review_record_count": pending_review_count,
        "coverage_rate": coverage_rate,
        "product_mapping": product_mapping,
        "text_quality": text_quality,
        "clean_comment_record_count": clean_comment_count,
        "clean_comment_rate": clean_comment_rate,
        "quality_issue_codes": quality_issue_codes,
        "report_status": "provisional" if quality_issue_codes else "final",
        "agent_keys": sorted(
            {
                str(source.get("agent_key"))
                for source in sources
                if source.get("agent_key")
            }
        ),
        "taxonomy_versions": sorted(
            {
                str(source.get("taxonomy_version") or source.get("taxonomy_version_id"))
                for source in sources
                if source.get("taxonomy_version") or source.get("taxonomy_version_id")
            }
        ),
        "report_profile": profile.snapshot(),
    }
