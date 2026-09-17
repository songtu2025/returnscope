import json
from pathlib import Path

import pytest

from return_semantics.fact_pipeline import (
    FactDecisions,
    FactMappings,
    compile_dimension_decisions,
    compile_fact_classification,
)
from return_semantics.schemas import (
    ExtractedFact,
    FactMapping,
    ListingClaimsConfig,
    ModelClassification,
    SemanticDisposition,
    SemanticUnit,
    TaxonomyConfig,
)
from return_semantics.validator import validate_classification

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "semantic_scope_regression_v3.json"
CASES = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


CANDIDATE_LABELS = {
    "R1B9DI8P9Y19CJ": {"F10": "TOUCH_POSITIVE", "F11": "TOUCH_NEGATIVE"},
    "R3U23YRWVG78N7": {
        "F5": "TOUCH_POSITIVE",
        "F6": "TOUCH_NEGATIVE",
        "F7": "TOUCH_POSITIVE",
    },
    "R1KF6WL1GJVV4C": {"F3": "SIZE_FIT", "F4": "SIZE_SMALL"},
    "R2O0SBDV84OWF6": {"F17": "SIZE_LARGE"},
    "RV4RDGT5QHZFG": {"F4": "WATER_POSITIVE", "F14": "WATER_NEGATIVE"},
    "R1SFQQ5T5U9SXE": {"F7": "WARM_NEGATIVE", "F9": "WARM_POSITIVE"},
    "R1JJGWQ05Q0ZYY": {"F3": "SIZE_TIGHT", "F4": "SIZE_LOOSE"},
}


DECISIONS = {
    "R1B9DI8P9Y19CJ": [
        ("TOUCH", "TOUCH_NEGATIVE", ["F11"], ["F10"]),
    ],
    "R3U23YRWVG78N7": [
        ("TOUCH", "TOUCH_NEGATIVE", ["F6"], ["F5", "F7"]),
    ],
    "R1KF6WL1GJVV4C": [
        ("SIZE_ACTUAL", "SIZE_FIT", ["F3"], []),
        ("SIZE_CALIBRATION", "SIZE_SMALL", ["F4"], []),
    ],
    "R2O0SBDV84OWF6": [
        ("SIZE_ACTUAL", "SIZE_LARGE", ["F17"], []),
    ],
    "RV4RDGT5QHZFG": [
        ("WATER", "WATER_POSITIVE", ["F4"], []),
        ("WATER", "WATER_NEGATIVE", ["F14"], []),
    ],
    "R1SFQQ5T5U9SXE": [
        ("WARM", "WARM_NEGATIVE", ["F7"], []),
        ("WARM", "WARM_POSITIVE", ["F9"], []),
    ],
    "R1JJGWQ05Q0ZYY": [
        ("SIZE_ACTUAL", "SIZE_TIGHT", ["F3"], []),
        ("SIZE_ACTUAL", "SIZE_LOOSE", ["F4"], []),
    ],
}


REFERENCE_BASIS = {
    "ACTUAL_FIT": "NONE",
    "APPEARANCE_ONLY": "NONE",
    "FUTURE_USE": "NONE",
    "PURCHASE_ADVICE": "OTHER_PERSON",
    "PURCHASE_INTENT": "PERSONAL_PREFERENCE",
    "SIZE_CHART": "SIZE_CHART",
}


def _taxonomy() -> TaxonomyConfig:
    labels = [
        ("TOUCH_POSITIVE", "触屏灵敏", "TOUCH", ["POSITIVE"]),
        ("TOUCH_NEGATIVE", "触屏不灵敏", "TOUCH", ["NEGATIVE"]),
        ("SIZE_FIT", "合身", "SIZE_ACTUAL", ["POSITIVE"]),
        ("SIZE_SMALL", "标称偏小", "SIZE_CALIBRATION", ["NEGATIVE"]),
        ("SIZE_LARGE", "偏大", "SIZE_ACTUAL", ["NEGATIVE"]),
        ("SIZE_TIGHT", "偏紧", "SIZE_ACTUAL", ["NEGATIVE"]),
        ("SIZE_LOOSE", "偏松", "SIZE_ACTUAL", ["NEGATIVE"]),
        ("WATER_POSITIVE", "防水", "WATER", ["POSITIVE"]),
        ("WATER_NEGATIVE", "不防水", "WATER", ["NEGATIVE"]),
        ("WARM_POSITIVE", "保暖", "WARM", ["POSITIVE"]),
        ("WARM_NEGATIVE", "不保暖", "WARM", ["NEGATIVE"]),
    ]
    return TaxonomyConfig.model_validate(
        {
            "version": "semantic-scope-regression-v3",
            "structure_version": 2,
            "recognition_profile": "fact_v2",
            "agent_family": "测试",
            "product_context": "手套",
            "allowed_parts": ["UNSPECIFIED"],
            "categories": [
                {"code": "PRODUCT", "name": "商品"},
                {"code": "TOUCH", "name": "触屏灵敏性", "parent_code": "PRODUCT"},
                {"code": "SIZE", "name": "尺码", "parent_code": "PRODUCT"},
                {
                    "code": "SIZE_ACTUAL",
                    "name": "实际适配",
                    "parent_code": "SIZE",
                },
                {
                    "code": "SIZE_CALIBRATION",
                    "name": "尺码标定",
                    "parent_code": "SIZE",
                },
                {"code": "WATER", "name": "防水性", "parent_code": "PRODUCT"},
                {"code": "WARM", "name": "保暖性", "parent_code": "PRODUCT"},
            ],
            "validation_rules": {
                "dimension_contracts": [
                    {
                        "parent_code": "TOUCH",
                        "verdict_label_codes": [
                            "TOUCH_POSITIVE",
                            "TOUCH_NEGATIVE",
                        ],
                        "scope_fields": [
                            "experiencer_ref",
                            "product_ref",
                            "variant_ref",
                            "event_ref",
                        ],
                    },
                    {
                        "parent_code": "SIZE_ACTUAL",
                        "verdict_label_codes": [
                            "SIZE_FIT",
                            "SIZE_LARGE",
                            "SIZE_TIGHT",
                            "SIZE_LOOSE",
                        ],
                        "scope_fields": [
                            "experiencer_ref",
                            "product_ref",
                            "variant_ref",
                            "event_ref",
                            "reference_basis",
                        ],
                    },
                    {
                        "parent_code": "SIZE_CALIBRATION",
                        "verdict_label_codes": ["SIZE_SMALL"],
                        "scope_fields": [
                            "product_ref",
                            "variant_ref",
                            "event_ref",
                            "reference_basis",
                        ],
                    },
                    {
                        "parent_code": "WATER",
                        "verdict_label_codes": [
                            "WATER_POSITIVE",
                            "WATER_NEGATIVE",
                        ],
                        "scope_fields": [
                            "experiencer_ref",
                            "product_ref",
                            "variant_ref",
                            "event_ref",
                            "condition",
                        ],
                    },
                    {
                        "parent_code": "WARM",
                        "verdict_label_codes": [
                            "WARM_POSITIVE",
                            "WARM_NEGATIVE",
                        ],
                        "scope_fields": [
                            "experiencer_ref",
                            "product_ref",
                            "variant_ref",
                            "event_ref",
                            "condition",
                        ],
                    },
                ]
            },
            "labels": [
                {
                    "code": code,
                    "name": name,
                    "parent_code": parent,
                    "allowed_sentiments": sentiments,
                }
                for code, name, parent, sentiments in labels
            ],
        }
    )


def _fact(case: dict, item: dict) -> ExtractedFact:
    actor_ref = item.get("actor_ref", "REVIEWER")
    role = item["expected_role"]
    return ExtractedFact.model_validate(
        {
            "fact_id": item["fact_id"],
            "actor_ref": actor_ref,
            "source_ref": "REVIEWER",
            "experiencer_ref": actor_ref,
            "product_ref": "CURRENT",
            "variant_ref": item.get("variant_ref", "UNSPECIFIED"),
            "event_ref": "E1",
            "reference_basis": REFERENCE_BASIS.get(
                item.get("reference_basis", "NONE"),
                item.get("reference_basis", "NONE"),
            ),
            "fact_role": "CONTEXT" if role in {"CONTEXT", "ABSTAIN"} else "CONCLUSION",
            "statement_type": item["statement_type"],
            "opinion": item["evidence"],
            "sentiment": item["sentiment"],
            "part": "UNSPECIFIED",
            "operation": item.get("operation", ""),
            "condition": item.get("condition", ""),
            "candidate_branch_codes": [],
            "evidence_spans": [{"text": item["evidence"]}],
        }
    )


def _mapping(case: dict, fact: ExtractedFact) -> FactMapping:
    candidate = CANDIDATE_LABELS[case["sample_id"]].get(fact.fact_id)
    if candidate:
        return FactMapping(fact_id=fact.fact_id, label_codes=[candidate])
    fixture_fact = next(
        item for item in case["facts"] if item["fact_id"] == fact.fact_id
    )
    disposition = (
        SemanticDisposition.EXPECTED_ABSTENTION
        if fixture_fact["expected_role"] == "ABSTAIN"
        else SemanticDisposition.EVIDENCE_ONLY
    )
    return FactMapping(
        fact_id=fact.fact_id,
        reason="该事实只作上下文或正常弃权",
        disposition=disposition,
    )


def _decision_scope(fact: ExtractedFact, parent_code: str) -> dict:
    scope = {
        "experiencer_ref": fact.experiencer_ref,
        "product_ref": fact.product_ref,
        "variant_ref": fact.variant_ref,
        "event_ref": fact.event_ref,
    }
    if parent_code == "SIZE_ACTUAL":
        scope["reference_basis"] = fact.reference_basis.value
    if parent_code == "SIZE_CALIBRATION":
        scope.pop("experiencer_ref")
        scope["reference_basis"] = fact.reference_basis.value
    if parent_code in {"WATER", "WARM"}:
        scope["condition"] = fact.condition
    return scope


def _compile(case: dict):
    taxonomy = _taxonomy()
    facts = [_fact(case, item) for item in case["facts"]]
    facts_by_id = {fact.fact_id: fact for fact in facts}
    mappings = [_mapping(case, fact) for fact in facts]
    comment = " ".join(item["evidence"] for item in case["facts"])
    classification = compile_fact_classification(
        facts,
        FactMappings(mappings=mappings),
        comment=comment,
        taxonomy=taxonomy,
        allowed={
            fact.fact_id: mapping.label_codes
            for fact, mapping in zip(facts, mappings, strict=True)
        },
    )
    decisions = []
    for parent, label, supporting_ids, context_ids in DECISIONS[case["sample_id"]]:
        anchor = facts_by_id[supporting_ids[0]]
        decisions.append(
            {
                "parent_code": parent,
                "scope": _decision_scope(anchor, parent),
                "verdict_label_code": label,
                "supporting_fact_ids": supporting_ids,
                "context_fact_ids": context_ids,
                "reason": "按事实作用域和完整命题生成唯一业务结论",
            }
        )
    decided = compile_dimension_decisions(
        classification,
        FactDecisions.model_validate({"decisions": decisions}),
        comment=comment,
        taxonomy=taxonomy,
    )
    result = validate_classification(
        classification_key=case["sample_id"],
        comment=comment,
        reason="",
        model_result=decided,
        taxonomy=taxonomy,
        claims=ListingClaimsConfig(version="none", claims=[]),
        model_name="fixture",
        prompt_version="fixture-v3",
        analysis_context="review",
    )
    return decided, result


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["sample_id"])
def test_semantic_scope_regression(case: dict) -> None:
    decided, result = _compile(case)
    expected = case["expected"]

    assert [unit.label_code for unit in decided.semantic_units] == expected[
        "terminal_labels"
    ]
    assert [unit.label_code for unit in result.semantic_units] == expected[
        "terminal_labels"
    ]
    assert result.comment_summary.status.value == expected["comment_status"]
    assert len(decided.dimension_decisions) == len(DECISIONS[case["sample_id"]])
    assert all(
        code not in {unit.label_code for unit in result.semantic_units}
        for code in expected["excluded_labels"]
    )
    expected_abstentions = set(expected.get("expected_abstention_fact_ids", []))
    actual_abstentions = {
        item.fact_id
        for item in result.unknown_semantics
        if item.disposition == SemanticDisposition.EXPECTED_ABSTENTION
    }
    assert expected_abstentions <= actual_abstentions
    if expected_abstentions:
        assert decided.needs_review is False
        assert not any(
            item.disposition
            in {
                SemanticDisposition.TAXONOMY_GAP,
                SemanticDisposition.MAPPING_UNCERTAIN,
            }
            for item in result.unknown_semantics
        )
    expected_relations = expected.get("relation_types")
    if expected_relations is not None:
        assert [
            relation.relation_type.value for relation in result.semantic_relations
        ] == expected_relations


def test_legacy_semantic_unit_defaults_new_scope_fields() -> None:
    unit = SemanticUnit.model_validate(
        {
            "subject": "PRODUCT",
            "label_code": "SIZE_FIT",
            "opinion": "Fits well.",
            "sentiment": "POSITIVE",
            "assertion": "AFFIRMED",
            "part": "UNSPECIFIED",
            "evidence": "Fits well.",
            "implicit": False,
        }
    )
    result = ModelClassification.model_validate({"semantic_units": [unit]})

    assert unit.actor_ref == "REVIEWER"
    assert unit.source_ref == "REVIEWER"
    assert unit.experiencer_ref == "REVIEWER"
    assert unit.variant_ref == "UNSPECIFIED"
    assert unit.reference_basis.value == "NONE"
    assert result.dimension_decisions == []
