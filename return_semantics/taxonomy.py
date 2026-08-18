from __future__ import annotations

import json
from pathlib import Path

from return_semantics.schemas import ListingClaimsConfig, TaxonomyConfig


def load_taxonomy(path: Path) -> TaxonomyConfig:
    data = json.loads(path.read_text(encoding="utf-8"))
    taxonomy = TaxonomyConfig.model_validate(data)
    codes = [label.code for label in taxonomy.labels]
    if len(codes) != len(set(codes)):
        raise ValueError("分类体系中存在重复标签编码")
    return taxonomy


def load_listing_claims(path: Path) -> ListingClaimsConfig:
    data = json.loads(path.read_text(encoding="utf-8"))
    claims = ListingClaimsConfig.model_validate(data)
    claim_ids = [claim.claim_id for claim in claims.claims]
    if len(claim_ids) != len(set(claim_ids)):
        raise ValueError("Listing 承诺中存在重复编号")
    return claims


def validate_taxonomy_claims(
    taxonomy: TaxonomyConfig,
    claims: ListingClaimsConfig,
) -> None:
    label_codes = {label.code for label in taxonomy.labels}
    claim_ids = {claim.claim_id for claim in claims.claims}

    for label in taxonomy.labels:
        unknown_claims = set(label.allowed_claim_ids).difference(claim_ids)
        if unknown_claims:
            raise ValueError(
                f"标签 {label.code} 引用了未知承诺: {sorted(unknown_claims)}"
            )

    for claim in claims.claims:
        unknown_labels = set(claim.allowed_label_codes).difference(label_codes)
        if unknown_labels:
            raise ValueError(
                f"承诺 {claim.claim_id} 引用了未知标签: {sorted(unknown_labels)}"
            )
