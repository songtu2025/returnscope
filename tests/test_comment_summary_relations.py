from return_semantics.comment_summary import compile_comment_semantics
from return_semantics.schemas import SemanticUnit, TaxonomyConfig


def _taxonomy() -> TaxonomyConfig:
    return TaxonomyConfig.model_validate(
        {
            "version": "relation-scope-test",
            "structure_version": 2,
            "recognition_profile": "fact_v2",
            "agent_family": "测试",
            "product_context": "测试商品",
            "categories": [
                {"code": "EXPERIENCE", "name": "体验"},
                {
                    "code": "COMFORT",
                    "name": "舒适",
                    "parent_code": "EXPERIENCE",
                },
                {
                    "code": "FLEXIBILITY",
                    "name": "灵活",
                    "parent_code": "EXPERIENCE",
                },
            ],
            "validation_rules": {
                "dimension_contracts": [
                    {
                        "parent_code": "COMFORT",
                        "verdict_label_codes": ["COMFORT_POS", "COMFORT_NEG"],
                        "scope_fields": ["product_ref", "variant_ref"],
                    }
                ]
            },
            "labels": [
                {
                    "code": "COMFORT_POS",
                    "name": "舒适",
                    "parent_code": "COMFORT",
                    "allowed_sentiments": ["POSITIVE"],
                },
                {
                    "code": "COMFORT_NEG",
                    "name": "不舒适",
                    "parent_code": "COMFORT",
                    "allowed_sentiments": ["NEGATIVE"],
                },
                {
                    "code": "FLEXIBILITY_NEG",
                    "name": "不灵活",
                    "parent_code": "FLEXIBILITY",
                    "allowed_sentiments": ["NEGATIVE"],
                },
            ],
        }
    )


def _unit(code: str, sentiment: str, **updates: str) -> SemanticUnit:
    return SemanticUnit.model_validate(
        {
            "subject": "PRODUCT",
            "label_code": code,
            "opinion": code,
            "sentiment": sentiment,
            "assertion": "AFFIRMED",
            "part": "UNSPECIFIED",
            "evidence": code,
            "implicit": False,
            "fact_id": code,
            "statement_type": "EXPERIENCE",
            "event_ref": "E1",
            **updates,
        }
    )


def test_different_business_dimensions_do_not_form_scope_relation() -> None:
    taxonomy = _taxonomy()
    units = [
        _unit("COMFORT_POS", "POSITIVE", product_ref="CURRENT:1"),
        _unit(
            "FLEXIBILITY_NEG",
            "NEGATIVE",
            product_ref="CURRENT:2",
            experiencer_ref="OTHER:1",
        ),
    ]

    relations, _ = compile_comment_semantics(
        units,
        taxonomy,
        {label.code: label for label in taxonomy.labels},
    )

    assert relations == []


def test_unspecified_variant_cannot_establish_multi_product_relation() -> None:
    taxonomy = _taxonomy()
    units = [
        _unit("COMFORT_POS", "POSITIVE", variant_ref="UNSPECIFIED"),
        _unit("COMFORT_NEG", "NEGATIVE", variant_ref="M"),
    ]

    relations, _ = compile_comment_semantics(
        units,
        taxonomy,
        {label.code: label for label in taxonomy.labels},
    )

    assert relations == []


def test_distinct_explicit_variants_establish_multi_product_relation() -> None:
    taxonomy = _taxonomy()
    units = [
        _unit("COMFORT_POS", "POSITIVE", variant_ref="M"),
        _unit("COMFORT_NEG", "NEGATIVE", variant_ref="L"),
    ]

    relations, _ = compile_comment_semantics(
        units,
        taxonomy,
        {label.code: label for label in taxonomy.labels},
    )

    assert [relation.relation_type for relation in relations] == ["MULTI_PRODUCT"]


def test_distinct_products_establish_multi_product_relation() -> None:
    taxonomy = _taxonomy()
    units = [
        _unit("COMFORT_POS", "POSITIVE", product_ref="CURRENT:1"),
        _unit("COMFORT_NEG", "NEGATIVE", product_ref="CURRENT:2"),
    ]

    relations, _ = compile_comment_semantics(
        units,
        taxonomy,
        {label.code: label for label in taxonomy.labels},
    )

    assert [relation.relation_type for relation in relations] == ["MULTI_PRODUCT"]
