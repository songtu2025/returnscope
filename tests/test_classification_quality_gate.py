from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
from test_classification_validation_quality import _item, _with_state

from web_backend.classification_validation_quality import (
    FACT_QUALITY_POLICY,
    SCOPE_FIELDS,
    evaluate_references,
    publication_quality_gate,
    quality_gate,
)


@pytest.fixture
def gate_inputs() -> tuple[dict[str, Any], dict[str, Any]]:
    items = [_with_state(_item()) for _ in range(20)]
    summary = {"sample_size": 20, "reference_evaluation": evaluate_references(items)}
    return summary, deepcopy(FACT_QUALITY_POLICY)


@pytest.mark.parametrize("policy", [None, {}])
def test_unconfigured_policy_requires_review_without_claiming_semantic_success(
    policy: dict[str, Any] | None,
) -> None:
    summary = {"reference_evaluation": None}
    assert quality_gate(summary, policy) == {
        "status": "not_configured",
        "passed": True,
        "blocking": [],
        "warnings": [],
        "note": "未配置自动质量门槛，需人工审阅；不代表语义质量已通过",
    }
    assert summary == {"reference_evaluation": None}


def test_complete_reference_preserves_full_result_and_inputs(
    gate_inputs: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    summary, policy = gate_inputs
    before = deepcopy((summary, policy))
    actual = quality_gate(summary, policy)
    assert actual == {
        "status": "passed",
        "passed": True,
        "blocking": [],
        "warnings": [],
        "policy": policy,
        "reference_coverage": 100,
        "instance_match_rate": 100,
        "duplicate_rate": 0,
    }
    assert actual["policy"] is policy
    assert (summary, policy) == before


@pytest.mark.parametrize(
    "case",
    [
        ("sample_count", 15, 75, "非歧义参考覆盖率 75.00%，要求至少 80%", ""),
        ("sample_count", 16, 80, "", "非歧义参考覆盖率 80.00%，请人工复核"),
        ("sample_count", 17, 85, "", "非歧义参考覆盖率 85.00%，请人工复核"),
        ("sample_count", 20, 100, "", ""),
        ("matched_instances", 15, 75, "实例标签匹配率 75.00%，要求至少 80%", ""),
        ("matched_instances", 16, 80, "", "实例标签匹配率 80.00%，请人工复核"),
        ("matched_instances", 17, 85, "", "实例标签匹配率 85.00%，请人工复核"),
        ("matched_instances", 20, 100, "", ""),
        ("duplicate_samples", 1, 5, "", "重复事实样本率 5.00%，请人工复核"),
        ("duplicate_samples", 2, 10, "", "重复事实样本率 10.00%，请人工复核"),
        ("duplicate_samples", 3, 15, "重复事实样本率 15.00%，要求不超过 10%", ""),
        ("duplicate_samples", 0, 0, "", ""),
        (
            "matched_instances",
            15.9999,
            79.9995,
            "实例标签匹配率 80.00%，要求至少 80%",
            "",
        ),
        (
            "duplicate_samples",
            2.00001,
            10.00005,
            "重复事实样本率 10.00%，要求不超过 10%",
            "",
        ),
    ],
)
def test_rate_thresholds_preserve_equality_and_unrounded_comparison(
    gate_inputs: tuple[dict[str, Any], dict[str, Any]],
    case: tuple[str, float, float, str, str],
) -> None:
    metric, value, expected_rate, blocking, warning = case
    summary, policy = gate_inputs
    evaluation = summary["reference_evaluation"]
    if metric == "sample_count":
        evaluation[metric] = value
        result_key = "reference_coverage"
    else:
        evaluation["sides"]["draft"][metric] = value
        result_key = {
            "matched_instances": "instance_match_rate",
            "duplicate_samples": "duplicate_rate",
        }[metric]
    before = deepcopy((summary, policy))
    actual = quality_gate(summary, policy)
    assert actual[result_key] == pytest.approx(expected_rate)
    assert actual["blocking"] == ([blocking] if blocking else [])
    assert actual["warnings"] == ([warning] if warning else [])
    assert actual["passed"] is (not blocking)
    assert actual["status"] == ("failed" if blocking else "passed")
    assert (summary, policy) == before


@pytest.mark.parametrize("dimension", list(SCOPE_FIELDS))
@pytest.mark.parametrize(
    "mode", ["require_scope_dimensions", "warn_incomplete_scope_dimensions"]
)
@pytest.mark.parametrize("count", [19, 20, 21, None])
def test_scope_missing_or_incomplete_keeps_configured_severity(
    gate_inputs: tuple[dict[str, Any], dict[str, Any]],
    dimension: str,
    mode: str,
    count: int | None,
) -> None:
    summary, policy = gate_inputs
    policy["require_scope_dimensions"] = []
    policy["warn_incomplete_scope_dimensions"] = []
    policy[mode] = [dimension]
    counts = summary["reference_evaluation"]["scope_sample_counts"]
    if count is None:
        counts.pop(dimension)
    else:
        counts[dimension] = count
    actual = quality_gate(summary, policy)
    label = SCOPE_FIELDS[dimension][0]
    detail = f"{label}参考未完整评估：{count or 0}/20 条；"
    expected = (
        []
        if count == 20
        else [
            detail
            + (
                "旧表缺列不代表零错误"
                if mode == "require_scope_dimensions"
                else "请在人工审批时核对"
            )
        ]
    )
    assert actual["blocking"] == (
        expected if mode == "require_scope_dimensions" else []
    )
    assert actual["warnings"] == (
        expected if mode == "warn_incomplete_scope_dimensions" else []
    )


@pytest.mark.parametrize("total", [0, None])
def test_zero_or_missing_total_keeps_scope_and_matching_denominator_rules(
    gate_inputs: tuple[dict[str, Any], dict[str, Any]],
    total: int | None,
) -> None:
    summary, policy = gate_inputs
    evaluation = summary["reference_evaluation"]
    if total is None:
        evaluation.pop("total_sample_count")
    else:
        evaluation["total_sample_count"] = total
    actual = quality_gate(summary, policy)
    assert actual["reference_coverage"] == (100 if total is None else 0)
    assert actual["blocking"] == (
        [] if total is None else ["非歧义参考覆盖率 0.00%，要求至少 80%"]
    )
    assert len(actual["warnings"]) == (0 if total is None else 5)


@pytest.mark.parametrize("sample_count", [0, 20])
def test_matching_without_instances_uses_reference_sample_count(
    gate_inputs: tuple[dict[str, Any], dict[str, Any]],
    sample_count: int,
) -> None:
    summary, policy = gate_inputs
    evaluation = summary["reference_evaluation"]
    evaluation["sample_count"] = sample_count
    evaluation["sides"]["draft"].update(
        expected_instances=0,
        actual_instances=0,
        matched_instances=0,
        duplicate_samples=1,
    )
    actual = quality_gate(summary, policy)
    assert actual["instance_match_rate"] == (100 if sample_count else 0)
    assert actual["duplicate_rate"] == (5 if sample_count else 100)


def test_zero_total_does_not_claim_scope_was_evaluated(
    gate_inputs: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    summary, policy = gate_inputs
    evaluation = summary["reference_evaluation"]
    evaluation.update(sample_count=0, total_sample_count=0, fact_state_sample_count=0)
    evaluation["scope_sample_counts"] = dict.fromkeys(SCOPE_FIELDS, 0)
    policy["require_scope_dimensions"] = ["event"]
    actual = quality_gate(summary, policy)
    assert "事件参考未完整评估：0/0 条；旧表缺列不代表零错误" in actual["blocking"]
    assert actual["warnings"] == [
        f"{label}参考未完整评估：0/0 条；请在人工审批时核对"
        for label, _field in SCOPE_FIELDS.values()
    ]


def test_matching_rate_uses_larger_expected_or_actual_instance_count(
    gate_inputs: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    summary, policy = gate_inputs
    summary["reference_evaluation"]["sides"]["draft"].update(
        expected_instances=20, actual_instances=25, matched_instances=20
    )
    actual = quality_gate(summary, policy)
    assert actual["instance_match_rate"] == 80
    assert actual["warnings"] == ["实例标签匹配率 80.00%，请人工复核"]


def test_messages_preserve_group_order_duplicates_and_unknown_metric_names(
    gate_inputs: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    summary, policy = gate_inputs
    evaluation = summary["reference_evaluation"]
    policy.update(
        thresholds={"custom": 0, "model_errors": 0},
        warning_metrics=["missing_labels", "missing_labels", "custom"],
        require_scope_dimensions=["event", "event"],
        warn_incomplete_scope_dimensions=["condition", "condition"],
        require_fact_states=True,
    )
    evaluation.update(sample_count=14, fact_state_sample_count=19)
    evaluation["scope_sample_counts"].update(event=19, condition=19)
    evaluation["sides"]["draft"].update(
        model_errors=1, missing_labels=1, matched_instances=14, duplicate_samples=2
    )
    before = deepcopy((summary, policy))
    actual = quality_gate(summary, policy)
    assert actual["blocking"] == [
        "custom=未评估，要求不超过 0",
        "模型错误=1，要求不超过 0",
        "非歧义参考样本 14 条，至少需要 15 条",
        "事件参考未完整评估：19/20 条；旧表缺列不代表零错误",
        "事件参考未完整评估：19/20 条；旧表缺列不代表零错误",
        "非歧义参考覆盖率 70.00%，要求至少 80%",
        "实例标签匹配率 70.00%，要求至少 80%",
        "重复事实样本率 14.29%，要求不超过 10%",
        "事实状态参考答案不完整：每条参考行须填写事实状态及对应证据；不能将未验证状态算作通过",
    ]
    assert actual["warnings"] == [
        "漏标实例=1，请人工复核",
        "漏标实例=1，请人工复核",
        "custom=未评估，请人工复核",
        "条件参考未完整评估：19/20 条；请在人工审批时核对",
        "条件参考未完整评估：19/20 条；请在人工审批时核对",
        "事实状态参考答案不完整：请在人工审批时核对未标注样本的事实状态",
    ]
    assert (summary, policy) == before


@pytest.mark.parametrize("required", [False, True])
@pytest.mark.parametrize("warn", [False, True])
@pytest.mark.parametrize("count", [19, 20])
def test_fact_state_checks_preserve_independent_blocking_and_warning_flags(
    gate_inputs: tuple[dict[str, Any], dict[str, Any]],
    required: bool,
    warn: bool,
    count: int,
) -> None:
    summary, policy = gate_inputs
    policy.update(require_fact_states=required, warn_incomplete_fact_states=warn)
    summary["reference_evaluation"]["fact_state_sample_count"] = count
    actual = quality_gate(summary, policy)
    assert actual["blocking"] == (
        [
            "事实状态参考答案不完整：每条参考行须填写事实状态及对应证据；不能将未验证状态算作通过"
        ]
        if required and count != 20
        else []
    )
    assert actual["warnings"] == (
        ["事实状态参考答案不完整：请在人工审批时核对未标注样本的事实状态"]
        if warn and count != 20
        else []
    )


@pytest.mark.parametrize(
    ("invalid", "exception"),
    [
        ({"thresholds": {}}, KeyError),
        ({**FACT_QUALITY_POLICY, "require_scope_dimensions": ["unknown"]}, KeyError),
        ({**FACT_QUALITY_POLICY, "min_reference_coverage": None}, TypeError),
    ],
)
def test_invalid_policy_keeps_exception_without_modifying_inputs(
    gate_inputs: tuple[dict[str, Any], dict[str, Any]],
    invalid: dict[str, Any],
    exception: type[Exception],
) -> None:
    summary, _policy = gate_inputs
    summary["reference_evaluation"]["scope_sample_counts"]["unknown"] = 19
    before = deepcopy((summary, invalid))
    with pytest.raises(exception):
        quality_gate(summary, invalid)
    assert (summary, invalid) == before


@pytest.mark.parametrize("profile", ["fact_v2", "semantic_v1"])
@pytest.mark.parametrize("policy", [None, {}])
def test_publication_keeps_fact_default_and_unconfigured_legacy_profile(
    gate_inputs: tuple[dict[str, Any], dict[str, Any]],
    profile: str,
    policy: dict[str, Any] | None,
) -> None:
    summary, _configured = gate_inputs
    actual = publication_quality_gate(
        {"taxonomy": {"recognition_profile": profile}},
        {"quality_policy": policy},
        [],
        summary,
    )
    assert actual == quality_gate(
        summary, FACT_QUALITY_POLICY if profile == "fact_v2" else policy
    )


def test_publication_recalculates_items_and_keeps_existing_comparison_side_effect() -> (
    None
):
    items = [_with_state(_item()) for _ in range(20)]
    summary = {"reference_evaluation": {"sample_count": 0}}
    before = deepcopy(summary)
    actual = publication_quality_gate(
        {"taxonomy": {"recognition_profile": "fact_v2"}}, {}, items, summary
    )
    assert actual["passed"]
    assert actual["reference_coverage"] == 100
    assert summary == before
    assert all("reference_comparison" in item for item in items)
