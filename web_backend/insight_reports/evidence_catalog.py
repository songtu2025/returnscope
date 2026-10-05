from __future__ import annotations

from typing import Any

from web_backend.insight_report_profiles import InsightReportProfile


def _counted_entry(item: dict[str, Any], label: str) -> dict[str, Any]:
    return {
        "label": label,
        "value": (
            f"{int(item.get('record_count') or 0)} 条 · "
            f"{float(item.get('percentage') or 0):.1f}%"
        ),
        "data": item,
    }


def _hotspot_entry(item: dict[str, Any], label: str, rate_label: str) -> dict[str, Any]:
    return {
        "label": label,
        "value": (
            f"{int(item.get('record_count') or 0)} / "
            f"{int(item.get('total_record_count') or 0)} 条，"
            f"{rate_label} {float(item.get('product_reason_rate') or 0):.1f}%，"
            f"整体 {float(item.get('overall_reason_rate') or 0):.1f}%，"
            f"{float(item.get('lift') or 0):.2f}×"
        ),
        "data": item,
    }


def _scope_catalog(
    analysis: dict[str, Any],
    product_mapping: dict[str, Any],
    profile: InsightReportProfile,
) -> dict[str, dict[str, Any]]:
    summary = analysis["summary"]
    review_bias = analysis["review_bias"]
    text_quality = analysis["text_quality"]
    return {
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


def _build_catalog(
    analysis: dict[str, Any],
    product_mapping: dict[str, Any],
    profile: InsightReportProfile,
    *,
    analysis_context: str,
) -> dict[str, dict[str, Any]]:
    catalog = _scope_catalog(analysis, product_mapping, profile)
    _add_breakdown_evidence(catalog, analysis, analysis_context=analysis_context)
    # 证据编号和插入顺序会进入提示词及报告引用，分组顺序必须保持一致。
    for case in analysis["issue_cases"]:
        catalog.update(_issue_case_evidence(case))
    for diagnostic in analysis["diagnostics"]:
        catalog.update(_diagnostic_evidence(diagnostic))
    for issue in analysis["business_issues"]:
        catalog[issue["id"]] = _counted_entry(
            issue, str(issue.get("label") or "业务问题")
        )
    return catalog


def _add_breakdown_evidence(
    catalog: dict[str, dict[str, Any]],
    analysis: dict[str, Any],
    *,
    analysis_context: str,
) -> None:
    groups = analysis["label_group_breakdown"]
    reasons = analysis["reasons"]
    subjects = analysis["subject_breakdown"]
    safe_products = analysis["product_reason_matrix"]
    analyzed_record_label = (
        "已分析退货" if analysis_context == "returns" else "已分析反馈"
    )
    for index, group in enumerate(groups, 1):
        catalog[f"group.{index}"] = _counted_entry(
            group, str(group.get("value") or "其他原因")
        )
    for reason in reasons:
        code = str(reason.get("value") or "unknown")
        catalog[f"reason.{code}"] = _counted_entry(
            reason, str(reason.get("label") or code)
        )
    for subject in subjects:
        code = str(subject.get("value") or "unknown")
        catalog[f"subject.{code}"] = _counted_entry(
            subject, str(subject.get("label") or code)
        )
    for index, product in enumerate(safe_products, 1):
        catalog[f"product.{index}"] = {
            "label": str(product.get("value") or f"商品 {index}"),
            "value": f"{int(product.get('total_record_count') or 0)} 条{analyzed_record_label}",
            "data": product,
        }


def _issue_case_evidence(case: dict[str, Any]) -> dict[str, dict[str, Any]]:
    case_id = str(case.get("id") or "")
    if not case_id:
        return {}
    catalog: dict[str, dict[str, Any]] = {}
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
        case.get("semantic_profile", {}).get("opinions", []), 1
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
    return catalog


def _diagnostic_evidence(diagnostic: dict[str, Any]) -> dict[str, dict[str, Any]]:
    catalog: dict[str, dict[str, Any]] = {}
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
        catalog[f"diagnostic.{code}.hotspot.{index}"] = _hotspot_entry(
            hotspot, str(hotspot.get("value") or f"商品 {index}"), "商品内"
        )
    for index, variant in enumerate(diagnostic.get("variants", []), 1):
        catalog[f"diagnostic.{code}.variant.{index}"] = _hotspot_entry(
            variant, str(variant.get("value") or f"商品变体 {index}"), "变体内"
        )
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
    return catalog
