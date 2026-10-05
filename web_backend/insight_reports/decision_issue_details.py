from __future__ import annotations

import hashlib
from typing import Any


def _report_language(source: dict[str, Any]) -> tuple[str, str, str, str]:
    is_returns = source.get("analysis_context") == "returns"
    return (
        "退货样本" if is_returns else "反馈样本",
        "真实退货率" if is_returns else "总体发生率",
        "退货问题" if is_returns else "用户反馈问题",
        "原始退货评论" if is_returns else "原始用户反馈",
    )


def _issue_scope(
    code: str,
    dimension: str,
    row: dict[str, Any],
) -> tuple[str, str | None, str | None, str]:
    case_id = str(row.get("id") or "")
    value = str(row.get("value") or "").strip()
    product = str(row.get("product_name") or "").strip() or None
    sku = str(row.get("product_sku") or "").strip() or None
    if not case_id and value:
        if dimension == "variant":
            sku = value
        else:
            product = value

    issue_id = case_id
    if not issue_id:
        if not product and not sku:
            issue_id = f"issue.reason.{code}"
        else:
            identity = "\x1f".join([code, dimension, product or "", sku or ""])
            suffix = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
            issue_id = f"issue.{code}.{suffix}"
    return case_id, product, sku, issue_id


def _issue_metrics(
    row: dict[str, Any],
    business_issue: dict[str, Any],
    source: dict[str, Any],
) -> dict[str, Any]:
    matched = int(row.get("record_count") or business_issue.get("record_count") or 0)
    scoped = int(
        row.get("total_record_count") or source.get("included_record_count") or 0
    )
    share_value = (
        row.get("product_reason_rate")
        if row.get("product_reason_rate") is not None
        else row.get("issue_rate")
        if row.get("issue_rate") is not None
        else business_issue.get("percentage") or 0
    )
    share = float(share_value or 0)
    baseline_value = (
        row.get("overall_reason_rate")
        if row.get("overall_reason_rate") is not None
        else row.get("overall_rate")
    )
    baseline = float(baseline_value) if baseline_value is not None else None
    gap = round(share - baseline, 1) if baseline is not None else None
    lift_value = row.get("lift")
    lift = float(lift_value) if lift_value is not None else None
    trend = row.get("trend_summary") or business_issue.get("trend_summary", {})
    trend_available = trend.get("status") == "available"
    recent_change = (
        float(trend.get("delta_percentage_points") or 0) if trend_available else None
    )
    direction = (
        str(trend.get("direction") or "stable") if trend_available else "insufficient"
    )
    if direction not in {"rising", "stable", "falling"}:
        direction = "insufficient"
    return {
        "matched_return_samples": matched,
        "scoped_return_samples": scoped,
        "return_sample_share": round(share, 1),
        "baseline_return_sample_share": (
            round(baseline, 1) if baseline is not None else None
        ),
        "gap_percentage_points": gap,
        "lift": round(lift, 2) if lift is not None else None,
        "recent_change_percentage_points": recent_change,
        "trend_direction": direction,
    }


def _issue_evidence_ids(
    code: str,
    dimension: str,
    index: int,
    case_id: str,
    catalog: dict[str, Any],
) -> list[str]:
    evidence_ids = [f"reason.{code}", "scope"]
    if case_id:
        evidence_ids.insert(1, case_id)
        evidence_ids.extend(
            evidence_id
            for evidence_id in (
                f"{case_id}.trend",
                f"{case_id}.opinion.1",
                f"{case_id}.sample.1",
            )
            if evidence_id in catalog
        )
    else:
        evidence_dimension = "variant" if dimension == "variant" else "hotspot"
        hotspot_id = f"diagnostic.{code}.{evidence_dimension}.{index}"
        for evidence_id in (
            hotspot_id,
            f"diagnostic.{code}.trend",
            f"diagnostic.{code}.opinion.1",
            f"diagnostic.{code}.sample.1",
        ):
            if evidence_id in catalog:
                evidence_ids.append(evidence_id)
    return list(dict.fromkeys(evidence_ids))


def _issue_known_facts(
    business_issue: dict[str, Any],
    metrics: dict[str, Any],
    label: str,
    sample_label: str,
) -> list[str]:
    matched = metrics["matched_return_samples"]
    scoped = metrics["scoped_return_samples"]
    share = metrics["return_sample_share"]
    baseline = metrics["baseline_return_sample_share"]
    gap = metrics["gap_percentage_points"]
    recent_change = metrics["recent_change_percentage_points"]
    known = [
        f"{matched} / {scoped} 条{sample_label}命中“{label}”，"
        f"{sample_label}内占比 {share:.1f}%。"
    ]
    if baseline is not None:
        known.append(
            f"相同范围整体基线为 {baseline:.1f}%，当前高出 {gap:+.1f} 个百分点。"
        )
    if recent_change is not None:
        known.append(f"最近窗口较早期同长度窗口变化 {recent_change:+.1f} 个百分点。")
    top_opinion = next(
        iter(business_issue.get("contexts", {}).get("opinions", [])), None
    )
    if top_opinion:
        known.append(
            f"高频反馈为“{top_opinion.get('opinion')}”，"
            f"覆盖 {int(top_opinion.get('record_count') or 0)} 条记录。"
        )
    return known[:6]


def _issue_readiness(
    source: dict[str, Any],
    row: dict[str, Any],
    product: str | None,
    sku: str | None,
    metrics: dict[str, Any],
) -> dict[str, str]:
    concrete_scope = bool(product or sku)
    reliable = bool(row.get("reliable", concrete_scope))
    if source.get("quality_issue_codes"):
        return {
            "status": "diagnostic_only",
            "label": "仅供诊断",
            "reason": "当前仍有数据质量或待审核问题，需先补齐证据。",
        }
    if (
        not concrete_scope
        or not reliable
        or metrics["matched_return_samples"] < 10
        or metrics["scoped_return_samples"] < 10
    ):
        return {
            "status": "diagnostic_only",
            "label": "仅供诊断",
            "reason": "当前信号尚未形成稳定的商品范围或样本基础。",
        }
    return {
        "status": "verification_ready",
        "label": "可进入验证",
        "reason": "样本量、对照基线和可追溯证据已具备。",
    }
