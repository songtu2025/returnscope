from __future__ import annotations

from typing import Any


def _decision_report_consistency(
    content: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    consistency = _report_consistency(
        content,
        evidence,
        require_information_diagnostics=False,
    )
    issues = list(consistency["issues"])
    blueprint_issues = evidence.get("blueprint", {}).get("issues", [])
    expected = {
        str(item.get("id")): item for item in blueprint_issues if item.get("id")
    }
    actual = {
        str(item.get("id")): item
        for item in content.get("issues", [])
        if item.get("id")
    }
    if list(actual) != list(expected):
        issues.append("问题列表或排序与确定性证据不一致")
    for issue_id, blueprint in expected.items():
        issue = actual.get(issue_id)
        if issue is None:
            continue
        if issue.get("metrics") != blueprint.get("metrics"):
            issues.append(f"问题 {issue_id} 的指标与确定性证据不一致")
        if issue.get("evidence_ids") != blueprint.get("evidence_ids"):
            issues.append(f"问题 {issue_id} 的证据引用不一致")
    return {
        "status": "blocked" if issues else "passed",
        "issues": list(dict.fromkeys(issues)),
    }


def _report_consistency(
    content: dict[str, Any],
    evidence: dict[str, Any],
    *,
    require_information_diagnostics: bool,
) -> dict[str, Any]:
    analysis = evidence.get("analysis", {})
    reasons = {
        str(item.get("value")): item
        for item in analysis.get("reasons", [])
        if item.get("value")
    }
    diagnostics: dict[str, dict[str, Any]] = {}
    issues: list[str] = []

    for diagnostic in analysis.get("diagnostics", []):
        code = str(diagnostic.get("reason_code") or "")
        if not code:
            issues.append("存在未标明原因代码的诊断数据")
            continue
        if code in diagnostics:
            issues.append(f"原因 {code} 存在重复诊断数据")
            continue
        diagnostics[code] = diagnostic
        reason = reasons.get(code)
        if reason is None:
            issues.append(f"诊断原因 {code} 不在分类结果中")
            continue

        selected_reason = diagnostic.get("selected_reason") or {}
        if str(selected_reason.get("value") or "") != code:
            issues.append(f"诊断原因 {code} 与选中原因不一致")
        if selected_reason.get("record_count") is None or int(
            selected_reason.get("record_count") or 0
        ) != int(reason.get("record_count") or 0):
            issues.append(f"诊断原因 {code} 的记录数与分类结果不一致")
        selected_percentage = selected_reason.get("percentage")
        if (
            selected_percentage is None
            or abs(
                float(selected_percentage or 0) - float(reason.get("percentage") or 0)
            )
            > 0.05
        ):
            issues.append(f"诊断原因 {code} 的占比与分类结果不一致")

    for finding in content.get("findings", []):
        if finding.get("kind") != "information":
            continue
        reason_codes = [
            str(evidence_id)[len("reason.") :]
            for evidence_id in finding.get("evidence_ids", [])
            if str(evidence_id).startswith("reason.")
        ]
        if len(reason_codes) != 1:
            issues.append("信息诊断未绑定唯一的分类原因")
            continue
        code = reason_codes[0]
        if code not in reasons:
            issues.append(f"信息诊断原因 {code} 不在分类结果中")
        if require_information_diagnostics and code not in diagnostics:
            issues.append(f"信息诊断原因 {code} 缺少语义诊断数据")

    return {
        "status": "blocked" if issues else "passed",
        "issues": list(dict.fromkeys(issues)),
    }
