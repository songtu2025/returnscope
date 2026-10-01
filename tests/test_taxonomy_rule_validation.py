import copy
from typing import Any

import pytest
from pydantic import ValidationError

from return_semantics.schemas import TaxonomyConfig


def _taxonomy_payload(structure_version: int) -> dict[str, Any]:
    labels = [
        {
            "code": code,
            "name": code,
            "group": group,
            "allowed_sentiments": ["NEGATIVE"],
        }
        for code, group in [("A", "功能"), ("B", "功能"), ("C", "质量")]
    ]
    categories = []
    if structure_version == 2:
        categories = [
            {"code": "ROOT", "name": "功能"},
            {"code": "CHILD", "name": "子维度", "parent_code": "ROOT"},
            {"code": "OTHER", "name": "质量"},
        ]
        for label, parent in zip(labels, ["CHILD", "CHILD", "OTHER"], strict=True):
            label["parent_code"] = parent
            label["group"] = "旧分组"
    return {
        "version": "rule-test",
        "structure_version": structure_version,
        "agent_family": "测试",
        "product_context": "测试商品",
        "categories": categories,
        "labels": labels,
        "validation_rules": {"allowed_groups": ["功能", "质量"]},
    }


def _contract(**updates: Any) -> dict[str, Any]:
    return {
        "parent_code": "CHILD",
        "verdict_label_codes": ["A", "B"],
        "scope_fields": ["product_ref"],
        **updates,
    }


RULE_REFERENCES = [
    ("opposite_reason_labels", {"原因": ["A"]}),
    ("conflicting_label_sets", [["A", "B"]]),
    (
        "evidence_requirements",
        [
            {
                "label_code": "A",
                "cues": ["测试"],
                "unknown_opinion": "观点",
                "unknown_reason": "原因",
            }
        ],
    ),
    ("implicit_evidence_rules", [{"label_code": "A", "cues": ["测试"]}]),
    (
        "claim_evidence_requirements",
        [{"label_code": "A", "claim_id": "声明", "cues": ["测试"]}],
    ),
    ("neutral_reason_labels", ["A"]),
    ("required_review_labels", ["A"]),
    ("boundary_required_labels", ["A"]),
    ("fallback_label_codes", ["A"]),
]


def _unknown_rule_value(value: Any) -> Any:
    if isinstance(value, str):
        return "MISSING" if value == "A" else value
    if isinstance(value, list):
        return [_unknown_rule_value(item) for item in value]
    return {key: _unknown_rule_value(item) for key, item in value.items()}


@pytest.mark.parametrize("structure_version", [1, 2])
@pytest.mark.parametrize("neutral_labels", [None, [], ["A"]])
def test_valid_rules_preserve_groups_and_roundtrip(
    structure_version: int, neutral_labels: list[str] | None
) -> None:
    payload = _taxonomy_payload(structure_version)
    payload["validation_rules"].update(dict(copy.deepcopy(RULE_REFERENCES)))
    payload["validation_rules"]["neutral_reason_labels"] = neutral_labels
    if structure_version == 2:
        payload["validation_rules"]["allowed_groups"] = ["旧分组"]
    original = copy.deepcopy(payload)

    taxonomy = TaxonomyConfig.model_validate(payload)

    assert payload == original
    assert [label.group for label in taxonomy.labels] == ["功能", "功能", "质量"]
    assert taxonomy.validation_rules.neutral_reason_labels == neutral_labels
    assert taxonomy.validation_rules.model_dump()["dimension_contracts"] == []
    assert TaxonomyConfig.model_validate_json(taxonomy.model_dump_json()) == taxonomy


@pytest.mark.parametrize("structure_version", [1, 2])
@pytest.mark.parametrize("field,value", RULE_REFERENCES)
def test_all_rule_reference_sources_reject_unknown_labels(
    structure_version: int, field: str, value: Any
) -> None:
    payload = _taxonomy_payload(structure_version)
    payload["validation_rules"][field] = _unknown_rule_value(value)

    with pytest.raises(ValidationError) as caught:
        TaxonomyConfig.model_validate(payload)

    assert caught.value.errors()[0]["msg"] == (
        "Value error, 校验规则引用了未知标签: ['MISSING']"
    )


CONTRACT_CASES = [
    (
        [_contract(parent_code="Z"), _contract(parent_code="D")],
        "维度裁决契约引用了未知分类: ['D', 'Z']",
    ),
    ([_contract(), _contract()], "同一分类只能配置一条维度裁决契约"),
    ([_contract(verdict_label_codes=["A", "A"])], "维度裁决契约的结论标签不能重复"),
    (
        [_contract(scope_fields=["product_ref", "product_ref"])],
        "维度裁决契约的作用域字段不能重复",
    ),
    (
        [_contract(verdict_label_codes=["Z", "D"])],
        "维度裁决契约引用了未知标签: ['Z', 'D']",
    ),
    ([_contract(verdict_label_codes=["C"])], "维度结论标签不属于配置父级: ['C']"),
    (
        [_contract(), _contract(parent_code="ROOT")],
        "维度裁决契约不能重叠管理同一标签: A",
    ),
]


@pytest.mark.parametrize("contracts,message", CONTRACT_CASES)
def test_dimension_contract_validation_errors(
    contracts: list[dict[str, Any]], message: str
) -> None:
    payload = _taxonomy_payload(2)
    payload["validation_rules"]["dimension_contracts"] = copy.deepcopy(contracts)

    with pytest.raises(ValidationError) as caught:
        TaxonomyConfig.model_validate(payload)

    assert caught.value.errors()[0]["msg"] == f"Value error, {message}"


def test_dimension_contracts_accept_ancestors_and_separate_branches() -> None:
    payload = _taxonomy_payload(2)
    payload["validation_rules"]["dimension_contracts"] = [
        _contract(parent_code="ROOT"),
        _contract(parent_code="OTHER", verdict_label_codes=["C"]),
    ]
    taxonomy = TaxonomyConfig.model_validate(payload)

    assert (
        taxonomy.validation_rules.model_dump()["dimension_contracts"]
        == (payload["validation_rules"]["dimension_contracts"])
    )
    assert TaxonomyConfig.model_validate_json(taxonomy.model_dump_json()) == taxonomy


@pytest.mark.parametrize("structure_version", [1, 2])
@pytest.mark.parametrize("codes", [[], ["A"], ["A", "A"]])
def test_conflicting_groups_require_two_distinct_labels(
    structure_version: int, codes: list[str]
) -> None:
    payload = _taxonomy_payload(structure_version)
    payload["validation_rules"]["conflicting_label_sets"] = [codes]

    with pytest.raises(ValidationError) as caught:
        TaxonomyConfig.model_validate(payload)

    assert caught.value.errors()[0]["msg"] == (
        "Value error, 冲突标签组至少需要两个不同标签"
    )


PRIORITY_CASES = [
    (
        1,
        {"categories": [{"code": "ROOT", "name": "功能"}]},
        {},
        "层级标签必须使用 structure_version=2",
    ),
    (
        1,
        {
            "labels": [
                {
                    "code": "A",
                    "name": "A",
                    "parent_code": "ROOT",
                    "allowed_sentiments": ["NEGATIVE"],
                }
            ]
        },
        {},
        "层级标签必须使用 structure_version=2",
    ),
    (1, {}, {"allowed_groups": ["旧分组"]}, "标签分组必须来自标准规定的业务分组"),
    (1, {}, {"dimension_contracts": [_contract()]}, "维度裁决契约仅适用于层级标签"),
    (
        2,
        {"categories": [{"code": "ROOT", "name": "功能", "parent_code": "MISSING"}]},
        {"fallback_label_codes": ["MISSING"]},
        "分类父节点不存在: MISSING",
    ),
    (
        2,
        {},
        {
            "fallback_label_codes": ["Z", "D", "Z"],
            "dimension_contracts": [_contract(parent_code="MISSING")],
        },
        "校验规则引用了未知标签: ['D', 'Z']",
    ),
    (
        2,
        {},
        {
            "dimension_contracts": [
                _contract(parent_code="MISSING"),
                _contract(parent_code="MISSING", verdict_label_codes=["A", "A"]),
            ]
        },
        "维度裁决契约引用了未知分类: ['MISSING']",
    ),
    (
        2,
        {},
        {
            "dimension_contracts": [
                _contract(verdict_label_codes=["A", "A"]),
                _contract(),
            ]
        },
        "同一分类只能配置一条维度裁决契约",
    ),
    (
        2,
        {},
        {
            "dimension_contracts": [
                _contract(
                    verdict_label_codes=["Z", "Z"],
                    scope_fields=["product_ref", "product_ref"],
                )
            ]
        },
        "维度裁决契约的结论标签不能重复",
    ),
    (
        2,
        {},
        {
            "dimension_contracts": [
                _contract(
                    verdict_label_codes=["Z"],
                    scope_fields=["product_ref", "product_ref"],
                )
            ]
        },
        "维度裁决契约的作用域字段不能重复",
    ),
    (
        2,
        {},
        {"dimension_contracts": [_contract(verdict_label_codes=["C", "Z"])]},
        "维度裁决契约引用了未知标签: ['Z']",
    ),
    (
        2,
        {},
        {
            "dimension_contracts": [
                _contract(verdict_label_codes=["C"]),
                _contract(parent_code="ROOT"),
            ]
        },
        "维度结论标签不属于配置父级: ['C']",
    ),
    (
        2,
        {},
        {"dimension_contracts": [_contract(), _contract(parent_code="ROOT")]},
        "维度裁决契约不能重叠管理同一标签: A",
    ),
    (
        2,
        {},
        {
            "dimension_contracts": [
                _contract(scope_fields=["product_ref", "product_ref"]),
                _contract(parent_code="OTHER", verdict_label_codes=["C", "C"]),
            ]
        },
        "维度裁决契约的作用域字段不能重复",
    ),
]


@pytest.mark.parametrize("version,updates,rules,message", PRIORITY_CASES)
def test_validation_preserves_first_error_priority(
    version: int,
    updates: dict[str, Any],
    rules: dict[str, Any],
    message: str,
) -> None:
    payload = _taxonomy_payload(version)
    payload.update(copy.deepcopy(updates))
    # 冲突组错误放在最后，前面的结构、引用和契约错误必须优先返回。
    payload["validation_rules"].update(
        {"conflicting_label_sets": [["A"]], **copy.deepcopy(rules)}
    )
    with pytest.raises(ValidationError) as caught:
        TaxonomyConfig.model_validate(payload)

    errors = caught.value.errors()
    assert len(errors) == 1
    assert errors[0]["loc"] == ()
    assert errors[0]["type"] == "value_error"
    assert errors[0]["msg"] == f"Value error, {message}"
