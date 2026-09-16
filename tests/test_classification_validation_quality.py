from copy import deepcopy

import pytest

from web_backend.classification_validation_quality import (
    ERROR_METRICS,
    FACT_QUALITY_POLICY,
    METRIC_LABELS,
    SCOPE_FIELDS,
    _fact_pairs,
    append_reference_fact,
    compare_reference,
    evaluate_references,
    publication_quality_gate,
    quality_gate,
)


def _unit(evidence="The glove is warm.", **changes):
    return {
        "label_code": "WARM",
        "sentiment": "POSITIVE",
        "part": "UNSPECIFIED",
        "subject": "PRODUCT",
        "condition": "",
        "evidence": evidence,
        **changes,
    }


def _item(expected=None, actual=None):
    unit = _unit()
    return {
        "comment": "The glove is warm. My fingers are warm. The palm is warm.",
        "reference": {
            "ambiguous": False,
            "units": [unit] if expected is None else expected,
        },
        "draft": {
            "status": "AUTO_APPROVED",
            "semantic_units": [unit] if actual is None else actual,
        },
        "baseline": {"status": "AUTO_APPROVED", "semantic_units": []},
    }


def _fact(fact_id="f1", **changes):
    return {
        "fact_id": fact_id,
        "statement_type": "EXPERIENCE",
        "actor_ref": "reviewer",
        "product_ref": "current",
        "event_ref": "first_use",
        "subject": "PRODUCT",
        "condition": "",
        "sentiment": "POSITIVE",
        "part": "UNSPECIFIED",
        "evidence_spans": [{"text": "The glove is warm."}],
        **changes,
    }


def _with_state(item):
    append_reference_fact(
        item["reference"],
        {
            "事实状态": "EXPERIENCE",
            "证据": "The glove is warm.",
            "事件": "E1",
            "条件": "无",
            "责任主体": "PRODUCT",
            "是否主因": "否",
        },
        "one",
        "WARM",
    )
    item["draft"]["extracted_facts"] = [_fact()]
    item["draft"]["fact_mappings"] = [{"fact_id": "f1", "label_codes": ["WARM"]}]
    return item


def test_duplicate_instances_are_not_swallowed_by_sets():
    counts = compare_reference(_item(actual=[_unit(), _unit()]), "draft")
    assert counts["extra_labels"] == 1
    assert counts["duplicate_units"] == 1
    assert counts["exact_label_samples"] == 0


def test_repeated_reference_instances_require_multiple_outputs():
    expected = [
        _unit("My fingers are warm.", part="FINGER"),
        _unit("The palm is warm.", part="PALM"),
    ]
    counts = compare_reference(_item(expected, expected[:1]), "draft")
    assert counts["missing_labels"] == 1
    assert counts["exact_label_samples"] == 0
    assert compare_reference(_item(expected, expected), "draft")["duplicate_units"] == 0


def test_explicit_part_is_matched_before_wildcard():
    expected = [_unit(), _unit(part="FINGER")]
    actual = [_unit(part="FINGER"), _unit(part="PALM")]
    assert compare_reference(_item(expected, actual), "draft")["part_errors"] == 0


def test_evidence_extension_is_valid_but_unrelated_span_is_not():
    item = _item(actual=[_unit("The glove is warm. My fingers are warm.")])
    assert compare_reference(item, "draft")["evidence_errors"] == 0
    item["draft"]["semantic_units"][0]["evidence"] = "The palm is warm."
    assert compare_reference(item, "draft")["evidence_errors"] == 1
    item["draft"]["semantic_units"][0]["evidence"] = "invented"
    assert compare_reference(item, "draft")["evidence_errors"] == 1


def test_terminal_punctuation_does_not_change_evidence_support():
    item = _with_state(_item(actual=[_unit("The glove is warm")]))
    item["draft"]["extracted_facts"][0]["evidence_spans"] = [
        {"text": "The glove is warm"}
    ]
    counts = compare_reference(item, "draft")
    assert counts["evidence_errors"] == counts["statement_type_errors"] == 0


def test_fact_location_does_not_relax_evidence_support():
    item = _with_state(_item(actual=[_unit()]))
    longer = "The glove is warm. My fingers are warm."
    item["reference"]["units"][0]["evidence"] = longer
    item["reference"]["facts"][0]["evidence"] = longer
    counts = compare_reference(item, "draft")
    assert counts["statement_type_errors"] == 0
    assert counts["evidence_errors"] == 1


def test_reference_order_cannot_steal_exact_state_match():
    item = _with_state(_item(expected=[], actual=[]))
    item["reference"]["facts"][0].update(
        expected_statement_type="PREDICTION", label_codes=[]
    )
    item["reference"]["facts"].append(
        {**item["reference"]["facts"][0], "expected_statement_type": "NOT_TESTED"}
    )
    item["draft"]["extracted_facts"] = [
        _fact(statement_type="NOT_TESTED"),
        _fact("f2", statement_type="HYPOTHESIS"),
    ]
    item["draft"]["fact_mappings"].append({"fact_id": "f2", "label_codes": ["WARM"]})
    assert compare_reference(item, "draft")["statement_type_errors"] == 1


def test_fact_with_title_and_partial_body_can_be_located():
    item = _with_state(_item(actual=[_unit()]))
    item["comment"] = "Warm gloves\n" + item["comment"]
    item["reference"]["facts"][0]["evidence"] = (
        "The glove is warm. My fingers are warm."
    )
    item["draft"]["extracted_facts"][0]["evidence_spans"] = [
        {"text": "Warm gloves\nThe glove is warm."}
    ]
    assert compare_reference(item, "draft")["statement_type_errors"] == 0


def test_different_evidence_same_event_is_duplicate_but_different_actor_is_not():
    item = _with_state(_item(actual=[_unit(), _unit("My fingers are warm.")]))
    item["draft"]["extracted_facts"].append(
        _fact("f2", evidence_spans=[{"text": "My fingers are warm."}])
    )
    item["draft"]["fact_mappings"].append({"fact_id": "f2", "label_codes": ["WARM"]})
    assert compare_reference(item, "draft")["duplicate_units"] == 1
    item["draft"]["extracted_facts"][1]["actor_ref"] = "child"
    assert compare_reference(item, "draft")["duplicate_units"] == 0


def test_mapping_trace_duplicates_do_not_mean_final_output_duplicates():
    item = _with_state(_item())
    item["draft"]["extracted_facts"].append(_fact("f2"))
    item["draft"]["fact_mappings"].append({"fact_id": "f2", "label_codes": ["WARM"]})
    assert compare_reference(item, "draft")["duplicate_units"] == 0


def test_reference_state_and_explicit_objects_are_compared():
    item = _with_state(_item())
    item["reference"]["facts"][0].update(
        expected_actor_ref="child", expected_product_ref="other"
    )
    item["draft"]["extracted_facts"][0]["statement_type"] = "PREDICTION"
    counts = compare_reference(item, "draft")
    assert counts["statement_type_errors"] == 1
    assert counts["actor_errors"] == counts["product_errors"] == 1


def test_fact_matching_identity_precedes_statement_type():
    item = _with_state(_item())
    first = item["reference"]["facts"][0]
    first.update(expected_actor_ref="REVIEWER", expected_product_ref="CURRENT:1")
    item["reference"]["facts"].append(
        {
            **first,
            "expected_product_ref": "CURRENT:2",
            "expected_statement_type": "EVALUATION",
        }
    )
    item["draft"]["extracted_facts"] = [
        _fact(
            actor_ref="REVIEWER", product_ref="CURRENT:1", statement_type="EVALUATION"
        ),
        _fact(
            "f2",
            actor_ref="REVIEWER",
            product_ref="CURRENT:2",
            statement_type="EXPERIENCE",
        ),
    ]
    item["draft"]["fact_mappings"].append({"fact_id": "f2", "label_codes": ["WARM"]})
    counts = compare_reference(item, "draft")
    assert counts["product_errors"] == 0
    assert counts["statement_type_errors"] == 0


def test_fact_matching_exact_evidence_precedes_statement_type():
    item = _with_state(_item())
    item["draft"]["extracted_facts"] = [
        _fact(statement_type="PREDICTION"),
        _fact("f2", evidence_spans=[{"text": item["comment"]}]),
    ]
    item["draft"]["fact_mappings"].append({"fact_id": "f2", "label_codes": ["WARM"]})
    assert compare_reference(item, "draft")["statement_type_errors"] == 1


def test_shared_paragraph_evidence_uses_claim_anchor_not_no_label_preference():
    item = _with_state(_item())
    item["comment"] = "I kept one pair and sent back four pairs."
    item["reference"]["facts"][0].update(
        evidence="sent back four pairs", label_codes=[]
    )
    item["draft"]["extracted_facts"] = [
        _fact(opinion="kept one pair", evidence_spans=[{"text": item["comment"]}]),
        _fact(
            "f2",
            opinion="sent back four pairs",
            evidence_spans=[{"text": item["comment"]}],
        ),
    ]
    item["draft"]["fact_mappings"] = [
        {"fact_id": "f1", "label_codes": []},
        {"fact_id": "f2", "label_codes": ["COLD"]},
    ]
    assert _fact_pairs(item, "draft") == {0: 1}


def test_plan_in_broad_evidence_is_not_confirmed_without_its_mapping():
    item = _with_state(_item())
    item["reference"]["facts"][0].update(
        expected_statement_type="ADVICE", label_codes=[]
    )
    item["draft"]["extracted_facts"][0].update(
        statement_type="ADVICE", opinion="Plan to use"
    )
    item["draft"]["fact_mappings"][0]["label_codes"] = []
    item["draft"]["semantic_units"][0]["evidence"] = item["comment"]
    assert compare_reference(item, "draft")["plan_confirmation_errors"] == 0


def test_filtered_plan_mapping_does_not_borrow_another_facts_final_unit():
    item = _with_state(_item())
    item["reference"]["facts"][0].update(
        expected_statement_type="ADVICE", label_codes=[]
    )
    item["draft"]["extracted_facts"][0].update(
        statement_type="ADVICE", opinion="Plan to use"
    )
    item["draft"]["semantic_units"][0]["opinion"] = "Already warm"
    assert compare_reference(item, "draft")["plan_confirmation_errors"] == 0


@pytest.mark.parametrize(
    "state", ["INTENT", "PREDICTION", "HYPOTHESIS", "NOT_TESTED", "ADVICE"]
)
def test_nonconfirmed_reference_never_counts_filtered_mapping_as_confirmed(state):
    item = _with_state(_item(expected=[], actual=[]))
    item["reference"]["facts"][0].update(expected_statement_type=state, label_codes=[])
    item["draft"]["extracted_facts"][0]["statement_type"] = state
    assert compare_reference(item, "draft")["plan_confirmation_errors"] == 0
    item["draft"]["semantic_units"] = [_unit()]
    assert compare_reference(item, "draft")["plan_confirmation_errors"] == 1


def test_fact_policy_passes_twenty_fully_annotated_samples():
    items = [_with_state(_item()) for _ in range(20)]
    summary = {"reference_evaluation": evaluate_references(items)}
    gate = quality_gate(summary, FACT_QUALITY_POLICY)
    assert gate["passed"] is True
    assert gate["instance_match_rate"] == gate["reference_coverage"] == 100


def test_fact_policy_warns_for_incomplete_reference_dimensions():
    item = _with_state(_item())
    assert not quality_gate(
        {"reference_evaluation": evaluate_references([item])}, FACT_QUALITY_POLICY
    )["passed"]
    items = [deepcopy(item) for _ in range(20)]
    items[0]["reference"].pop("fact_state_complete")
    gate = quality_gate(
        {"reference_evaluation": evaluate_references(items)}, FACT_QUALITY_POLICY
    )
    assert gate["passed"]
    assert any("事实状态参考答案不完整" in warning for warning in gate["warnings"])
    items[0]["reference"]["ambiguous"] = True
    gate = quality_gate(
        {"reference_evaluation": evaluate_references(items)}, FACT_QUALITY_POLICY
    )
    assert gate["reference_coverage"] == 95
    assert gate["passed"] is True
    assert any("非歧义参考覆盖率 95.00%" in warning for warning in gate["warnings"])


def test_one_duplicate_in_twenty_warns_but_does_not_block():
    items = [_with_state(_item()) for _ in range(20)]
    items[0]["draft"]["semantic_units"].append(_unit())
    gate = quality_gate(
        {"reference_evaluation": evaluate_references(items)}, FACT_QUALITY_POLICY
    )
    assert gate["duplicate_rate"] == 5
    assert gate["passed"]
    assert any("重复" in warning for warning in gate["warnings"])


def test_fact_policy_applies_engineering_rate_boundaries():
    items = [_with_state(_item()) for _ in range(20)]
    for item in items[:4]:
        item["reference"]["ambiguous"] = True
    evaluation = evaluate_references(items)
    evaluation["sides"]["draft"].update(
        expected_instances=20,
        actual_instances=20,
        matched_instances=16,
        duplicate_samples=1,
    )
    gate = quality_gate({"reference_evaluation": evaluation}, FACT_QUALITY_POLICY)
    assert gate["passed"]
    assert gate["reference_coverage"] == 80
    assert gate["instance_match_rate"] == 80
    assert gate["duplicate_rate"] == pytest.approx(6.25)

    items[4]["reference"]["ambiguous"] = True
    evaluation = evaluate_references(items)
    evaluation["sides"]["draft"].update(
        expected_instances=20,
        actual_instances=20,
        matched_instances=15,
        duplicate_samples=2,
    )
    gate = quality_gate({"reference_evaluation": evaluation}, FACT_QUALITY_POLICY)
    assert not gate["passed"]
    assert gate["reference_coverage"] == 75
    assert gate["instance_match_rate"] == 75
    assert gate["duplicate_rate"] == pytest.approx(13.33, abs=0.01)


def test_fact_profile_cannot_bypass_gate_by_omitting_frozen_policy():
    assert not publication_quality_gate(
        {"taxonomy": {"recognition_profile": "fact_v2"}}, {}, [], {}
    )["passed"]
    legacy = publication_quality_gate(
        {"taxonomy": {"recognition_profile": "semantic_v1"}}, {}, [], {}
    )
    assert legacy["passed"] is True
    assert legacy["status"] == "not_configured"


def test_reference_fact_columns_validate_state_and_evidence():
    with pytest.raises(ValueError, match="事实状态无效"):
        append_reference_fact({}, {"事实状态": "wrong"}, "one", "无标签")
    with pytest.raises(ValueError, match="缺少证据"):
        append_reference_fact({}, {"事实状态": "EXPERIENCE"}, "one", "无标签")


def test_reference_parser_keeps_state_for_no_label_rows():
    from openpyxl import Workbook

    from web_backend.classification_standard_validation_service import (
        ClassificationStandardValidationService,
    )

    workbook = Workbook()
    sheet = workbook.create_sheet("人工参考答案")
    sheet.append(
        [
            "评论编号",
            "标签编码",
            "评价方向",
            "部位",
            "证据",
            "事实状态",
            "使用者",
            "商品对象",
        ]
    )
    sheet.append(
        ["one", "无标签", "", "", "not tried", "NOT_TESTED", "REVIEWER", "CURRENT"]
    )
    reference = ClassificationStandardValidationService._read_references(
        workbook, {"labels": [], "allowed_parts": ["UNSPECIFIED"]}
    )["one"]
    assert reference["units"] == []
    assert reference["fact_state_complete"] is True
    assert reference["facts"][0]["expected_statement_type"] == "NOT_TESTED"
    assert reference["facts"][0]["expected_actor_ref"] == "REVIEWER"


@pytest.mark.parametrize(
    "actor,product",
    [
        ("", ""),
        ("REVIEWER", "CURRENT"),
        ("OTHER:1", "CURRENT:2"),
        ("OTHER:12", "OTHER:3"),
    ],
)
def test_reference_object_identifiers_accept_canonical_values(actor, product):
    reference = {}
    append_reference_fact(
        reference,
        {
            "事实状态": "EXPERIENCE",
            "证据": "The glove is warm.",
            "expected_actor_ref": actor,
            "expected_product_ref": product,
        },
        "one",
        "WARM",
    )
    assert reference["facts"][0]["expected_actor_ref"] == actor
    assert reference["facts"][0]["expected_product_ref"] == product


@pytest.mark.parametrize(
    "column,value",
    [
        ("使用者", "reviewer"),
        ("使用者", "OTHER:My daughter"),
        ("使用者", "OTHER:0"),
        ("使用者", "OTHER:01"),
        ("使用者", "OTHER:-1"),
        ("使用者", "CURRENT"),
        ("商品对象", "CURRENT:medium pair"),
        ("商品对象", "OTHER"),
        ("商品对象", "CURRENT:0"),
        ("商品对象", "CURRENT:1.5"),
        ("商品对象", "OTHER:１"),
        ("使用者", 0),
        ("商品对象", False),
    ],
)
@pytest.mark.parametrize("state", ["", "EXPERIENCE"])
def test_reference_object_identifiers_reject_descriptions_before_evaluation(
    column, value, state
):
    reference = {}
    with pytest.raises(ValueError, match=f"参考答案 one 的{column}引用无效"):
        append_reference_fact(
            reference,
            {column: value, "事实状态": state, "证据": "The glove is warm."},
            "one",
            "WARM",
        )
    assert "facts" not in reference


@pytest.mark.parametrize("state", ["EXPERIENCE", "EVALUATION"])
def test_confirmed_business_evaluations_share_gate_state(state):
    item = _with_state(_item())
    item["draft"]["extracted_facts"][0]["statement_type"] = state
    assert compare_reference(item, "draft")["statement_type_errors"] == 0


def test_unmapped_context_scope_differences_do_not_block_business_gate():
    item = _with_state(_item(expected=[], actual=[]))
    item["reference"]["facts"][0]["label_codes"] = []
    item["draft"]["fact_mappings"] = []
    item["draft"]["extracted_facts"][0].update(
        statement_type="NOT_TESTED",
        subject="CUSTOMER",
        event_ref="other",
        condition="other",
    )
    counts = compare_reference(item, "draft")
    assert all(
        counts[key] == 0
        for key in (
            "statement_type_errors",
            "subject_errors",
            "event_errors",
            "condition_errors",
        )
    )
    item["draft"]["extracted_facts"][0]["product_ref"] = "OTHER:1"
    item["reference"]["facts"][0]["expected_product_ref"] = "CURRENT"
    assert compare_reference(item, "draft")["product_errors"] == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("subject", "CUSTOMER"),
        ("statement_type", "EVALUATION"),
        ("condition", "icy evening"),
    ],
)
def test_different_fact_scope_is_not_a_duplicate(field, value):
    item = _with_state(_item(actual=[_unit(), _unit("My fingers are warm.")]))
    item["draft"]["extracted_facts"].append(
        _fact("f2", evidence_spans=[{"text": "My fingers are warm."}], **{field: value})
    )
    item["draft"]["fact_mappings"].append({"fact_id": "f2", "label_codes": ["WARM"]})
    assert compare_reference(item, "draft")["duplicate_units"] == 0


@pytest.mark.parametrize(
    "metric", ["extra_labels", "missing_labels", "duplicate_units"]
)
def test_single_secondary_instance_error_warns(metric):
    item = _with_state(_item())
    evaluation = evaluate_references([item] * 20)
    evaluation["sides"]["draft"][metric] = 1
    gate = quality_gate({"reference_evaluation": evaluation}, FACT_QUALITY_POLICY)
    assert gate["passed"]
    assert any(METRIC_LABELS[metric] in warning for warning in gate["warnings"])


@pytest.mark.parametrize(
    "metric",
    [
        "model_errors",
        "evidence_errors",
        "plan_confirmation_errors",
        "product_errors",
        "direction_errors",
        "subject_errors",
        "primary_errors",
    ],
)
def test_single_high_damage_error_blocks_gate(metric):
    item = _with_state(_item())
    evaluation = evaluate_references([item] * 20)
    evaluation["sides"]["draft"][metric] = 1
    gate = quality_gate({"reference_evaluation": evaluation}, FACT_QUALITY_POLICY)
    assert not gate["passed"]
    assert FACT_QUALITY_POLICY["thresholds"][metric] == 0


def test_embedded_legacy_policy_keeps_zero_tolerance_behavior():
    legacy_policy = {
        "version": "fact-reference-v3",
        "thresholds": dict.fromkeys(ERROR_METRICS, 0),
        "min_reference_samples": 20,
        "min_reference_coverage": 100,
        "min_instance_match_rate": 100,
        "max_duplicate_rate": 0,
        "require_fact_states": True,
        "require_scope_dimensions": list(SCOPE_FIELDS),
    }
    items = [_with_state(_item()) for _ in range(20)]
    evaluation = evaluate_references(items)
    evaluation["sides"]["draft"]["missing_labels"] = 1
    gate = publication_quality_gate(
        {"taxonomy": {"recognition_profile": "fact_v2"}},
        {"quality_policy": legacy_policy},
        [],
        {"reference_evaluation": evaluation},
    )
    assert not gate["passed"]
    assert gate["warnings"] == []
