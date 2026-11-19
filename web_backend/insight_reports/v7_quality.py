from __future__ import annotations

from copy import deepcopy
from typing import Any

from web_backend.insight_report_contracts import DecisionReportQualityGate
from web_backend.insight_report_quality_v6 import (
    _apply_text_quality,
    _quality_readiness,
)
from web_backend.insight_reports.quality_issues import source_quality_issues
from web_backend.insight_reports.v7_content import assemble_semantic_content


def evaluate_semantic_quality(
    content: dict[str, Any], evidence: dict[str, Any], text_quality: dict[str, Any]
) -> dict[str, Any]:
    safe_content = deepcopy(content)
    safe_evidence = deepcopy(evidence)
    source = safe_evidence["source"]
    analysis = safe_evidence["analysis"]
    catalog = safe_evidence["catalog"]
    mapping = source["product_mapping"]
    if text_quality.get("status") == "needs_review":
        safe_content = assemble_semantic_content(safe_evidence, {}).model_dump()
    issues = _apply_text_quality(safe_content, source, analysis, catalog, text_quality)
    issues.extend(
        source_quality_issues(
            mapping,
            analysis["review_bias"],
            source["pending_review_record_count"],
            mapping_trusted=mapping["status"] != "needs_review",
        )
    )
    references = {
        evidence_id
        for item in safe_content["issues"] + safe_content["executive_summary"]
        for evidence_id in item["evidence_ids"]
    }
    consistent = references <= catalog.keys()
    consistency = {
        "status": "passed" if consistent else "blocked",
        "issues": [] if consistent else ["存在无法追溯的证据引用"],
    }
    readiness, status = _quality_readiness(consistency, issues)
    for issue in safe_content["issues"]:
        if readiness["status"] != "verification_ready":
            issue["readiness"] = readiness
    if status == "passed" and all(
        issue["readiness"]["status"] != "verification_ready"
        for issue in safe_content["issues"]
    ):
        readiness = {
            "status": "diagnostic_only",
            "label": "仅供诊断",
            "reason": "当前洞察的样本量或数据范围仍有限。",
        }
        status = "warning"
    source["quality_issue_codes"] = [item["code"] for item in issues]
    source["report_status"] = "provisional" if status != "passed" else "final"
    return {
        "content": safe_content,
        "evidence": safe_evidence,
        "quality_gate": DecisionReportQualityGate.model_validate(
            {
                "status": status,
                "issues": issues,
                "text_quality": text_quality,
                "product_mapping": mapping,
                "consistency": consistency,
                "decision_readiness": readiness,
            }
        ).model_dump(),
    }
