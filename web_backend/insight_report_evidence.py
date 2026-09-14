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
from web_backend.insight_report_profiles import resolve_insight_report_profile


def _build_evidence(
    analysis: dict[str, Any],
    *,
    prompt_version: str = V5_PROMPT_VERSION,
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
    listings = list(analysis.get("filter_options", {}).get("listings", []))
    product_names = list(analysis.get("filter_options", {}).get("product_names", []))
    sources = list(analysis.get("sources", []))
    profile = resolve_insight_report_profile(sources)
    product_mapping = _product_mapping_check(
        summary,
        listings,
    )
    mapping_trusted = product_mapping.get("status") != "needs_review"
    text_trusted = text_quality.get("status") != "needs_review"
    product_level_trusted = mapping_trusted
    safe_products = products if product_level_trusted else []
    safe_diagnostics = deepcopy(diagnostics)
    safe_issue_cases = deepcopy(issue_cases) if product_level_trusted else []
    if not product_level_trusted:
        safe_diagnostics = [
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
            for diagnostic in diagnostics
        ]
    if not text_trusted:
        safe_diagnostics = [
            _filter_diagnostic_text(diagnostic) for diagnostic in safe_diagnostics
        ]
        safe_issue_cases = [_filter_issue_case_text(case) for case in safe_issue_cases]
    catalog: dict[str, dict[str, Any]] = {
        "scope": {
            "label": "分析范围",
            "value": (
                f"纳入 {int(summary.get('record_count') or 0)} 条，"
                f"待审核 {int(summary.get('pending_review_record_count') or 0)} 条"
            ),
            "data": summary,
        },
        "review_bias": {
            "label": "待审核集中偏差",
            "value": str(review_bias.get("note") or "尚未评估"),
            "data": review_bias,
        },
        "product_mapping": {
            "label": "商品主数据映射",
            "value": str(product_mapping.get("note") or "未发现明显前缀冲突"),
            "data": product_mapping,
        },
        "text_quality": {
            "label": "评论文本质量",
            "value": str(text_quality.get("note") or "尚未评估"),
            "data": text_quality,
        },
        "report_profile": {
            "label": "报告品类配置",
            "value": f"{profile.category_name} · {profile.version}",
            "data": profile.snapshot(),
        },
    }
    for index, group in enumerate(groups, 1):
        catalog[f"group.{index}"] = {
            "label": str(group.get("value") or "其他原因"),
            "value": (
                f"{int(group.get('record_count') or 0)} 条 · "
                f"{float(group.get('percentage') or 0):.1f}%"
            ),
            "data": group,
        }
    for reason in reasons:
        code = str(reason.get("value") or "unknown")
        catalog[f"reason.{code}"] = {
            "label": str(reason.get("label") or code),
            "value": (
                f"{int(reason.get('record_count') or 0)} 条 · "
                f"{float(reason.get('percentage') or 0):.1f}%"
            ),
            "data": reason,
        }
    for subject in subjects:
        code = str(subject.get("value") or "unknown")
        catalog[f"subject.{code}"] = {
            "label": str(subject.get("label") or code),
            "value": (
                f"{int(subject.get('record_count') or 0)} 条 · "
                f"{float(subject.get('percentage') or 0):.1f}%"
            ),
            "data": subject,
        }
    for index, product in enumerate(safe_products, 1):
        catalog[f"product.{index}"] = {
            "label": str(product.get("value") or f"商品 {index}"),
            "value": f"{int(product.get('total_record_count') or 0)} 条已分析退货",
            "data": product,
        }
    for case in safe_issue_cases:
        case_id = str(case.get("id") or "")
        if not case_id:
            continue
        catalog[case_id] = {
            "label": (
                f"{case.get('label') or case.get('reason_code')} · "
                f"{case.get('product_sku') or '未提供 SKU'}"
            ),
            "value": (
                f"{int(case.get('record_count') or 0)} / "
                f"{int(case.get('total_record_count') or 0)} 条，"
                f"变体内 {float(case.get('issue_rate') or 0):.1f}%，"
                f"整体 {float(case.get('overall_rate') or 0):.1f}%，"
                f"{float(case.get('lift') or 0):.2f}×"
            ),
            "data": case,
        }
        if case.get("trend"):
            catalog[f"{case_id}.trend"] = {
                "label": f"{case.get('product_sku') or '商品变体'}问题趋势",
                "value": f"{len(case.get('trend', []))} 个周度数据点",
                "data": case.get("trend", []),
            }
        for index, opinion in enumerate(
            case.get("semantic_profile", {}).get("opinions", []),
            1,
        ):
            catalog[f"{case_id}.opinion.{index}"] = {
                "label": str(opinion.get("opinion") or f"高频表述 {index}"),
                "value": f"{int(opinion.get('record_count') or 0)} 条",
                "data": opinion,
            }
        for index, sample in enumerate(case.get("samples", []), 1):
            text = str(sample.get("comment") or sample.get("reason") or "").strip()
            catalog[f"{case_id}.sample.{index}"] = {
                "label": str(case.get("product_sku") or "原始评论"),
                "value": text[:160] or "未提供评论",
                "data": sample,
            }
    samples = []
    seen_samples: set[str] = set()
    for diagnostic in safe_diagnostics:
        code = str(diagnostic.get("reason_code") or "unknown")
        trend_summary = diagnostic.get("trend_summary", {})
        if trend_summary.get("status") == "available":
            catalog[f"diagnostic.{code}.trend"] = {
                "label": f"{diagnostic.get('selected_reason', {}).get('label') or code}趋势",
                "value": (
                    f"最早 {trend_summary.get('window_weeks')} 个完整周 "
                    f"{float(trend_summary.get('early_rate') or 0):.1f}% → "
                    f"最近 {trend_summary.get('window_weeks')} 个完整周 "
                    f"{float(trend_summary.get('recent_rate') or 0):.1f}%（"
                    f"{float(trend_summary.get('delta_percentage_points') or 0):+.1f}pp）"
                ),
                "data": trend_summary,
            }
        for index, hotspot in enumerate(diagnostic.get("hotspots", []), 1):
            catalog[f"diagnostic.{code}.hotspot.{index}"] = {
                "label": str(hotspot.get("value") or f"商品 {index}"),
                "value": (
                    f"{int(hotspot.get('record_count') or 0)} / "
                    f"{int(hotspot.get('total_record_count') or 0)} 条，"
                    f"商品内 {float(hotspot.get('product_reason_rate') or 0):.1f}%，"
                    f"整体 {float(hotspot.get('overall_reason_rate') or 0):.1f}%，"
                    f"{float(hotspot.get('lift') or 0):.2f}×"
                ),
                "data": hotspot,
            }
        for index, variant in enumerate(diagnostic.get("variants", []), 1):
            catalog[f"diagnostic.{code}.variant.{index}"] = {
                "label": str(variant.get("value") or f"商品变体 {index}"),
                "value": (
                    f"{int(variant.get('record_count') or 0)} / "
                    f"{int(variant.get('total_record_count') or 0)} 条，"
                    f"变体内 {float(variant.get('product_reason_rate') or 0):.1f}%，"
                    f"整体 {float(variant.get('overall_reason_rate') or 0):.1f}%，"
                    f"{float(variant.get('lift') or 0):.2f}×"
                ),
                "data": variant,
            }
        opinions = diagnostic.get("semantic_profile", {}).get("opinions", [])
        for index, opinion in enumerate(opinions, 1):
            catalog[f"diagnostic.{code}.opinion.{index}"] = {
                "label": str(opinion.get("opinion") or f"高频表述 {index}"),
                "value": f"{int(opinion.get('record_count') or 0)} 条",
                "data": opinion,
            }
        for index, sample in enumerate(diagnostic.get("samples", []), 1):
            text = str(sample.get("comment") or sample.get("reason") or "").strip()
            sample_id = f"diagnostic.{code}.sample.{index}"
            catalog[sample_id] = {
                "label": str(sample.get("product_name") or "原始评论"),
                "value": text[:160] or "未提供评论",
                "data": sample,
            }
            if text and text not in seen_samples and len(samples) < 8:
                samples.append(
                    {**sample, "reason_code": code, "evidence_id": sample_id}
                )
                seen_samples.add(text)
    business_issues = _build_business_issues(
        safe_diagnostics,
        safe_issue_cases,
        profile=profile,
    )
    for issue in business_issues:
        catalog[issue["id"]] = {
            "label": str(issue.get("label") or "业务问题"),
            "value": (
                f"{int(issue.get('record_count') or 0)} 条 · "
                f"{float(issue.get('percentage') or 0):.1f}%"
            ),
            "data": issue,
        }
    total_record_count = int(
        summary.get("total_record_count") or summary.get("record_count") or 0
    )
    pending_review_count = int(summary.get("pending_review_record_count") or 0)
    coverage_rate = float(
        summary.get("coverage_rate")
        if summary.get("coverage_rate") is not None
        else (100 if total_record_count else 0)
    )
    checked_comment_count = int(text_quality.get("checked_record_count") or 0)
    anomaly_comment_count = int(text_quality.get("anomaly_record_count") or 0)
    clean_comment_count = max(
        checked_comment_count - anomaly_comment_count,
        0,
    )
    clean_comment_rate = (
        round(
            clean_comment_count / checked_comment_count * 100,
            1,
        )
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
    evidence = {
        "source": {
            "dashboard_id": analysis.get("dashboard_id"),
            "dashboard_version_id": analysis.get("version_id"),
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
                    str(
                        source.get("taxonomy_version")
                        or source.get("taxonomy_version_id")
                    )
                    for source in sources
                    if source.get("taxonomy_version")
                    or source.get("taxonomy_version_id")
                }
            ),
            "report_profile": profile.snapshot(),
        },
        "catalog": catalog,
        "analysis": {
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
        },
    }
    evidence["blueprint"] = (
        _build_decision_blueprint(evidence)
        if prompt_version == PROMPT_VERSION
        else _build_blueprint(evidence)
    )
    return evidence
