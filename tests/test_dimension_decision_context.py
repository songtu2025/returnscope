import pytest
from test_dimension_decision import (
    _classification,
    _decision,
    _fact,
    _size_taxonomy,
    _taxonomy,
)

from return_semantics.dimension_decisions import compile_dimension_decisions
from return_semantics.fact_mapping import FactDecisions
from return_semantics.schemas import FactMapping


@pytest.mark.parametrize("mode", ["valid", "recover", "reject"])
def test_compilation_keeps_inputs_unchanged_on_success_recovery_and_failure(
    mode,
) -> None:
    comment = "Typing is inaccurate because taps are missed."
    taxonomy = _taxonomy()
    classification = _classification(
        comment,
        taxonomy,
        [
            _fact("F1", "Typing is inaccurate", "NEGATIVE", is_primary_reason=True),
            _fact("F2", "taps are missed", "NEGATIVE", fact_role="EVIDENCE"),
        ],
        [
            FactMapping(fact_id="F1", label_codes=["TOUCH_NEGATIVE"]),
            FactMapping(fact_id="F2", disposition="EVIDENCE_ONLY"),
        ],
    )
    decisions = FactDecisions(
        decisions=[
            _decision(
                "TOUCHSCREEN",
                "TOUCH_NEGATIVE",
                ["F1"] if mode == "valid" else ["F2"],
                context=["F2"] if mode == "valid" else [],
            )
        ]
    )
    before = [
        item.model_dump(mode="json") for item in (classification, decisions, taxonomy)
    ]

    if mode == "reject":
        with pytest.raises(ValueError, match="支持事实必须全部候选映射到维度结论标签"):
            compile_dimension_decisions(
                classification, decisions, comment=comment, taxonomy=taxonomy
            )
    else:
        result = compile_dimension_decisions(
            classification,
            decisions,
            comment=comment,
            taxonomy=taxonomy,
            recover_invalid_decisions=mode == "recover",
        )
        assert result is not classification
        assert result.primary_label_codes == ["TOUCH_NEGATIVE"]
        assert [unit.fact_id for unit in result.semantic_units] == ["F1"]
        assert result.dimension_decisions[0].supporting_fact_ids == ["F1"]
        result.semantic_units[0].opinion = "仅修改返回结果"
        result.fact_mappings[0].label_codes.clear()

    assert [
        item.model_dump(mode="json") for item in (classification, decisions, taxonomy)
    ] == before


def test_sequential_compilations_keep_taxonomy_facts_and_comment_isolated() -> None:
    touchscreen = _taxonomy()
    size = _size_taxonomy()
    touch_comment = "Typing is inaccurate."
    size_comment = "These gloves fit."
    touch_input = _classification(
        touch_comment,
        touchscreen,
        [_fact("F1", touch_comment, "NEGATIVE")],
        [FactMapping(fact_id="F1", label_codes=["TOUCH_NEGATIVE"])],
    )
    size_input = _classification(
        size_comment,
        size,
        [
            _fact(
                "F1",
                size_comment,
                "POSITIVE",
                part="UNSPECIFIED",
                candidate_branch_codes=["SIZE"],
            )
        ],
        [FactMapping(fact_id="F1", label_codes=["FIT_ACCEPTED"])],
    )
    touch_decisions = FactDecisions(
        decisions=[_decision("TOUCHSCREEN", "TOUCH_NEGATIVE", ["F1"])]
    )
    size_decisions = FactDecisions(
        decisions=[_decision("FIT", "FIT_ACCEPTED", ["F1"], part="UNSPECIFIED")]
    )

    first = compile_dimension_decisions(
        touch_input, touch_decisions, comment=touch_comment, taxonomy=touchscreen
    )
    second = compile_dimension_decisions(
        size_input, size_decisions, comment=size_comment, taxonomy=size
    )
    repeated = compile_dimension_decisions(
        touch_input, touch_decisions, comment=touch_comment, taxonomy=touchscreen
    )

    assert first.model_dump(mode="json") == repeated.model_dump(mode="json")
    assert first.semantic_units[0].label_code == "TOUCH_NEGATIVE"
    assert first.semantic_units[0].evidence == touch_comment
    assert second.semantic_units[0].label_code == "FIT_ACCEPTED"
    assert second.semantic_units[0].evidence == size_comment
    assert first.semantic_units[0].opinion != second.semantic_units[0].opinion
