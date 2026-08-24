from return_semantics.taxonomy import validate_taxonomy_claims


def test_taxonomy_and_claims_are_consistent(taxonomy, claims) -> None:
    validate_taxonomy_claims(taxonomy, claims)

    assert len(taxonomy.labels) == 44
    assert len(claims.claims) == 13

    labels = {label.code: label for label in taxonomy.labels}
    assert all(label.keywords for label in taxonomy.labels)
    assert "size chart" in labels["SIZE_GUIDANCE_CONFUSING"].keywords
    assert labels["OTHER_USE_SCENARIO"].name == "适用或不适用场景"
    assert "部位字段使用 UNSPECIFIED" in labels["EXPERIENCE_THIN"].description
