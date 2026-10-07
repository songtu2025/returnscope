from __future__ import annotations

from return_semantics.semantic_review_items import _get, _list, _text

_SYSTEM_REVIEW_REASON_PREFIXES = (
    "覆盖审计失败",
    "二次模型调用失败:",
    "二次模型结果未通过程序校验",
    "两次模型的语义结果不一致",
    "低成本模型与主模型结果不一致",
    "风险复核模型缺失",
)


_DETAILS_NOT_RETAINED = "NOT_RETAINED"


_DETAILS_NOT_APPLICABLE = "NOT_APPLICABLE"


_DIAGNOSTIC_METADATA = {
    "COVERAGE_AUDIT_FAILED": (
        "SEMANTIC_ANALYSIS_QUALITY",
        "可能存在用户反馈漏抽",
        "请核对疑似漏抽片段；没有片段时请系统重跑。",
    ),
    "MODEL_RESULT_MISMATCH": (
        "SEMANTIC_ANALYSIS_QUALITY",
        "两次模型结果不一致",
        "请核对两次模型的逐项差异；没有差异明细时请系统重跑。",
    ),
    "LABEL_RULE_REVIEW_REQUIRED": (
        "SEMANTIC_ANALYSIS_QUALITY",
        "标签规则要求人工判断",
        "请业务员核对原文证据是否足以支持该标签，并确认保留或修改标签。",
    ),
    "SECONDARY_MODEL_MISSING": (
        "TECHNICAL_CONFIGURATION",
        "风险复核模型未配置",
        "已使用主模型完成复核；无需业务员核验，请管理员补充风险复核模型配置。",
    ),
    "SECONDARY_MODEL_TIMEOUT": (
        "TECHNICAL_RUNTIME",
        "风险复核调用超时",
        "无需业务员核验；请系统重试风险复核。",
    ),
    "SECONDARY_MODEL_CALL_FAILED": (
        "TECHNICAL_RUNTIME",
        "风险复核调用失败",
        "无需业务员核验；请系统重试风险复核。",
    ),
    "SECONDARY_RESULT_INVALID": (
        "TECHNICAL_RUNTIME",
        "风险复核结果校验失败",
        "无需业务员核验；请系统重新执行风险复核。",
    ),
    "MODEL_RUN_TIMEOUT": (
        "TECHNICAL_RUNTIME",
        "模型分析超时",
        "无需业务员核验；请系统重跑本条分析。",
    ),
    "MODEL_RUN_FAILED": (
        "TECHNICAL_RUNTIME",
        "模型分析未完成",
        "无需业务员核验；请系统重跑本条分析。",
    ),
}


def _system_review_reasons(result: object) -> list[str]:
    reasons = [_text(reason) for reason in _list(result, "review_reasons")]
    return list(
        dict.fromkeys(
            reason
            for reason in reasons
            if reason.startswith(_SYSTEM_REVIEW_REASON_PREFIXES)
        )
    )


def _failure_code(reason: str, *, model_error: bool = False) -> str:
    normalized = reason.casefold()
    is_timeout = (
        "超时" in reason or "timeout" in normalized or "timed out" in normalized
    )
    if model_error:
        return "MODEL_RUN_TIMEOUT" if is_timeout else "MODEL_RUN_FAILED"
    if reason.startswith("覆盖审计失败"):
        return "COVERAGE_AUDIT_FAILED"
    if reason.startswith(("两次模型的语义结果不一致", "低成本模型与主模型结果不一致")):
        return "MODEL_RESULT_MISMATCH"
    if reason.startswith("风险复核模型缺失"):
        return "SECONDARY_MODEL_MISSING"
    if reason.startswith("二次模型调用失败:"):
        return (
            "SECONDARY_MODEL_TIMEOUT" if is_timeout else "SECONDARY_MODEL_CALL_FAILED"
        )
    return "SECONDARY_RESULT_INVALID"


def _legacy_diagnostic_action(code: str, action: str) -> str:
    if code == "COVERAGE_AUDIT_FAILED":
        return (
            "当前结果未保留疑似漏抽的原文片段，业务员无法据此判断；"
            "请系统重跑并保留疑似漏抽片段。"
        )
    if code == "MODEL_RESULT_MISMATCH":
        return (
            "当前结果未保留两次模型的差异明细，业务员无法据此判断；"
            "请系统重跑并保留逐项差异。"
        )
    return action


def _failure_diagnostic(reason: str, *, model_error: bool = False) -> dict[str, object]:
    code = _failure_code(reason, model_error=model_error)
    domain, title, action = _DIAGNOSTIC_METADATA[code]
    action = _legacy_diagnostic_action(code, action)
    return {
        "diagnostic_domain": domain,
        "diagnostic_code": code,
        "diagnostic_title": title,
        "detail_status": (
            _DETAILS_NOT_RETAINED
            if code in {"COVERAGE_AUDIT_FAILED", "MODEL_RESULT_MISMATCH"}
            else _DETAILS_NOT_APPLICABLE
        ),
        "action": action,
        "business_review_required": False,
    }


def _structured_failure_diagnostic(value: object) -> dict[str, object]:
    code = _text(_get(value, "code")) or "ANALYSIS_DIAGNOSTIC"
    evidence_text = _text(_get(value, "evidence_text"))
    primary_result = _text(_get(value, "primary_result"))
    secondary_result = _text(_get(value, "secondary_result"))
    detail = _text(_get(value, "detail"))
    action = _text(_get(value, "action"))

    domain, title, default_action = _DIAGNOSTIC_METADATA.get(
        code,
        _DIAGNOSTIC_METADATA["MODEL_RUN_FAILED"],
    )

    has_details = _diagnostic_has_details(
        code, evidence_text, primary_result, secondary_result
    )
    is_system_action = action in {"SYSTEM_RERUN", "SYSTEM_RETRY", "ADMIN_CONFIG"}
    action_text = _structured_diagnostic_action(
        code, action, default_action, is_system_action
    )
    return {
        "diagnostic_domain": domain,
        "diagnostic_code": code,
        "diagnostic_title": title,
        "detail_status": (
            "AVAILABLE"
            if has_details
            else _DETAILS_NOT_APPLICABLE
            if domain != "SEMANTIC_ANALYSIS_QUALITY"
            else _DETAILS_NOT_RETAINED
        ),
        "evidence_text": evidence_text,
        "primary_result": primary_result,
        "secondary_result": secondary_result,
        "detail": detail,
        "action": action_text,
        "business_review_required": domain == "SEMANTIC_ANALYSIS_QUALITY"
        and has_details
        and not is_system_action,
    }


def _diagnostic_has_details(
    code: str,
    evidence_text: str,
    primary_result: str,
    secondary_result: str,
) -> bool:
    if code == "COVERAGE_AUDIT_FAILED":
        return bool(evidence_text)
    if code in {"MODEL_RESULT_MISMATCH", "LABEL_RULE_REVIEW_REQUIRED"}:
        return bool(evidence_text or primary_result or secondary_result)
    return False


def _structured_diagnostic_action(
    code: str,
    action: str,
    default_action: str,
    is_system_action: bool,
) -> str:
    if is_system_action and code == "COVERAGE_AUDIT_FAILED":
        return "无需业务员判断本次运行异常；请系统重跑，疑似片段仅用于定位。"
    if is_system_action and code == "MODEL_RESULT_MISMATCH":
        return "无需业务员判断本次运行异常；请系统重跑，差异明细仅用于定位。"
    return default_action if not action or is_system_action else action
