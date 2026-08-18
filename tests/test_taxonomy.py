from return_semantics.taxonomy import validate_taxonomy_claims


def test_taxonomy_and_claims_are_consistent(taxonomy, claims) -> None:
    validate_taxonomy_claims(taxonomy, claims)

    assert len(taxonomy.labels) == 44
    assert len(claims.claims) == 13
