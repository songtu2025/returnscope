from __future__ import annotations

import hashlib
from typing import Any

from web_backend.insight_report_profiles import get_insight_report_profile


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


def _build_issue_candidate(
    source: dict[str, Any],
    catalog: dict[str, Any],
    business_issue: dict[str, Any],
    row: dict[str, Any],
    index: int,
) -> dict[str, Any]:
    code = str(business_issue.get("reason_code") or "")
    dimension = str(business_issue.get("hotspot_dimension") or "product")
    profile = get_insight_report_profile(source.get("report_profile", {}).get("key"))
    listings = list(source.get("listings", []))
    listing = str(listings[0]) if len(listings) == 1 else None
    category = profile.category_name if profile.key != "generic" else None
    sample_label, rate_label, _, original_feedback = _report_language(source)
    case_id, product, sku, issue_id = _issue_scope(code, dimension, row)
    metrics = _issue_metrics(row, business_issue, source)
    lift_value = row.get("lift")
    rank_lift = float(lift_value) if lift_value is not None else 0.0
    label = str(business_issue.get("label") or code)
    target = sku or product
    title = f"{target} · {label}" if target else label
    questions = list(profile.further_questions)[:3]
    if target:
        questions.insert(0, f"{target} 的该问题是否在相同条件下重复出现？")
    return {
        "id": issue_id,
        "rank_key": (
            0 if business_issue.get("role") == "primary" else 1,
            -int(row.get("excess_record_count") or 0),
            -rank_lift,
            -metrics["matched_return_samples"],
            title,
        ),
        "title": title,
        "scope": {
            "category": category,
            "listing": listing,
            "product": product,
            "sku": sku,
        },
        "metrics": metrics,
        "known": _issue_known_facts(business_issue, metrics, label, sample_label),
        "fallback_evidence_explanation": (
            f"该信号在当前{sample_label}中形成集中分化，"
            f"但仅凭反馈与样本结构不能判断{rate_label}或因果。"
        ),
        "fallback_unknown": list(dict.fromkeys(questions))[:5],
        "fallback_recommendation": {
            "label": "建议验证",
            "validation_question": f"是否需要进一步验证 {target or label} 的{label}风险？",
            "rationale": (
                "当前证据足以定位问题范围，但仍需结合实物、"
                "页面信息或业务分母验证原因与影响。"
            ),
            "suggested_evidence": [
                f"复核命中的{original_feedback}",
                "核对相同范围的商品信息与实物表现",
                "补充订单量或销量分母",
            ],
        },
        "readiness": _issue_readiness(source, row, product, sku, metrics),
        "evidence_ids": _issue_evidence_ids(code, dimension, index, case_id, catalog),
    }


def _build_decision_blueprint(evidence: dict[str, Any]) -> dict[str, Any]:
    source = evidence["source"]
    analysis = evidence["analysis"]
    catalog = evidence["catalog"]
    profile = get_insight_report_profile(source.get("report_profile", {}).get("key"))
    listings = list(source.get("listings", []))
    listing = str(listings[0]) if len(listings) == 1 else None
    category = profile.category_name if profile.key != "generic" else None
    sample_label, rate_label, report_subject, _ = _report_language(source)
    candidates: list[dict[str, Any]] = []
    for business_issue in analysis.get("business_issues", []):
        if not business_issue.get("reason_code"):
            continue
        rows = list(business_issue.get("cases", []))
        if not rows:
            rows = list(business_issue.get("hotspots", []))
        if not rows:
            rows = [None]
        for index, row in enumerate(rows[:2], 1):
            candidates.append(
                _build_issue_candidate(
                    source, catalog, business_issue, row or {}, index
                )
            )

    if not candidates:
        candidates.append(
            {
                "id": "issue.scope.coverage",
                "rank_key": (1, 0, 0, 0, "数据覆盖"),
                "title": "当前范围尚未形成可定位的问题信号",
                "scope": {
                    "category": category,
                    "listing": listing,
                    "product": None,
                    "sku": None,
                },
                "metrics": {
                    "matched_return_samples": 0,
                    "scoped_return_samples": int(
                        source.get("included_record_count") or 0
                    ),
                    "return_sample_share": 0.0,
                    "baseline_return_sample_share": None,
                    "gap_percentage_points": None,
                    "lift": None,
                    "recent_change_percentage_points": None,
                    "trend_direction": "insufficient",
                },
                "known": ["当前已分析范围内没有形成可定位到具体问题的稳定信号。"],
                "fallback_evidence_explanation": "现有数据只能说明覆盖范围，不能支持具体问题判断。",
                "fallback_unknown": list(profile.further_questions)[:5]
                or ["是否需要补充更完整的分类与商品信息？"],
                "fallback_recommendation": {
                    "label": "建议验证",
                    "validation_question": "是否需要先补充分类与商品证据？",
                    "rationale": "当前缺少可定位的问题信号。",
                    "suggested_evidence": ["补充已审核分类结果"],
                },
                "readiness": {
                    "status": "diagnostic_only",
                    "label": "仅供诊断",
                    "reason": "当前证据不足以定位具体问题。",
                },
                "evidence_ids": ["scope"],
            }
        )

    issues: list[dict[str, Any]] = []
    for rank, candidate in enumerate(
        sorted(candidates, key=lambda item: item["rank_key"])[:8],
        1,
    ):
        issue = {key: value for key, value in candidate.items() if key != "rank_key"}
        issue["rank"] = rank
        issues.append(issue)

    scope_name = (
        listing
        if listing
        else f"{len(listings)} 个 Listing"
        if listings
        else "当前范围"
    )
    caveats = [
        f"所有占比均为{sample_label}内占比，不代表{rate_label}。",
        "当前缺少订单量、销量、成本和批次等分母，不能据此推断因果。",
    ]
    if source.get("pending_review_record_count"):
        caveats.append("待审核记录未进入本次统计，结论可能随复核推进而变化。")
    return {
        "report_type": "problem_decision",
        "title": f"{scope_name} {report_subject}判断报告",
        "issues": issues,
        "caveats": caveats,
    }
