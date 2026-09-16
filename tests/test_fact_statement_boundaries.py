import pytest

from return_semantics.fact_pipeline import (
    FactMappings,
    compile_fact_classification,
    extraction_messages,
)
from return_semantics.schemas import ExtractedFact, FactMapping


def test_extraction_contract_separates_properties_events_and_negated_problems(taxonomy):
    instruction = extraction_messages("评价文本", taxonomy)[0]["content"]
    for boundary in (
        "未明确试穿或实际使用事件时用EVALUATION",
        "owned及去年等时间背景不构成使用证据",
        "明确试穿后发现偏小才是EXPERIENCE",
        "否认问题存在时为NEGATED",
        "不推导为合身等正向性能",
        "否定保暖等性能本身仍是负向EXPERIENCE/EVALUATION",
        "使用操作建议时subject为CUSTOMER",
        "否认自己作出购买推荐时也为CUSTOMER",
    ):
        assert boundary in instruction


@pytest.mark.parametrize(
    "statement,subject,text,assertion",
    [
        ("EVALUATION", "PRODUCT", "This item is too small overall.", "AFFIRMED"),
        ("EVALUATION", "PRODUCT", "The bulky item I owned last year.", "AFFIRMED"),
        ("EXPERIENCE", "PRODUCT", "It felt tight when I tried it on.", "AFFIRMED"),
        ("NEGATED", "CUSTOMER", "I have no sizing complaint.", "NEGATED"),
        ("NEGATED", "CUSTOMER", "I am not recommending a purchase.", "NEGATED"),
        ("ADVICE", "CUSTOMER", "Prewarm it indoors before wearing it.", "UNCERTAIN"),
        ("EVALUATION", "PRODUCT", "It is not warm.", "AFFIRMED"),
    ],
)
def test_statement_and_subject_projection_preserves_semantic_boundary(
    taxonomy, statement, subject, text, assertion
):
    label = taxonomy.labels[0].model_copy(update={"allowed_sentiments": ["NEGATIVE"]})
    candidate = taxonomy.model_copy(update={"labels": [label]})
    fact = ExtractedFact(
        fact_id="f1",
        actor_ref="REVIEWER",
        product_ref="CURRENT",
        event_ref="event",
        subject=subject,
        statement_type=statement,
        opinion=text,
        sentiment="NEGATIVE",
        part="UNSPECIFIED",
        evidence_spans=[{"text": text}],
    )
    result = compile_fact_classification(
        [fact],
        FactMappings(mappings=[FactMapping(fact_id="f1", label_codes=[label.code])]),
        comment=text,
        taxonomy=candidate,
        allowed={"f1": [label.code]},
    )
    assert result.extracted_facts[0].statement_type == statement
    if statement in {"NEGATED", "ADVICE"}:
        assert result.semantic_units == []
        assert result.unknown_semantics[0].disposition == "EXPECTED_ABSTENTION"
    else:
        assert result.semantic_units[0].subject == subject
        assert result.semantic_units[0].assertion == assertion
