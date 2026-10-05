"""集中定义质量指标、默认策略和发布门槛判定。"""

from web_backend.classification_reference_scope import SCOPE_FIELDS, SCOPE_METRICS

ERROR_METRICS = (
    "extra_labels",
    "missing_labels",
    "duplicate_units",
    "direction_errors",
    "part_errors",
    "evidence_errors",
    "model_errors",
    "statement_type_errors",
    "actor_errors",
    "product_errors",
    "plan_confirmation_errors",
    *SCOPE_METRICS,
)
HIGH_DAMAGE_METRICS = (
    "model_errors",
    "evidence_errors",
    "plan_confirmation_errors",
    "product_errors",
    "direction_errors",
    "subject_errors",
    "primary_errors",
)
WARNING_METRICS = tuple(
    metric for metric in ERROR_METRICS if metric not in HIGH_DAMAGE_METRICS
)
FACT_QUALITY_POLICY = {
    "version": "fact-reference-v4",
    "thresholds": dict.fromkeys(HIGH_DAMAGE_METRICS, 0),
    "warning_metrics": list(WARNING_METRICS),
    "min_reference_samples": 15,
    "min_reference_coverage": 80,
    "min_instance_match_rate": 80,
    "max_duplicate_rate": 10,
    "require_fact_states": False,
    "warn_incomplete_fact_states": True,
    "require_scope_dimensions": [],
    "warn_incomplete_scope_dimensions": list(SCOPE_FIELDS),
}
METRIC_LABELS = dict(
    zip(
        ERROR_METRICS,
        (
            "多标实例",
            "漏标实例",
            "重复实例",
            "方向错误",
            "明确部位漏错",
            "证据检查失败",
            "模型错误",
            "事实状态错误",
            "使用者错配",
            "商品对象错配",
            "计划或假设误确认为事实",
            *SCOPE_METRICS.values(),
        ),
        strict=True,
    )
)


def quality_gate(summary: dict, policy: dict | None = None) -> dict:
    """只用已配置的指标门槛评估，不把无参考答案当作零错误。"""
    evaluation = summary.get("reference_evaluation", {})
    if not policy:
        return {
            "status": "not_configured",
            "passed": True,
            "blocking": [],
            "warnings": [],
            "note": "未配置自动质量门槛，需人工审阅；不代表语义质量已通过",
        }
    values = evaluation.get("sides", {}).get("draft", {})
    blocking, warnings = _metric_quality_issues(values, policy)
    sample_count = evaluation.get("sample_count", 0)
    if sample_count < policy["min_reference_samples"]:
        blocking.append(
            f"非歧义参考样本 {sample_count} 条，至少需要 {policy['min_reference_samples']} 条"
        )
    total = evaluation.get("total_sample_count", summary.get("sample_size", 0))
    scope_blocking, scope_warnings = _scope_quality_issues(evaluation, policy, total)
    blocking.extend(scope_blocking)
    warnings.extend(scope_warnings)
    coverage, match_rate, duplicate_rate = _reference_rates(values, sample_count, total)
    rate_blocking, rate_warnings = _rate_quality_issues(
        coverage, match_rate, duplicate_rate, policy
    )
    blocking.extend(rate_blocking)
    warnings.extend(rate_warnings)
    state_blocking, state_warnings = _fact_state_quality_issues(
        evaluation, policy, total
    )
    blocking.extend(state_blocking)
    warnings.extend(state_warnings)
    return {
        "status": "failed" if blocking else "passed",
        "passed": not blocking,
        "blocking": blocking,
        "warnings": warnings,
        "policy": policy,
        "reference_coverage": coverage,
        "instance_match_rate": match_rate,
        "duplicate_rate": duplicate_rate,
    }


def _scope_quality_issues(
    evaluation: dict,
    policy: dict,
    total: int,
) -> tuple[list[str], list[str]]:
    """按策略检查参考维度完整性，缺列或零样本不能视为已评估。"""
    blocking = []
    warnings = []
    for dimension in policy.get("require_scope_dimensions", []):
        count = evaluation.get("scope_sample_counts", {}).get(dimension, 0)
        if count != total or not total:
            blocking.append(
                f"{SCOPE_FIELDS[dimension][0]}参考未完整评估：{count}/{total} 条；旧表缺列不代表零错误"
            )
    for dimension in policy.get("warn_incomplete_scope_dimensions", []):
        count = evaluation.get("scope_sample_counts", {}).get(dimension, 0)
        if count != total or not total:
            warnings.append(
                f"{SCOPE_FIELDS[dimension][0]}参考未完整评估：{count}/{total} 条；请在人工审批时核对"
            )
    return blocking, warnings


def _rate_quality_issues(
    coverage: float,
    match_rate: float,
    duplicate_rate: float,
    policy: dict,
) -> tuple[list[str], list[str]]:
    """按未四舍五入的比例判定，展示时才保留两位小数。"""
    blocking = []
    warnings = []
    for actual, limit, message, minimum in (
        (coverage, policy["min_reference_coverage"], "非歧义参考覆盖率", True),
        (match_rate, policy["min_instance_match_rate"], "实例标签匹配率", True),
        (duplicate_rate, policy["max_duplicate_rate"], "重复事实样本率", False),
    ):
        if (actual < limit) if minimum else (actual > limit):
            blocking.append(
                f"{message} {actual:.2f}%，要求{'至少' if minimum else '不超过'} {limit}%"
            )
        elif (minimum and actual < 100) or (not minimum and actual > 0):
            warnings.append(f"{message} {actual:.2f}%，请人工复核")
    return blocking, warnings


def _metric_quality_issues(values: dict, policy: dict) -> tuple[list[str], list[str]]:
    blocking = [
        f"{METRIC_LABELS.get(metric, metric)}={values.get(metric, '未评估')}，要求不超过 {limit}"
        for metric, limit in policy["thresholds"].items()
        if metric not in values or values[metric] > limit
    ]
    warnings = [
        f"{METRIC_LABELS.get(metric, metric)}={values.get(metric, '未评估')}，请人工复核"
        for metric in policy.get("warning_metrics", [])
        if metric not in values or values[metric] > 0
    ]
    return (blocking, warnings)


def _reference_rates(
    values: dict, sample_count: int, total: int
) -> tuple[float, float, float]:
    coverage = sample_count / total * 100 if total else 0
    denominator = max(
        values.get("expected_instances", 0), values.get("actual_instances", 0)
    )
    match_rate = (
        values.get("matched_instances", 0) / denominator * 100
        if denominator
        else 100
        if sample_count
        else 0
    )
    duplicate_rate = values.get("duplicate_samples", 0) / max(1, sample_count) * 100
    return (coverage, match_rate, duplicate_rate)


def _fact_state_quality_issues(
    evaluation: dict, policy: dict, total: int
) -> tuple[list[str], list[str]]:
    blocking = []
    warnings = []
    if (
        policy.get("require_fact_states")
        and evaluation.get("fact_state_sample_count", 0) != total
    ):
        blocking.append(
            "事实状态参考答案不完整：每条参考行须填写事实状态及对应证据；不能将未验证状态算作通过"
        )
    if (
        policy.get("warn_incomplete_fact_states")
        and evaluation.get("fact_state_sample_count", 0) != total
    ):
        warnings.append(
            "事实状态参考答案不完整：请在人工审批时核对未标注样本的事实状态"
        )
    return (blocking, warnings)
