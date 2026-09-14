from __future__ import annotations

from typing import Any

from web_backend.insight_report_profiles import get_insight_report_profile


def _build_blueprint(evidence: dict[str, Any]) -> dict[str, Any]:
    source = evidence["source"]
    analysis = evidence["analysis"]
    profile = get_insight_report_profile(source.get("report_profile", {}).get("key"))
    reasons = list(analysis.get("reasons", []))
    groups = list(analysis.get("label_group_breakdown", []))
    diagnostics = {
        str(item.get("reason_code")): item
        for item in analysis.get("diagnostics", [])
        if item.get("reason_code")
    }
    business_issues = list(analysis.get("business_issues", []))
    primary_issues = [
        issue for issue in business_issues if issue.get("role") == "primary"
    ]
    issues_by_code = {
        str(issue.get("reason_code") or ""): issue
        for issue in business_issues
        if issue.get("reason_code")
    }
    listings = list(source.get("listings", []))
    scope_name = (
        str(listings[0])
        if len(listings) == 1
        else f"{len(listings)} 个 Listing"
        if listings
        else "当前范围"
    )
    provisional = source.get("report_status") == "provisional"
    included = int(source.get("included_record_count") or 0)
    total = int(source.get("total_record_count") or included)
    pending = int(source.get("pending_review_record_count") or 0)
    coverage = float(source.get("coverage_rate") or 0)
    review_bias = analysis.get("review_bias", {})
    bias_note = str(review_bias.get("note") or "")
    product_mapping = source.get("product_mapping", {})
    mapping_trusted = product_mapping.get("status") != "needs_review"
    text_quality = source.get("text_quality", {})
    text_trusted = text_quality.get("status") != "needs_review"
    product_level_trusted = mapping_trusted
    scope_statement = (
        f"报告纳入 {included} / {total} 条记录，覆盖率 {coverage:.1f}%；"
        f"另有 {pending} 条待审核记录未进入本次统计。{bias_note}"
        if pending
        else f"报告纳入 {included} 条记录，当前范围内无待审核记录。"
    )
    generic_actionable_reasons = [
        reason
        for reason in reasons
        if "PRODUCT" in reason.get("subjects", [])
        and str(reason.get("label_group") or "") != "其他原因"
    ]
    reason_by_code = {
        str(reason.get("value") or ""): reason for reason in generic_actionable_reasons
    }
    actionable_reasons = [
        reason_by_code[code]
        for code in profile.preferred_reason_codes
        if code in reason_by_code
    ]
    for reason in generic_actionable_reasons:
        if reason not in actionable_reasons:
            actionable_reasons.append(reason)
        if len(actionable_reasons) >= 3:
            break
    actionable_reasons = actionable_reasons[:3]
    broad_reason = next(
        (
            reason
            for reason in reasons
            if len(reason.get("subjects", [])) > 1
            or str(reason.get("label_group") or "") == "其他原因"
        ),
        None,
    )
    primary_group = next(
        (group for group in groups if str(group.get("value")) != "其他原因"),
        groups[0] if groups else None,
    )
    group_evidence_id = "scope"
    if primary_group:
        group_evidence_id = next(
            (
                f"group.{index}"
                for index, group in enumerate(groups, 1)
                if group.get("value") == primary_group.get("value")
            ),
            "scope",
        )
    reason_evidence_ids = [
        f"reason.{reason.get('value') or 'unknown'}" for reason in actionable_reasons
    ]
    structure_statement = (
        f"{primary_group.get('value')}覆盖 "
        f"{int(primary_group.get('record_count') or 0)} 条记录，"
        f"占已纳入样本 {float(primary_group.get('percentage') or 0):.1f}%。"
        if primary_group
        else f"当前共纳入 {included} 条可分析退货记录。"
    )
    if actionable_reasons:
        reason_text = "；".join(
            f"{reason.get('label')} {int(reason.get('record_count') or 0)} 条"
            f"（{float(reason.get('percentage') or 0):.1f}%）"
            for reason in actionable_reasons
        )
        structure_statement = f"{structure_statement.rstrip('。')}；其中{reason_text}。"
    business_headlines = []
    business_evidence_ids = []
    for issue in primary_issues[:3]:
        hotspot = next(iter(issue.get("hotspots", [])), None)
        if not hotspot:
            continue
        rate = float(hotspot.get("product_reason_rate") or 0)
        baseline = float(hotspot.get("overall_reason_rate") or 0)
        business_headlines.append(
            f"{issue.get('label')}在{hotspot.get('value')}为{rate:.1f}%，"
            f"比整体基线高{rate - baseline:+.1f}pp"
        )
        business_evidence_ids.append(str(issue.get("id")))
    business_statement = (
        "；".join(business_headlines) + "。"
        if business_headlines
        else structure_statement
    )

    findings = [
        {
            "id": "finding.structure",
            "kind": "structure",
            "title": (
                f"{profile.category_name}问题已经分化到具体{profile.variant_label}"
                if business_headlines
                else f"{primary_group.get('value')}是当前最值得优先处理的商品问题"
                if primary_group
                else "当前问题结构需要先完成业务归类"
            ),
            "conclusion": business_statement,
            "evidence_ids": [
                *business_evidence_ids,
                group_evidence_id,
                *reason_evidence_ids,
                "scope",
            ],
        }
    ]

    diagnostic_ids = []
    trend_sentences = []
    hotspot_sentences = []
    hotspot_targets = []
    for reason in actionable_reasons:
        code = str(reason.get("value") or "")
        issue = issues_by_code.get(code, {})
        issue_case = next(iter(issue.get("cases", [])), None)
        if issue_case:
            case_id = str(issue_case.get("id") or "")
            trend_summary = issue_case.get("trend_summary", {})
            if (
                trend_summary.get("status") == "available"
                and f"{case_id}.trend" in evidence["catalog"]
            ):
                diagnostic_ids.append(f"{case_id}.trend")
                trend_sentences.append(
                    f"{reason.get('label')}在"
                    f"{issue_case.get('product_sku')}最近"
                    f"{trend_summary.get('window_weeks')}个完整周均值为"
                    f"{float(trend_summary.get('recent_rate') or 0):.1f}%，"
                    f"较最早同长度窗口"
                    f"{float(trend_summary.get('delta_percentage_points') or 0):+.1f}pp"
                )
            diagnostic_ids.append(case_id)
            hotspot_targets.append(str(issue_case.get("product_sku") or ""))
            hotspot_sentences.append(
                f"{reason.get('label')}集中在"
                f"{issue_case.get('product_sku')}："
                f"{int(issue_case.get('record_count') or 0)} / "
                f"{int(issue_case.get('total_record_count') or 0)}条，"
                f"变体内占比"
                f"{float(issue_case.get('product_reason_rate') or 0):.1f}%，"
                f"整体基线"
                f"{float(issue_case.get('overall_reason_rate') or 0):.1f}%，"
                f"为基线的{float(issue_case.get('lift') or 0):.2f}倍，"
                f"超出按整体基线预期约"
                f"{int(issue_case.get('excess_record_count') or 0)}条"
            )
            continue
        diagnostic = diagnostics.get(code, {})
        trend_summary = diagnostic.get("trend_summary", {})
        trend_id = f"diagnostic.{code}.trend"
        if trend_id in evidence["catalog"]:
            diagnostic_ids.append(trend_id)
            trend_sentences.append(
                f"{reason.get('label')}最近"
                f"{trend_summary.get('window_weeks')}个完整周均值为"
                f"{float(trend_summary.get('recent_rate') or 0):.1f}%，"
                f"较最早同长度窗口"
                f"{float(trend_summary.get('delta_percentage_points') or 0):+.1f}pp"
            )
        diagnostic_dimension = "variants" if diagnostic.get("variants") else "hotspots"
        hotspot = next(iter(diagnostic.get(diagnostic_dimension, [])), None)
        evidence_dimension = (
            "variant" if diagnostic_dimension == "variants" else "hotspot"
        )
        hotspot_id = f"diagnostic.{code}.{evidence_dimension}.1"
        if hotspot and hotspot_id in evidence["catalog"]:
            diagnostic_ids.append(hotspot_id)
            hotspot_targets.append(str(hotspot.get("value") or ""))
            hotspot_sentences.append(
                f"{reason.get('label')}在{hotspot.get('value')}达到"
                f"{float(hotspot.get('product_reason_rate') or 0):.1f}%，"
                f"为整体基线的{float(hotspot.get('lift') or 0):.2f}倍"
            )
    hotspot_targets = list(
        dict.fromkeys(target for target in hotspot_targets if target)
    )
    if actionable_reasons:
        diagnostic_conclusion = "；".join(trend_sentences + hotspot_sentences)
        if not diagnostic_conclusion:
            diagnostic_conclusion = profile.diagnostic_empty
        findings.append(
            {
                "id": "finding.diagnostic",
                "kind": "diagnostic",
                "title": (
                    f"{'、'.join(hotspot_targets[:2])}是当前最需要验证的具体 SKU"
                    if hotspot_targets
                    else profile.diagnostic_title
                ),
                "conclusion": f"{diagnostic_conclusion}。",
                "evidence_ids": [
                    *reason_evidence_ids,
                    *diagnostic_ids,
                ],
            }
        )

    information_ids = []
    if broad_reason:
        broad_code = str(broad_reason.get("value") or "")
        broad_diagnostic = diagnostics.get(broad_code, {})
        semantic = broad_diagnostic.get("semantic_profile", {})
        unspecified = next(
            (
                part
                for part in semantic.get("parts", [])
                if part.get("value") == "UNSPECIFIED"
            ),
            None,
        )
        top_opinion = next(iter(semantic.get("opinions", [])), None)
        broad_reason_id = f"reason.{broad_code}"
        information_ids.append(broad_reason_id)
        details = []
        if unspecified:
            details.append(
                f"{float(unspecified.get('percentage') or 0):.1f}%未明确商品部位"
            )
        if top_opinion:
            opinion_id = f"diagnostic.{broad_code}.opinion.1"
            information_ids.append(opinion_id)
            details.append(
                f"最高频语义为“{top_opinion.get('opinion')}”"
                f"（{int(top_opinion.get('record_count') or 0)}条）"
            )
        information_conclusion = (
            f"{broad_reason.get('label')}涉及"
            f"{int(broad_reason.get('record_count') or 0)}条记录，"
            f"占{float(broad_reason.get('percentage') or 0):.1f}%"
        )
        if details:
            information_conclusion += "；" + "；".join(details)
        findings.append(
            {
                "id": "finding.information",
                "kind": "information",
                "title": f"“{broad_reason.get('label')}”需要按意图拆解，而不是当作商品缺陷",
                "conclusion": f"{information_conclusion}。",
                "evidence_ids": [*information_ids, "scope"],
            }
        )

    if len(findings) < 2:
        findings.append(
            {
                "id": "finding.coverage",
                "kind": "information",
                "title": "数据覆盖决定当前结论可用于什么决策",
                "conclusion": scope_statement,
                "evidence_ids": ["scope", "review_bias"],
            }
        )

    actions = []
    if not text_trusted:
        actions.append(
            {
                "id": "action.text_quality",
                "priority": "P0",
                "target": "退货评论源数据",
                "finding_id": "finding.structure",
                "evidence_ids": ["text_quality", "scope"],
                "fallback_action": "重新导出并导入未发生乱码的原始退货数据，再重新生成分类结果。",
                "fallback_rationale": "评论文本已经出现编码异常，语义分类和原始证据均可能失真。",
                "fallback_success_signal": "重新导入后不再检测到中英文异常混排，抽样评论与源文件一致。",
            }
        )
    if not mapping_trusted:
        actions.append(
            {
                "id": "action.mapping",
                "priority": "P0",
                "target": f"Listing {product_mapping.get('listing')} 的商品主数据映射",
                "finding_id": "finding.structure",
                "evidence_ids": ["product_mapping", "scope"],
                "fallback_action": "核对源 SKU、商品 SKU 与商品名称的对应关系后再下发商品级整改。",
                "fallback_rationale": "存在未匹配或缺少名称的商品记录，当前不能确认商品级热点对应的真实对象。",
                "fallback_success_signal": "源 SKU、商品 SKU 与商品名称形成唯一且可追溯的映射。",
            }
        )
    if actionable_reasons and product_level_trusted:
        validation_issues = [issue for issue in primary_issues if issue.get("cases")][
            :3
        ]
        validation_cases = [issue["cases"][0] for issue in validation_issues]
        target = (
            "、".join(
                dict.fromkeys(
                    str(case.get("product_sku") or "")
                    for case in validation_cases
                    if case.get("product_sku")
                )
            )
            or "、".join(hotspot_targets[:2])
            or f"高频{profile.variant_label}"
        )
        case_actions = [
            str(issue.get("validation_focus") or "")
            for issue in validation_issues
            if issue.get("validation_focus")
        ]
        case_rationales = [
            (
                f"{case.get('product_sku')}的{case.get('label')}为"
                f"{float(case.get('product_reason_rate') or 0):.1f}%"
                f"（整体{float(case.get('overall_reason_rate') or 0):.1f}%，"
                f"{float(case.get('lift') or 0):.2f}倍）"
            )
            for case in validation_cases
        ]
        action_evidence_ids = list(
            dict.fromkeys(
                [
                    *reason_evidence_ids,
                    *diagnostic_ids,
                    *(
                        str(case.get("id"))
                        for case in validation_cases
                        if case.get("id")
                    ),
                ]
            )
        )
        actions.append(
            {
                "id": "action.diagnostic",
                "priority": "P0",
                "target": target,
                "finding_id": "finding.diagnostic",
                "evidence_ids": action_evidence_ids,
                "fallback_action": (
                    "；".join(case_actions)
                    if case_actions
                    else profile.diagnostic_action
                ),
                "fallback_rationale": (
                    "；".join(case_rationales)
                    + "。这些集中信号值得优先验证，但不能单凭评论结构推断原因。"
                    if case_rationales
                    else profile.diagnostic_rationale
                ),
                "fallback_success_signal": (
                    "每个目标 SKU 都形成可复核的原因结论；后续同口径评论中，"
                    "对应问题连续两个完整周期下降，且反向问题不升高。"
                    if validation_cases
                    else profile.diagnostic_success_signal
                ),
            }
        )
    if broad_reason:
        actions.append(
            {
                "id": "action.information",
                "priority": "P1",
                "target": f"{broad_reason.get('label')}相关记录",
                "finding_id": "finding.information",
                "evidence_ids": information_ids,
                "fallback_action": "按评论表达的具体意图、对象和使用场景拆分宽泛原因。",
                "fallback_rationale": "宽泛标签混合多种退货情境，不能直接转化为单一商品整改。",
                "fallback_success_signal": "宽泛原因被稳定拆分为可解释子类，且未明确对象占比下降。",
            }
        )
    actions.append(
        {
            "id": "action.scope",
            "priority": "P2",
            "target": "待审核记录与商品销量分母",
            "finding_id": "finding.structure",
            "evidence_ids": ["scope", "review_bias"],
            "fallback_action": "持续处理待审核记录，并补充商品销量或订单量分母。",
            "fallback_rationale": "退货记录占比只能描述问题结构，不能代替真实退货率。",
            "fallback_success_signal": "待审核占比下降并形成商品级真实退货率基线。",
        }
    )
    action_order = {
        "action.mapping": 0,
        "action.diagnostic": 1,
        "action.text_quality": 2,
        "action.information": 3,
        "action.scope": 4,
    }
    actions.sort(key=lambda item: action_order.get(str(item.get("id")), 99))
    caveats = [
        "本报告只描述所选分类结果版本中的退货问题结构，不代表真实退货率。",
        "当前缺少销量、订单量、成本和批次等分母数据，不能据此推断因果。",
    ]
    if provisional:
        caveats.insert(
            0,
            f"这是临时报告：{pending} 条待审核记录未纳入，结论可能随复核推进而变化。",
        )
        if review_bias.get("status") == "concentrated":
            caveats.insert(1, bias_note)
    if product_mapping.get("status") == "needs_review":
        caveats.append(str(product_mapping.get("note")))
    if not text_trusted:
        caveats.append(str(text_quality.get("note")))

    diagnostic_summary = (
        findings[1]["conclusion"] if len(findings) > 1 else structure_statement
    )
    diagnostic_action = next(
        (action for action in actions if action.get("id") == "action.diagnostic"),
        None,
    )
    validation_target = (
        str(diagnostic_action.get("target") or "")
        if diagnostic_action
        else "、".join(hotspot_targets[:2])
    )
    validation_statement = (
        f"优先验证{validation_target}：{diagnostic_action.get('fallback_action')}"
        if validation_target and diagnostic_action
        else diagnostic_summary
    )
    return {
        "title": f"{scope_name} 退货问题{'临时' if provisional else ''}诊断报告",
        "executive_summary": [
            {
                "id": "summary.1",
                "title": "最明确的问题分化",
                "statement": business_statement,
                "tone": "primary",
                "evidence_ids": [
                    *business_evidence_ids,
                    group_evidence_id,
                    *reason_evidence_ids,
                ],
            },
            {
                "id": "summary.2",
                "title": "优先验证对象",
                "statement": validation_statement,
                "tone": "neutral",
                "evidence_ids": findings[1]["evidence_ids"],
            },
            {
                "id": "summary.3",
                "title": "结论可信边界",
                "statement": scope_statement,
                "tone": "warning" if provisional else "neutral",
                "evidence_ids": ["scope", "review_bias"],
            },
        ],
        "findings": findings,
        "actions": actions,
        "further_questions": list(profile.further_questions),
        "caveats": caveats,
    }
