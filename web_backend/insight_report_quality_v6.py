from __future__ import annotations

from copy import deepcopy
from typing import Any

from web_backend.insight_report_consistency import _decision_report_consistency
from web_backend.insight_report_contracts import DecisionReportQualityGate
from web_backend.insight_report_diagnostics import (
    _filter_business_issue_text,
    _filter_diagnostic_text,
    _filter_issue_case_text,
    _has_text_anomaly,
)


def _evaluate_live_quality_v6(
    content: dict[str, Any],
    evidence: dict[str, Any],
    text_quality: dict[str, Any],
) -> dict[str, Any]:
    safe_content = deepcopy(content)
    safe_evidence = deepcopy(evidence)
    source = safe_evidence.setdefault("source", {})
    analysis = safe_evidence.setdefault("analysis", {})
    catalog = safe_evidence.setdefault("catalog", {})
    product_mapping = source.get("product_mapping", {})
    review_bias = analysis.get("review_bias", {})
    pending_count = int(source.get("pending_review_record_count") or 0)
    quality_issues = []

    source["text_quality"] = text_quality
    analysis["text_quality"] = text_quality
    catalog["text_quality"] = {
        "label": "评论文本质量",
        "value": str(text_quality.get("note") or "未发现明显编码异常"),
        "data": text_quality,
    }
    if text_quality.get("status") == "needs_review":
        quality_issues.append(
            {
                "code": "text_quality",
                "label": "评论文本质量未通过",
                "detail": str(text_quality.get("note") or "评论文本需要核对。"),
                "evidence_ids": ["text_quality", "scope"],
            }
        )
        analysis["diagnostics"] = [
            _filter_diagnostic_text(item) for item in analysis.get("diagnostics", [])
        ]
        analysis["issue_cases"] = [
            _filter_issue_case_text(item) for item in analysis.get("issue_cases", [])
        ]
        analysis["business_issues"] = [
            _filter_business_issue_text(item)
            for item in analysis.get("business_issues", [])
        ]
        analysis["samples"] = []
        for evidence_id, item in catalog.items():
            if not any(marker in evidence_id for marker in (".sample.", ".opinion.")):
                continue
            data = item.get("data", {})
            if _has_text_anomaly(
                data.get("opinion"),
                data.get("evidence"),
                data.get("comment"),
                data.get("reason"),
            ):
                item["value"] = "文本质量未通过，原始文本证据暂不可用"
                item["data"] = {}
        for issue in safe_content.get("issues", []):
            issue["known"] = [
                value
                for value in issue.get("known", [])
                if not str(value).startswith("高频反馈为")
            ]
            issue["evidence_explanation"] = (
                "评论文本质量未通过，当前仅保留结构化指标用于定位，不能据此判断原因。"
            )

    if product_mapping.get("status") == "needs_review":
        quality_issues.append(
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
        quality_issues.append(
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

    consistency = _decision_report_consistency(
        safe_content,
        safe_evidence,
    )
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
        readiness = {
            "status": "unusable",
            "label": "不可使用",
            "reason": "报告内部数据不一致，请重新生成报告。",
        }
        gate_status = "blocked"
    elif quality_issues:
        readiness = {
            "status": "diagnostic_only",
            "label": "仅供诊断",
            "reason": "数据质量或审核范围仍有限，只能用于定位问题。",
        }
        gate_status = "warning"
    else:
        readiness = {
            "status": "verification_ready",
            "label": "可进入验证",
            "reason": "数据质量和报告一致性校验均已通过。",
        }
        gate_status = "passed"

    if readiness["status"] != "verification_ready":
        for issue in safe_content.get("issues", []):
            issue["readiness"] = readiness
    source["quality_issue_codes"] = [item["code"] for item in quality_issues]
    source["report_status"] = "provisional" if quality_issues else "final"
    quality_gate = DecisionReportQualityGate.model_validate(
        {
            "status": gate_status,
            "issues": quality_issues,
            "text_quality": text_quality,
            "product_mapping": product_mapping,
            "consistency": consistency,
            "decision_readiness": readiness,
        }
    ).model_dump()
    return {
        "content": safe_content,
        "evidence": safe_evidence,
        "quality_gate": quality_gate,
    }
