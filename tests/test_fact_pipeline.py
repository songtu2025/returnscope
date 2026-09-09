import json
from types import SimpleNamespace

import pytest

from return_semantics import prompt
from return_semantics.fact_pipeline import (
    FactMappings,
    classify_facts,
    compile_fact_classification,
)
from return_semantics.model_client import JsonlCache, JsonModelCallResult
from return_semantics.pipeline import _call_with_cache
from return_semantics.schemas import (
    ExtractedFact,
    FactMapping,
    ListingClaimsConfig,
    ModelClassification,
    TaxonomyConfig,
)


@pytest.fixture
def fact_taxonomy():
    return TaxonomyConfig.model_validate(
        {
            "version": "test",
            "recognition_profile": "fact_v2",
            "agent_family": "测试",
            "product_context": "测试商品",
            "labels": [
                {
                    "code": "WARM",
                    "name": "保暖",
                    "group": "功能",
                    "allowed_sentiments": ["POSITIVE"],
                },
                {
                    "code": "COLD",
                    "name": "不保暖",
                    "group": "功能",
                    "allowed_sentiments": ["NEGATIVE"],
                },
                {
                    "code": "FIT",
                    "name": "合身",
                    "group": "尺码",
                    "allowed_sentiments": ["POSITIVE"],
                },
            ],
        }
    )


def make_fact(identifier="a", **updates):
    return ExtractedFact.model_validate(
        {
            "fact_id": identifier,
            "actor_ref": "REVIEWER",
            "product_ref": "CURRENT",
            "event_ref": "首次使用",
            "statement_type": "EXPERIENCE",
            "opinion": "手套暖和",
            "sentiment": "POSITIVE",
            "part": "UNSPECIFIED",
            "condition": "",
            "evidence_spans": [{"text": "warm"}],
            "candidate_branch_codes": ["功能"],
            **updates,
        }
    )


class FakeJsonClient:
    def __init__(self, payloads):
        self.payloads = iter(payloads)
        self.messages = []
        self.settings = SimpleNamespace(cache_namespace="test", reasoning_effort="low")

    def generate_json(self, messages, **kwargs):
        self.messages.append(messages)
        return JsonModelCallResult(next(self.payloads), "test", {"total_tokens": 5})


def test_two_calls_map_only_selected_branch_and_cache(fact_taxonomy, tmp_path):
    fact = make_fact()
    client = FakeJsonClient(
        [
            {"facts": [fact.model_dump(mode="json")]},
            {"mappings": [{"fact_id": "a", "label_codes": ["WARM"]}]},
        ]
    )
    kwargs = dict(
        comment="warm",
        model_name="test",
        thinking=False,
        messages=[],
        taxonomy=fact_taxonomy,
        claims=ListingClaimsConfig(version="none", claims=[]),
        client=client,
        cache=JsonlCache(tmp_path / "cache.jsonl"),
        force=False,
        classification_scope="test",
        model_policy_version="test",
    )
    result, cached = _call_with_cache(**kwargs)
    again, cached_again = _call_with_cache(**kwargs)

    assert not cached and cached_again
    assert result == again
    assert len(client.messages) == 2
    first = json.loads(client.messages[0][1]["content"])
    second = json.loads(client.messages[1][1]["content"])
    assert "labels" not in first
    assert {label["code"] for label in second["labels"]} == {"WARM", "COLD"}
    assert result.usage == {"total_tokens": 10}
    assert result.metrics["fact_model_calls"] == 2
    assert result.classification.extracted_facts == [fact]


def test_different_objects_and_conditions_survive(fact_taxonomy):
    facts = [
        make_fact(product_ref="CURRENT:1"),
        make_fact(
            "b",
            product_ref="CURRENT:2",
            condition="湿冷时",
            opinion="湿冷时另一副手套冷",
            sentiment="NEGATIVE",
            evidence_spans=[{"text": "cold"}],
        ),
    ]
    result = compile_fact_classification(
        facts,
        FactMappings(
            mappings=[
                FactMapping(fact_id="a", label_codes=["WARM"]),
                FactMapping(fact_id="b", label_codes=["COLD"]),
            ]
        ),
        comment="warm then second pair cold",
        taxonomy=fact_taxonomy,
        allowed={"a": ["WARM"], "b": ["COLD"]},
    )
    assert len(result.semantic_units) == 2
    assert result.semantic_units[1].opinion == "湿冷时另一副手套冷"
    assert result.extracted_facts[1].product_ref == "CURRENT:2"


@pytest.mark.parametrize(
    "statement", ["PREDICTION", "HYPOTHESIS", "INTENT", "NOT_TESTED", "ADVICE"]
)
def test_future_positive_is_not_confirmed(statement, fact_taxonomy):
    result = compile_fact_classification(
        [make_fact(statement_type=statement)],
        FactMappings(mappings=[FactMapping(fact_id="a", label_codes=["WARM"])]),
        comment="warm",
        taxonomy=fact_taxonomy,
        allowed={"a": ["WARM"]},
    )
    assert result.semantic_units[0].assertion == "UNCERTAIN"
    assert result.needs_review


@pytest.mark.parametrize("mappings", [[], [FactMapping(fact_id="other")]])
def test_missing_or_foreign_fact_mapping_rejected(mappings, fact_taxonomy):
    with pytest.raises(ValueError, match="每个事实"):
        compile_fact_classification(
            [make_fact()],
            FactMappings(mappings=mappings),
            comment="warm",
            taxonomy=fact_taxonomy,
            allowed={"a": ["WARM"]},
        )


def test_unknown_preserves_fact_and_contiguous_evidence(fact_taxonomy):
    fact = make_fact(evidence_spans=[{"text": "warm"}, {"text": "today"}])
    result = compile_fact_classification(
        [fact],
        FactMappings(mappings=[FactMapping(fact_id="a", reason="没有对应标签")]),
        comment="warm and dry today",
        taxonomy=fact_taxonomy,
        allowed={"a": []},
    )
    assert result.unknown_semantics[0].evidence == "warm and dry today"
    assert result.extracted_facts == [fact]
    assert result.needs_review


def test_fabricated_evidence_is_rejected_before_mapping(fact_taxonomy):
    client = FakeJsonClient([{"facts": [make_fact().model_dump(mode="json")]}] * 2)
    with pytest.raises(ValueError, match="证据不在"):
        classify_facts(
            comment="unrelated",
            taxonomy=fact_taxonomy,
            client=client,
            model_name="test",
            reasoning_effort="low",
        )
    assert len(client.messages) == 2


def test_branch_escape_is_rejected(fact_taxonomy):
    with pytest.raises(ValueError, match="分支外"):
        compile_fact_classification(
            [make_fact()],
            FactMappings(mappings=[FactMapping(fact_id="a", label_codes=["FIT"])]),
            comment="warm",
            taxonomy=fact_taxonomy,
            allowed={"a": ["WARM"]},
        )


def test_old_output_without_fact_trace_remains_valid():
    assert ModelClassification.model_validate({}).extracted_facts == []


@pytest.mark.parametrize(
    "statement, assertion", [("EXPERIENCE", "AFFIRMED"), ("NEGATED", "NEGATED")]
)
def test_negative_performance_is_not_negation_of_an_event(
    fact_taxonomy, statement, assertion
):
    fact = make_fact(
        statement_type=statement,
        sentiment="NEGATIVE",
        opinion="手套不暖",
        evidence_spans=[{"text": "not warm"}],
    )
    result = compile_fact_classification(
        [fact],
        FactMappings(mappings=[FactMapping(fact_id="a", label_codes=["COLD"])]),
        comment="not warm",
        taxonomy=fact_taxonomy,
        allowed={"a": ["COLD"]},
    )
    assert result.semantic_units[0].assertion == assertion
    assert result.needs_review == (statement == "NEGATED")


def test_reported_actual_experience_is_retained(fact_taxonomy):
    result = compile_fact_classification(
        [make_fact(statement_type="REPORTED", actor_ref="OTHER:1")],
        FactMappings(mappings=[FactMapping(fact_id="a", label_codes=["WARM"])]),
        comment="my child says warm",
        taxonomy=fact_taxonomy,
        allowed={"a": ["WARM"]},
    )
    assert result.semantic_units[0].assertion == "AFFIRMED"
    assert result.extracted_facts[0].actor_ref == "OTHER:1"
    assert result.needs_review


def test_one_atomic_fact_cannot_map_multiple_labels():
    with pytest.raises(ValueError):
        FactMapping(fact_id="a", label_codes=["WARM", "FIT"])


@pytest.mark.parametrize("different_event", [False, True])
def test_event_identity_deduplicates_only_same_event(fact_taxonomy, different_event):
    facts = [
        make_fact(),
        make_fact("b", event_ref="第二次使用" if different_event else "首次使用"),
    ]
    result = compile_fact_classification(
        facts,
        FactMappings(
            mappings=[
                FactMapping(fact_id=f.fact_id, label_codes=["WARM"]) for f in facts
            ]
        ),
        comment="warm",
        taxonomy=fact_taxonomy,
        allowed={f.fact_id: ["WARM"] for f in facts},
    )
    assert len(result.semantic_units) == (2 if different_event else 1)
    assert len(result.extracted_facts) == 2


def test_mapping_retries_only_failed_stage(fact_taxonomy):
    client = FakeJsonClient(
        [
            {"facts": [make_fact().model_dump(mode="json")]},
            {"mappings": [{"fact_id": "a", "label_codes": ["FIT"]}]},
            {"mappings": [{"fact_id": "a", "label_codes": ["WARM"]}]},
        ]
    )
    result = classify_facts(
        comment="warm",
        taxonomy=fact_taxonomy,
        client=client,
        model_name="test",
        reasoning_effort="low",
    )
    assert len(client.messages) == 3
    assert result.metrics["fact_model_calls"] == 3
    assert result.usage["total_tokens"] == 15
    assert "上次输出未通过校验" in client.messages[2][-1]["content"]


def test_invalid_part_retries_extraction_before_mapping(fact_taxonomy):
    client = FakeJsonClient(
        [
            {"facts": [make_fact(part="INVALID").model_dump(mode="json")]},
            {"facts": [make_fact().model_dump(mode="json")]},
            {"mappings": [{"fact_id": "a", "label_codes": ["WARM"]}]},
        ]
    )
    result = classify_facts(
        comment="warm",
        taxonomy=fact_taxonomy,
        client=client,
        model_name="test",
        reasoning_effort="low",
    )
    assert result.metrics["fact_model_calls"] == 3
    assert "事实部位不适用" in client.messages[1][-1]["content"]
    assert result.classification.semantic_units[0].part == "UNSPECIFIED"


@pytest.mark.parametrize(
    "updates",
    [
        {"actor_ref": "买家"},
        {"actor_ref": "CURRENT"},
        {"actor_ref": "OTHER:"},
        {"actor_ref": "OTHER:my child"},
        {"product_ref": "本品"},
        {"product_ref": "OTHER:missing product"},
        {"product_ref": "CURRENT: "},
        {"actor_ref": "OTHER:0"},
        {"actor_ref": "OTHER:01"},
        {"actor_ref": "OTHER:-1"},
        {"actor_ref": "OTHER:1.5"},
        {"product_ref": "OTHER:１"},
        {"product_ref": "CURRENT:0"},
        {"product_ref": "CURRENT:01"},
    ],
)
def test_invalid_reference_repairs_only_extraction(fact_taxonomy, updates):
    client = FakeJsonClient(
        [
            {"facts": [make_fact(**updates).model_dump(mode="json")]},
            {"facts": [make_fact().model_dump(mode="json")]},
            {"mappings": [{"fact_id": "a", "label_codes": ["WARM"]}]},
        ]
    )
    result = classify_facts(
        comment="warm",
        taxonomy=fact_taxonomy,
        client=client,
        model_name="test",
        reasoning_effort="low",
    )
    assert result.metrics["fact_model_calls"] == 3
    assert "事实对象引用不符合协议" in client.messages[1][-1]["content"]
    assert result.classification.extracted_facts[0].actor_ref == "REVIEWER"
    assert result.classification.extracted_facts[0].product_ref == "CURRENT"


def test_other_product_numeric_reference_retains_evidence(fact_taxonomy):
    fact = make_fact(
        product_ref="OTHER:1", evidence_spans=[{"text": "old gloves were warm"}]
    )
    result = compile_fact_classification(
        [fact],
        FactMappings(mappings=[FactMapping(fact_id="a", reason="其他商品对照")]),
        comment="old gloves were warm",
        taxonomy=fact_taxonomy,
        allowed={"a": ["WARM"]},
    )
    assert result.extracted_facts[0].product_ref == "OTHER:1"
    assert result.extracted_facts[0].evidence_spans[0].text == "old gloves were warm"
    assert result.semantic_units == []
    assert result.unknown_semantics == []


def test_current_single_and_numbered_references_cannot_mix(fact_taxonomy):
    facts = [make_fact(), make_fact("b", product_ref="CURRENT:1")]
    with pytest.raises(ValueError, match="不能与多件商品"):
        compile_fact_classification(
            facts,
            FactMappings(mappings=[FactMapping(fact_id=f.fact_id) for f in facts]),
            comment="warm",
            taxonomy=fact_taxonomy,
            allowed={f.fact_id: [] for f in facts},
        )


def test_service_responsibility_does_not_change_reviewer_reference(fact_taxonomy):
    fact = make_fact(subject="SERVICE", actor_ref="REVIEWER")
    client = FakeJsonClient(
        [
            {"facts": [fact.model_dump(mode="json")]},
            {
                "mappings": [
                    {"fact_id": "a", "label_codes": [], "reason": "无对应服务标签"}
                ]
            },
        ]
    )
    result = classify_facts(
        comment="warm",
        taxonomy=fact_taxonomy,
        client=client,
        model_name="test",
        reasoning_effort="low",
    )
    extracted = result.classification.extracted_facts[0]
    assert extracted.subject == "SERVICE"
    assert extracted.actor_ref == "REVIEWER"
    system = client.messages[0][0]["content"]
    assert "首次出现顺序编号" in system
    assert "actor与product编号互相独立" in system
    assert "评论者本人经历客服响应时actor_ref仍为REVIEWER" in system


def test_other_product_mapping_is_repaired_without_reextracting(fact_taxonomy):
    fact = make_fact(product_ref="OTHER:1")
    client = FakeJsonClient(
        [
            {"facts": [fact.model_dump(mode="json")]},
            {"mappings": [{"fact_id": "a", "label_codes": ["WARM"]}]},
            {"mappings": [{"fact_id": "a", "label_codes": [], "reason": "对照商品"}]},
        ]
    )
    result = classify_facts(
        comment="previous pair was warm",
        taxonomy=fact_taxonomy,
        client=client,
        model_name="test",
        reasoning_effort="low",
    )
    assert result.metrics["fact_model_calls"] == 3
    assert result.classification.semantic_units == []
    assert result.classification.extracted_facts == [fact]
    mapping_input = json.loads(client.messages[1][1]["content"])
    assert mapping_input["allowed_labels_by_fact"]["a"] == []


def test_routing_exposes_topics_hidden_by_generic_branch_names(fact_taxonomy):
    fact_taxonomy.labels[0].group = "综合"
    client = FakeJsonClient(
        [
            {
                "facts": [
                    make_fact(candidate_branch_codes=["综合"]).model_dump(mode="json")
                ]
            },
            {"mappings": [{"fact_id": "a", "label_codes": ["WARM"]}]},
        ]
    )
    classify_facts(
        comment="warm",
        taxonomy=fact_taxonomy,
        client=client,
        model_name="test",
        reasoning_effort="low",
    )
    extraction_input = json.loads(client.messages[0][1]["content"])
    branch = extraction_input["candidate_branches"]["综合"]
    assert branch == {"name": "综合", "topics": ["保暖"]}
    assert "WARM" not in json.dumps(extraction_input["candidate_branches"])


def test_prediction_cannot_hide_later_confirmed_fact(fact_taxonomy):
    facts = [make_fact(statement_type="PREDICTION"), make_fact("b")]
    result = compile_fact_classification(
        facts,
        FactMappings(
            mappings=[
                FactMapping(fact_id=f.fact_id, label_codes=["WARM"]) for f in facts
            ]
        ),
        comment="warm",
        taxonomy=fact_taxonomy,
        allowed={f.fact_id: ["WARM"] for f in facts},
    )
    assert [unit.assertion for unit in result.semantic_units] == [
        "UNCERTAIN",
        "AFFIRMED",
    ]


def test_claims_require_explicit_safe_review(fact_taxonomy):
    claims = ListingClaimsConfig.model_validate(
        {
            "version": "test",
            "claims": [
                {
                    "claim_id": "c",
                    "text": "保暖",
                    "source": "测试",
                    "allowed_label_codes": ["WARM"],
                }
            ],
        }
    )
    client = FakeJsonClient(
        [
            {"facts": [make_fact().model_dump(mode="json")]},
            {"mappings": [{"fact_id": "a", "label_codes": ["WARM"]}]},
        ]
    )
    result = classify_facts(
        comment="warm",
        taxonomy=fact_taxonomy,
        client=client,
        model_name="test",
        reasoning_effort="low",
        claims=claims,
    )
    assert result.classification.needs_review
    assert any("Listing" in reason for reason in result.classification.review_reasons)


def test_boundary_required_labels_are_optional_and_checked(fact_taxonomy):
    assert fact_taxonomy.validation_rules.boundary_required_labels == []
    data = fact_taxonomy.model_dump(mode="json")
    data["validation_rules"]["boundary_required_labels"] = ["MISSING"]
    with pytest.raises(ValueError, match="未知标签"):
        TaxonomyConfig.model_validate(data)


@pytest.mark.parametrize(
    "comment,sentiment,statement,label_name",
    [
        ("我习惯选择宽一点的规格。", "NEUTRAL", "EVALUATION", "尺码需求"),
        ("收到的尺寸太小，挤得不舒服。", "NEGATIVE", "EXPERIENCE", "偏小"),
        ("戴上后大小刚好。", "POSITIVE", "EVALUATION", "合身"),
    ],
)
def test_sizing_directions_survive_two_stage_mapping(
    fact_taxonomy, comment, sentiment, statement, label_name
):
    data = fact_taxonomy.model_dump(mode="json")
    data["labels"] = [
        {
            "code": "SIZE",
            "name": label_name,
            "group": "尺码",
            "allowed_sentiments": [sentiment],
        }
    ]
    taxonomy = TaxonomyConfig.model_validate(data)
    fact = make_fact(
        opinion=comment,
        sentiment=sentiment,
        statement_type=statement,
        evidence_spans=[{"text": comment}],
        candidate_branch_codes=["尺码"],
    )
    client = FakeJsonClient(
        [
            {"facts": [fact.model_dump(mode="json")]},
            {"mappings": [{"fact_id": "a", "label_codes": ["SIZE"]}]},
        ]
    )
    result = classify_facts(
        comment=comment,
        taxonomy=taxonomy,
        client=client,
        model_name="test",
        reasoning_effort="low",
    )
    unit = result.classification.semantic_units[0]
    assert unit.sentiment == sentiment
    assert unit.assertion == "AFFIRMED"
    assert result.classification.unknown_semantics == []
    instruction = client.messages[0][0]["content"]
    assert "个人选码偏好或本人尺码需求，其sentiment为NEUTRAL" in instruction
    assert "尺码问题仍为NEGATIVE" in instruction
    assert "当前商品合身仍为POSITIVE" in instruction


@pytest.mark.parametrize(
    "previous_version",
    ["category-fact-v2-v2", "category-fact-v2-v3", "category-fact-v2-v4"],
)
def test_fact_prompt_update_invalidates_previous_fact_cache(
    fact_taxonomy, monkeypatch, previous_version
):
    with monkeypatch.context() as context:
        context.setattr(prompt, "prompt_version", lambda _: previous_version)
        old_fingerprint = prompt.recognition_fingerprint(fact_taxonomy)
    assert prompt.prompt_version(fact_taxonomy) == "category-fact-v2-v10"
    assert old_fingerprint != prompt.recognition_fingerprint(fact_taxonomy)


@pytest.mark.parametrize(
    "comment,statement,label_name",
    [
        ("The fabric felt coarse last spring.", "EVALUATION", "粗糙"),
        ("The seam tore during yesterday's walk.", "EXPERIENCE", "开线"),
    ],
)
def test_past_attribute_and_event_keep_distinct_fact_states(
    fact_taxonomy, comment, statement, label_name
):
    data = fact_taxonomy.model_dump(mode="json")
    data["labels"] = [
        {
            "code": "DETAIL",
            "name": label_name,
            "group": "质量",
            "allowed_sentiments": ["NEGATIVE"],
        }
    ]
    taxonomy = TaxonomyConfig.model_validate(data)
    fact = make_fact(
        opinion=comment,
        sentiment="NEGATIVE",
        statement_type=statement,
        evidence_spans=[{"text": comment}],
        candidate_branch_codes=["质量"],
    )
    client = FakeJsonClient(
        [
            {"facts": [fact.model_dump(mode="json")]},
            {"mappings": [{"fact_id": "a", "label_codes": ["DETAIL"]}]},
        ]
    )
    result = classify_facts(
        comment=comment,
        taxonomy=taxonomy,
        client=client,
        model_name="test",
        reasoning_effort="low",
    )
    assert result.classification.extracted_facts[0].statement_type == statement
    assert result.classification.semantic_units[0].assertion == "AFFIRMED"
    instruction = client.messages[0][0]["content"]
    assert "主观判断，不受现在或过去时限制" in instruction
    assert "不足以把属性评价变成体验事件" in instruction


@pytest.mark.parametrize("different_condition", [False, True])
def test_same_identity_merges_details_but_preserves_conditions(
    fact_taxonomy, different_condition
):
    facts = [
        make_fact(opinion="initial warmth"),
        make_fact(
            "b",
            opinion="later warmth",
            condition="later" if different_condition else "",
            evidence_spans=[{"text": "still warm"}],
        ),
    ]
    result = compile_fact_classification(
        facts,
        FactMappings(
            mappings=[
                FactMapping(fact_id=f.fact_id, label_codes=["WARM"]) for f in facts
            ]
        ),
        comment="warm, and still warm",
        taxonomy=fact_taxonomy,
        allowed={f.fact_id: ["WARM"] for f in facts},
    )
    assert len(result.semantic_units) == (2 if different_condition else 1)
    if not different_condition:
        assert result.semantic_units[0].evidence == "warm, and still warm"
        assert "initial warmth" in result.semantic_units[0].opinion
        assert "later warmth" in result.semantic_units[0].opinion


@pytest.mark.parametrize("profile,expected", [("fact_v2", 2), ("semantic_v1", 1)])
def test_final_validator_preserves_fact_identity_only_for_fact_v2(
    fact_taxonomy, profile, expected
):
    from return_semantics.validator import validate_classification

    facts = [
        make_fact(product_ref="CURRENT:1"),
        make_fact("b", product_ref="CURRENT:2"),
    ]
    compiled = compile_fact_classification(
        facts,
        FactMappings(
            mappings=[
                FactMapping(fact_id=f.fact_id, label_codes=["WARM"]) for f in facts
            ]
        ),
        comment="warm",
        taxonomy=fact_taxonomy,
        allowed={f.fact_id: ["WARM"] for f in facts},
    )
    result = validate_classification(
        "test",
        "warm",
        "",
        compiled,
        fact_taxonomy.model_copy(update={"recognition_profile": profile}),
        ListingClaimsConfig(version="none", claims=[]),
        "test",
        "test",
        "review",
    )
    assert len(result.semantic_units) == expected


@pytest.mark.parametrize(
    "statement,primary",
    [("EXPERIENCE", True), ("EXPERIENCE", False), ("PREDICTION", True)],
)
def test_primary_requires_explicit_and_confirmed_fact(
    fact_taxonomy, statement, primary
):
    fact = make_fact(statement_type=statement, is_primary_reason=primary)
    result = compile_fact_classification(
        [fact],
        FactMappings(mappings=[FactMapping(fact_id="a", label_codes=["WARM"])]),
        comment="warm",
        taxonomy=fact_taxonomy,
        allowed={"a": ["WARM"]},
    )
    assert result.primary_label_codes == (
        ["WARM"] if primary and statement == "EXPERIENCE" else []
    )
    assert make_fact().is_primary_reason is False


@pytest.mark.parametrize(
    "name,affirmed", [("愿意回购", True), ("值得购买", True), ("保暖", False)]
)
def test_intent_fallback_is_only_for_mapped_purchase_attitude(
    fact_taxonomy, name, affirmed
):
    label = fact_taxonomy.labels[0].model_copy(update={"name": name})
    taxonomy = fact_taxonomy.model_copy(update={"labels": [label]})
    result = compile_fact_classification(
        [make_fact(statement_type="INTENT")],
        FactMappings(mappings=[FactMapping(fact_id="a", label_codes=["WARM"])]),
        comment="warm",
        taxonomy=taxonomy,
        allowed={"a": ["WARM"]},
    )
    assert result.semantic_units[0].assertion == (
        "AFFIRMED" if affirmed else "UNCERTAIN"
    )


def test_negative_repurchase_attitude_survives_final_validation(fact_taxonomy):
    from return_semantics.validator import validate_classification

    label = fact_taxonomy.labels[1].model_copy(update={"name": "不值得购买/拒绝回购"})
    taxonomy = fact_taxonomy.model_copy(update={"labels": [label]})
    fact = make_fact(
        statement_type="INTENT",
        sentiment="NEGATIVE",
        opinion="明确拒绝回购",
        evidence_spans=[{"text": "I would not buy again."}],
    )
    compiled = compile_fact_classification(
        [fact],
        FactMappings(mappings=[FactMapping(fact_id="a", label_codes=["COLD"])]),
        comment="I would not buy again.",
        taxonomy=taxonomy,
        allowed={"a": ["COLD"]},
    )
    result = validate_classification(
        "test",
        "I would not buy again.",
        "",
        compiled,
        taxonomy,
        ListingClaimsConfig(version="none", claims=[]),
        "test",
        "test",
        "review",
    )
    assert len(result.semantic_units) == 1
    assert result.semantic_units[0].sentiment == "NEGATIVE"


def test_fact_extraction_requests_explicit_primary_and_no_anatomical_inference(
    fact_taxonomy,
):
    from return_semantics.fact_pipeline import extraction_messages

    instruction = extraction_messages("ordinary review", fact_taxonomy)[0]["content"]
    for boundary in (
        "is_primary_reason默认false",
        "整体尺码陈述",
        "hand、grip、touchscreen",
        "雪天、雨天",
        "当前态度",
    ):
        assert boundary in instruction


@pytest.mark.parametrize(
    "product,sentiment,expected",
    [
        ("CURRENT", "POSITIVE", ["WARM", "COLD", "OTHER_POS"]),
        ("CURRENT", "NEGATIVE", ["WARM", "COLD", "OTHER_NEG"]),
        ("OTHER:1", "POSITIVE", []),
    ],
)
def test_current_product_receives_direction_compatible_fallback(
    fact_taxonomy, product, sentiment, expected
):
    from return_semantics.fact_pipeline import _mapping_payload

    positive = fact_taxonomy.labels[0].model_copy(
        update={"code": "OTHER_POS", "name": "其他", "group": "兜底"}
    )
    negative = fact_taxonomy.labels[1].model_copy(
        update={"code": "OTHER_NEG", "name": "其他", "group": "兜底"}
    )
    taxonomy = fact_taxonomy.model_copy(
        update={"labels": [*fact_taxonomy.labels, positive, negative]}
    )
    payload = _mapping_payload(
        [make_fact(product_ref=product, sentiment=sentiment)], taxonomy
    )
    assert payload["allowed_labels_by_fact"]["a"] == expected
    assert {label["code"] for label in payload["labels"]} == set(expected)


def test_unrouted_current_fact_can_reach_existing_other_label(fact_taxonomy):
    from return_semantics.fact_pipeline import _mapping_payload

    fallback = fact_taxonomy.labels[0].model_copy(
        update={"code": "OTHER", "name": "其他", "group": "兜底"}
    )
    taxonomy = fact_taxonomy.model_copy(
        update={"labels": [*fact_taxonomy.labels, fallback]}
    )
    payload = _mapping_payload([make_fact(candidate_branch_codes=[])], taxonomy)
    assert payload["allowed_labels_by_fact"]["a"] == ["OTHER"]


@pytest.mark.parametrize(
    "profile,explicit,expected",
    [
        ("fact_v2", False, []),
        ("fact_v2", True, ["COLD"]),
        ("semantic_v1", False, ["COLD"]),
    ],
)
def test_primary_projection_requires_explicit_fact_only_in_fact_v2(
    fact_taxonomy, profile, explicit, expected
):
    from return_semantics.validator import validate_classification

    fact = make_fact(sentiment="NEGATIVE", is_primary_reason=explicit)
    taxonomy = fact_taxonomy.model_copy(update={"recognition_profile": profile})
    compiled = compile_fact_classification(
        [fact],
        FactMappings(mappings=[FactMapping(fact_id="a", label_codes=["COLD"])]),
        comment="warm",
        taxonomy=taxonomy,
        allowed={"a": ["COLD"]},
    )
    result = validate_classification(
        "test",
        "warm",
        "",
        compiled,
        taxonomy,
        ListingClaimsConfig(version="none", claims=[]),
        "test",
        "test",
        "review",
    )
    assert result.primary_label_codes == expected
    if profile == "fact_v2" and not explicit:
        compiled.primary_label_codes = ["COLD"]
        result = validate_classification(
            "test",
            "warm",
            "",
            compiled,
            taxonomy,
            ListingClaimsConfig(version="none", claims=[]),
            "test",
            "test",
            "review",
        )
        assert result.primary_label_codes == []


@pytest.mark.parametrize(
    "subject,text",
    [
        ("CUSTOMER", "I mistakenly thought the button meant heating."),
        ("ORDER", "Only one glove arrived instead of two."),
        ("DELIVERY", "The courier delivered to the wrong address."),
        ("SERVICE", "Support declined my request."),
        ("PRODUCT", "The glove did not keep me warm."),
    ],
)
def test_responsibility_subject_survives_fact_compilation(fact_taxonomy, subject, text):
    fact = make_fact(
        subject=subject,
        sentiment="NEGATIVE",
        opinion=text,
        evidence_spans=[{"text": text}],
    )
    result = compile_fact_classification(
        [fact],
        FactMappings(mappings=[FactMapping(fact_id="a", label_codes=["COLD"])]),
        comment=text,
        taxonomy=fact_taxonomy,
        allowed={"a": ["COLD"]},
    )
    assert result.extracted_facts[0].subject == subject
    assert result.semantic_units[0].subject == subject
    assert result.extracted_facts[0].actor_ref == "REVIEWER"


def test_subject_instruction_distinguishes_order_delivery_and_misunderstanding(
    fact_taxonomy,
):
    from return_semantics.fact_pipeline import extraction_messages

    instruction = extraction_messages("review", fact_taxonomy)[0]["content"]
    for rule in (
        "误认自身购买对象、功能属于CUSTOMER",
        "少收到一只）属于ORDER",
        "送错地址属于DELIVERY",
        "客服处理属于SERVICE",
        "使用表现属于PRODUCT",
        "仅描述不加热不等于买家误认",
    ):
        assert rule in instruction
