from __future__ import annotations

from copy import deepcopy
from typing import Any

from web_backend.insight_report_consistency import _report_consistency
from web_backend.insight_report_contracts import ReportQualityGate
from web_backend.insight_report_diagnostics import (
    _filter_business_issue_text,
    _filter_diagnostic_text,
    _filter_issue_case_text,
    _has_text_anomaly,
)


def _evaluate_live_quality(
    content: dict[str, Any],
    evidence: dict[str, Any],
    text_quality: dict[str, Any],
) -> dict[str, Any]:
    safe_content = deepcopy(content)
    safe_evidence = deepcopy(evidence)
    source = safe_evidence.setdefault("source", {})
    analysis = safe_evidence.setdefault("analysis", {})
    catalog = safe_evidence.setdefault("catalog", {})
    consistency = _report_consistency(
        safe_content,
        safe_evidence,
        require_information_diagnostics=True,
    )
    product_mapping = source.get("product_mapping", {})
    text_trusted = text_quality.get("status") != "needs_review"
    mapping_trusted = product_mapping.get("status") != "needs_review"
    product_level_trusted = mapping_trusted
    pending_count = int(source.get("pending_review_record_count") or 0)
    review_bias = analysis.get("review_bias", {})
    source_issues: list[dict[str, Any]] = []
    if not text_trusted:
        source_issues.append(
            {
                "code": "text_quality",
                "label": "评论文本质量未通过",
                "detail": str(text_quality.get("note") or "评论文本质量需要核对。"),
                "evidence_ids": ["text_quality", "scope"],
            }
        )
    if not mapping_trusted:
        source_issues.append(
            {
                "code": "product_mapping",
                "label": "商品主数据需核对",
                "detail": str(
                    product_mapping.get("note") or "商品主数据映射需要核对。"
                ),
                "evidence_ids": ["product_mapping", "scope"],
            }
        )
    if pending_count:
        source_issues.append(
            {
                "code": "pending_review",
                "label": "存在待审核记录",
                "detail": str(
                    review_bias.get("note")
                    or f"{pending_count} 条待审核记录未进入本次统计。"
                ),
                "evidence_ids": ["scope", "review_bias"],
            }
        )
    product_names = [
        str(item.get("value") or "")
        for item in analysis.get("product_reason_matrix", [])
        if item.get("value")
    ]

    source["text_quality"] = text_quality
    source["quality_issue_codes"] = [item["code"] for item in source_issues]
    source["report_status"] = "provisional" if source_issues else "final"
    analysis["text_quality"] = text_quality
    catalog["text_quality"] = {
        "label": "评论文本质量",
        "value": str(text_quality.get("note") or "未发现明显编码异常"),
        "data": text_quality,
    }

    if not product_level_trusted:
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
    if not text_trusted:
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
            if not _has_text_anomaly(
                sample.get("comment"),
                sample.get("reason"),
            )
        ]

    blocked_catalog_markers = []
    if not product_level_trusted:
        blocked_catalog_markers.extend(
            [
                ".hotspot.",
                ".variant.",
                "business_issue.",
                "issue_case.",
            ]
        )
    for evidence_id in list(catalog):
        if any(marker in evidence_id for marker in blocked_catalog_markers):
            catalog.pop(evidence_id, None)
            continue
        if not text_trusted and any(
            marker in evidence_id for marker in (".sample.", ".opinion.")
        ):
            data = catalog[evidence_id].get("data", {})
            if _has_text_anomaly(
                data.get("opinion"),
                data.get("evidence"),
                data.get("comment"),
                data.get("reason"),
            ):
                catalog.pop(evidence_id, None)
        elif not text_trusted and evidence_id.startswith("business_issue."):
            catalog[evidence_id]["data"] = _filter_business_issue_text(
                catalog[evidence_id].get("data", {})
            )

    if not product_level_trusted:
        safe_content["findings"] = [
            finding
            for finding in safe_content.get("findings", [])
            if finding.get("kind") != "diagnostic"
        ]

    summaries = []
    for summary in safe_content.get("executive_summary", []):
        summary_text = f"{summary.get('title', '')} {summary.get('statement', '')}"
        references = summary.get("evidence_ids", [])
        if not product_level_trusted and (
            any(name in summary_text for name in product_names)
            or any(
                marker in item
                for item in references
                for marker in (
                    ".hotspot.",
                    ".variant.",
                    "business_issue.",
                    "issue_case.",
                )
            )
        ):
            continue
        if not text_trusted and any(
            marker in item
            for item in references
            for marker in (".sample.", ".opinion.")
        ):
            continue
        summaries.append(summary)

    quality_issues = list(source_issues)
    if consistency["status"] == "blocked":
        quality_issues.insert(
            0,
            {
                "code": "report_consistency",
                "label": "报告内部数据不一致",
                "detail": "；".join(consistency["issues"][:3]),
                "evidence_ids": [],
            },
        )
        summaries = []
    gate_summary = None
    if quality_issues:
        issue_labels = "、".join(item["label"] for item in quality_issues)
        evidence_ids = list(
            dict.fromkeys(
                evidence_id
                for item in quality_issues
                for evidence_id in item["evidence_ids"]
            )
        )
        gate_summary = {
            "id": "summary.quality_gate",
            "title": (
                "当前报告不可使用"
                if consistency["status"] == "blocked"
                else "当前结论仅供诊断"
            ),
            "statement": (
                f"{issue_labels}。"
                + (
                    "请重新生成报告后再使用。"
                    if consistency["status"] == "blocked"
                    else "问题修复前，不应直接下发商品整改。"
                )
            ),
            "tone": "warning",
            "evidence_ids": evidence_ids or ["scope"],
        }
    summary_candidates = [gate_summary, *summaries] if gate_summary else summaries
    unique_summaries = []
    seen_summaries = set()
    for summary in summary_candidates:
        key = (summary.get("title"), summary.get("statement"))
        if key in seen_summaries:
            continue
        seen_summaries.add(key)
        unique_summaries.append(summary)
    safe_content["executive_summary"] = unique_summaries[:4]

    actions = [
        action
        for action in safe_content.get("actions", [])
        if action.get("id") != "action.diagnostic" or product_level_trusted
    ]
    gate_actions = []
    if not text_trusted:
        gate_actions.append(
            {
                "id": "action.text_quality",
                "priority": "P0",
                "target": "退货评论源数据",
                "action": (
                    "重新导出并导入未发生乱码的原始退货数据，"
                    "再重新生成分类结果和 AI 洞察报告。"
                ),
                "rationale": (
                    "评论文本检测到中英文异常混排，语义分类和原始证据可能失真。"
                ),
                "success_signal": (
                    "重新导入后不再检测到异常混排，抽样评论与源文件一致。"
                ),
                "evidence_ids": ["text_quality", "scope"],
            }
        )
    if not mapping_trusted:
        actions = [action for action in actions if action.get("id") != "action.mapping"]
        gate_actions.append(
            {
                "id": "action.mapping",
                "priority": "P0",
                "target": "商品主数据映射",
                "action": (
                    "核对源 SKU、商品 SKU 与商品名称的对应关系后，再下发商品级整改。"
                ),
                "rationale": (
                    "存在未匹配或缺少名称的商品记录，"
                    "当前不能确认商品级热点对应的真实对象。"
                ),
                "success_signal": (
                    "源 SKU、商品 SKU 与商品名称形成唯一且可追溯的映射。"
                ),
                "evidence_ids": ["product_mapping", "scope"],
            }
        )
    actions = [
        action
        for action in actions
        if action.get("id") not in {item["id"] for item in gate_actions}
    ]
    action_candidates = (
        []
        if consistency["status"] == "blocked"
        else [
            *gate_actions,
            *actions,
        ]
    )
    unique_actions = []
    seen_action_ids = set()
    for action in action_candidates:
        action_id = action.get("id")
        if action_id in seen_action_ids:
            continue
        seen_action_ids.add(action_id)
        unique_actions.append(action)
    action_order = {
        "action.mapping": 0,
        "action.diagnostic": 1,
        "action.text_quality": 2,
        "action.information": 3,
        "action.scope": 4,
    }
    unique_actions.sort(key=lambda action: action_order.get(action.get("id"), 99))
    safe_content["actions"] = unique_actions[:6]

    warnings = []
    if not text_trusted:
        warnings.append(
            "评论文本质量未通过门禁：在重新导入干净源数据前，"
            "本报告只可用于定位数据问题，不可下发商品整改。"
        )
    if not mapping_trusted:
        warnings.append(str(product_mapping.get("note") or "商品主数据需核对。"))
    if pending_count:
        warnings.append(str(review_bias.get("note") or source_issues[-1]["detail"]))
    caveats = [*warnings, *safe_content.get("caveats", [])]
    safe_content["caveats"] = list(dict.fromkeys(caveats))
    if consistency["status"] == "blocked":
        decision_readiness = {
            "status": "unusable",
            "label": "不可使用",
            "reason": "报告内部数据不一致，请重新生成报告。",
        }
    elif source_issues:
        decision_readiness = {
            "status": "diagnostic_only",
            "label": "仅供诊断",
            "reason": (
                f"当前存在{'、'.join(item['label'] for item in source_issues)}，"
                "不应直接下发商品整改。"
            ),
        }
    else:
        decision_readiness = {
            "status": "actionable",
            "label": "可行动",
            "reason": "数据质量与报告一致性校验均已通过。",
        }

    if consistency["status"] == "blocked":
        gate_status = "blocked"
    elif source_issues:
        gate_status = "warning"
    else:
        gate_status = "passed"
    quality_gate = ReportQualityGate.model_validate(
        {
            "status": gate_status,
            "issues": quality_issues,
            "text_quality": text_quality,
            "product_mapping": product_mapping,
            "consistency": consistency,
            "decision_readiness": decision_readiness,
        }
    ).model_dump()
    return {
        "content": safe_content,
        "evidence": safe_evidence,
        "quality_gate": quality_gate,
    }
