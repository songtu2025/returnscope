from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from web_backend.insight_report_consistency import (
    _decision_report_consistency,
    _report_consistency,
)
from web_backend.insight_report_service import InsightReportService


def _reason(**changes: Any) -> dict[str, Any]:
    return {"value": "A", "record_count": 2, "percentage": 0, **changes}


def _diagnostic(**changes: Any) -> dict[str, Any]:
    return {"reason_code": "A", "selected_reason": _reason(), **changes}


@pytest.mark.parametrize(
    ("diagnostics", "expected"),
    [
        ([_diagnostic()], []),
        ([_diagnostic(selected_reason=_reason(record_count="2", percentage="0"))], []),
        ([{}], ["存在未标明原因代码的诊断数据"]),
        ([_diagnostic(reason_code="")], ["存在未标明原因代码的诊断数据"]),
        ([_diagnostic(reason_code=None)], ["存在未标明原因代码的诊断数据"]),
        ([_diagnostic(reason_code="B")], ["诊断原因 B 不在分类结果中"]),
        ([_diagnostic(), _diagnostic()], ["原因 A 存在重复诊断数据"]),
        ([_diagnostic(), _diagnostic(selected_reason={})], ["原因 A 存在重复诊断数据"]),
        (
            [_diagnostic(selected_reason=_reason(value="B"))],
            ["诊断原因 A 与选中原因不一致"],
        ),
        (
            [_diagnostic(selected_reason=_reason(record_count=None))],
            ["诊断原因 A 的记录数与分类结果不一致"],
        ),
        (
            [_diagnostic(selected_reason=_reason(record_count=3))],
            ["诊断原因 A 的记录数与分类结果不一致"],
        ),
        (
            [_diagnostic(selected_reason=_reason(percentage=None))],
            ["诊断原因 A 的占比与分类结果不一致"],
        ),
        (
            [_diagnostic(selected_reason={})],
            [
                "诊断原因 A 与选中原因不一致",
                "诊断原因 A 的记录数与分类结果不一致",
                "诊断原因 A 的占比与分类结果不一致",
            ],
        ),
        (
            [_diagnostic(selected_reason=None)],
            [
                "诊断原因 A 与选中原因不一致",
                "诊断原因 A 的记录数与分类结果不一致",
                "诊断原因 A 的占比与分类结果不一致",
            ],
        ),
        (
            [{}, {}, _diagnostic(), _diagnostic(), _diagnostic()],
            ["存在未标明原因代码的诊断数据", "原因 A 存在重复诊断数据"],
        ),
    ],
)
def test_diagnostic_consistency_preserves_complete_result(
    diagnostics: list[dict[str, Any]],
    expected: list[str],
) -> None:
    evidence = {"analysis": {"reasons": [_reason()], "diagnostics": diagnostics}}
    before = deepcopy(evidence)
    actual = _report_consistency({}, evidence, require_information_diagnostics=True)
    assert actual == {"status": "blocked" if expected else "passed", "issues": expected}
    assert evidence == before


@pytest.mark.parametrize(
    ("percentage", "expected"),
    [
        (0, []),
        (0.049999, []),
        (0.05, []),
        (-0.05, []),
        (0.050001, ["诊断原因 A 的占比与分类结果不一致"]),
        (-0.050001, ["诊断原因 A 的占比与分类结果不一致"]),
    ],
)
def test_percentage_tolerance_preserves_unrounded_boundary(
    percentage: float,
    expected: list[str],
) -> None:
    evidence = {
        "analysis": {
            "reasons": [_reason()],
            "diagnostics": [
                _diagnostic(selected_reason=_reason(percentage=percentage))
            ],
        }
    }
    assert _report_consistency({}, evidence, require_information_diagnostics=True) == {
        "status": "blocked" if expected else "passed",
        "issues": expected,
    }


@pytest.mark.parametrize(
    ("selected", "blocked"), [(24.25, True), (24.15, True), (24.249999, False)]
)
def test_percentage_boundary_keeps_existing_float_precision(
    selected: float,
    blocked: bool,
) -> None:
    evidence = {
        "analysis": {
            "reasons": [_reason(percentage=24.2)],
            "diagnostics": [_diagnostic(selected_reason=_reason(percentage=selected))],
        }
    }
    expected = ["诊断原因 A 的占比与分类结果不一致"] if blocked else []
    assert _report_consistency({}, evidence, require_information_diagnostics=True) == {
        "status": "blocked" if blocked else "passed",
        "issues": expected,
    }


@pytest.mark.parametrize("field", ["record_count", "percentage"])
def test_invalid_numeric_values_keep_conversion_errors(field: str) -> None:
    evidence = {
        "analysis": {
            "reasons": [_reason()],
            "diagnostics": [_diagnostic(selected_reason=_reason(**{field: "invalid"}))],
        }
    }
    with pytest.raises(ValueError, match="invalid"):
        _report_consistency({}, evidence, require_information_diagnostics=True)


@pytest.mark.parametrize(
    ("finding", "expected"),
    [
        ({"kind": "diagnostic"}, []),
        ({}, []),
        ({"kind": "information", "evidence_ids": ["reason.A", "scope"]}, []),
        ({"kind": "information"}, ["信息诊断未绑定唯一的分类原因"]),
        (
            {"kind": "information", "evidence_ids": ["scope"]},
            ["信息诊断未绑定唯一的分类原因"],
        ),
        (
            {"kind": "information", "evidence_ids": ["reason.A", "reason.A"]},
            ["信息诊断未绑定唯一的分类原因"],
        ),
        (
            {"kind": "information", "evidence_ids": ["reason.A", "reason.B"]},
            ["信息诊断未绑定唯一的分类原因"],
        ),
        (
            {"kind": "information", "evidence_ids": ["reason.B"]},
            ["信息诊断原因 B 不在分类结果中", "信息诊断原因 B 缺少语义诊断数据"],
        ),
        (
            {"kind": "information", "evidence_ids": ["reason."]},
            ["信息诊断原因  不在分类结果中", "信息诊断原因  缺少语义诊断数据"],
        ),
    ],
)
def test_information_bindings_preserve_complete_result(
    finding: dict[str, Any],
    expected: list[str],
) -> None:
    content = {"findings": [finding]}
    evidence = {"analysis": {"reasons": [_reason()], "diagnostics": [_diagnostic()]}}
    before = deepcopy((content, evidence))
    assert _report_consistency(
        content, evidence, require_information_diagnostics=True
    ) == {
        "status": "blocked" if expected else "passed",
        "issues": expected,
    }
    assert (content, evidence) == before


@pytest.mark.parametrize("required", [True, False])
@pytest.mark.parametrize("registered", [True, False])
def test_missing_diagnostic_requirement_and_registration_order(
    required: bool,
    registered: bool,
) -> None:
    content = {"findings": [{"kind": "information", "evidence_ids": ["reason.B"]}]}
    evidence = {
        "analysis": {
            "reasons": [],
            "diagnostics": [_diagnostic(reason_code="B")] if registered else [],
        }
    }
    expected = ["诊断原因 B 不在分类结果中"] if registered else []
    expected.append("信息诊断原因 B 不在分类结果中")
    if required and not registered:
        expected.append("信息诊断原因 B 缺少语义诊断数据")
    assert _report_consistency(
        content, evidence, require_information_diagnostics=required
    ) == {
        "status": "blocked",
        "issues": expected,
    }


def test_last_reason_and_first_diagnostic_remain_authoritative() -> None:
    evidence = {
        "analysis": {
            "reasons": [_reason(record_count=99), _reason(), _reason(value="")],
            "diagnostics": [
                _diagnostic(),
                _diagnostic(selected_reason=_reason(record_count=99)),
            ],
        }
    }
    assert _report_consistency({}, evidence, require_information_diagnostics=True) == {
        "status": "blocked",
        "issues": ["原因 A 存在重复诊断数据"],
    }


def test_multiple_errors_preserve_order_and_remove_duplicates() -> None:
    finding = {"kind": "information", "evidence_ids": ["reason.B"]}
    content = {"findings": [finding, finding, {"kind": "information"}]}
    evidence = {
        "analysis": {
            "reasons": [_reason()],
            "diagnostics": [
                {},
                _diagnostic(
                    selected_reason=_reason(value="B", record_count=3, percentage=1)
                ),
                _diagnostic(),
            ],
        }
    }
    before = deepcopy((content, evidence))
    assert _report_consistency(
        content, evidence, require_information_diagnostics=True
    ) == {
        "status": "blocked",
        "issues": [
            "存在未标明原因代码的诊断数据",
            "诊断原因 A 与选中原因不一致",
            "诊断原因 A 的记录数与分类结果不一致",
            "诊断原因 A 的占比与分类结果不一致",
            "原因 A 存在重复诊断数据",
            "信息诊断原因 B 不在分类结果中",
            "信息诊断原因 B 缺少语义诊断数据",
            "信息诊断未绑定唯一的分类原因",
        ],
    }
    assert (content, evidence) == before


@pytest.mark.parametrize("required", [True, False])
def test_empty_report_and_service_alias_preserve_contract(required: bool) -> None:
    expected = {"status": "passed", "issues": []}
    assert (
        _report_consistency({}, {}, require_information_diagnostics=required)
        == expected
    )
    assert (
        InsightReportService._report_consistency(
            {}, {}, require_information_diagnostics=required
        )
        == expected
    )
    assert InsightReportService._decision_report_consistency({}, {}) == expected


@pytest.mark.parametrize(
    ("actual", "expected"),
    [
        ([{"id": "A", "metrics": {"count": 2}, "evidence_ids": ["reason.A"]}], []),
        ([], ["问题列表或排序与确定性证据不一致"]),
        (
            [
                {"id": "B"},
                {"id": "A", "metrics": {"count": 2}, "evidence_ids": ["reason.A"]},
            ],
            ["问题列表或排序与确定性证据不一致"],
        ),
        (
            [{"id": "A", "metrics": {"count": 3}, "evidence_ids": ["reason.B"]}],
            ["问题 A 的指标与确定性证据不一致", "问题 A 的证据引用不一致"],
        ),
    ],
)
def test_decision_report_keeps_blueprint_checks_after_shared_consistency(
    actual: list[dict[str, Any]],
    expected: list[str],
) -> None:
    content = {
        "issues": actual,
        "findings": [{"kind": "information", "evidence_ids": ["reason.A"]}],
    }
    evidence = {
        "analysis": {"reasons": [_reason()], "diagnostics": []},
        "blueprint": {
            "issues": [
                {"id": "A", "metrics": {"count": 2}, "evidence_ids": ["reason.A"]}
            ]
        },
    }
    before = deepcopy((content, evidence))
    assert _decision_report_consistency(content, evidence) == {
        "status": "blocked" if expected else "passed",
        "issues": expected,
    }
    assert (content, evidence) == before
