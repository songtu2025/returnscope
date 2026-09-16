from __future__ import annotations

import json
from functools import lru_cache
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
    claims = adapt_claims_to_taxonomy(claims, taxonomy)
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


@lru_cache(maxsize=1)
def load_taxonomy_alignment() -> dict:
    path = Path(__file__).resolve().parents[1] / "config/taxonomy_alignment.json"
    return json.loads(path.read_text(encoding="utf-8"))


def aligned_label_group(
    standard_key: str,
    taxonomy_version: str,
    code: str,
    original_group: str,
) -> str:
    for source in load_taxonomy_alignment()["sources"]:
        if (source["standard_key"], source["taxonomy_version"]) == (
            standard_key,
            taxonomy_version,
        ):
            return source["labels"].get(code, {}).get("group", original_group)
    return original_group


def adapt_claims_to_taxonomy(
    claims: ListingClaimsConfig,
    taxonomy: TaxonomyConfig,
) -> ListingClaimsConfig:
    if (
        taxonomy.structure_version == 2
        or not taxonomy.validation_rules.allowed_groups
        or not claims.claims
    ):
        return claims
    # 只转换已登记的编码映射；承诺文本、来源和原版本保持不变。
    targets = {label.code: label for label in taxonomy.labels}
    aliases: dict[str, set[str]] = {}
    for source in load_taxonomy_alignment()["sources"]:
        for code, mapping in source["labels"].items():
            target = mapping.get("target_code")
            if target in targets:
                aliases.setdefault(code, set()).add(target)
    return claims.model_copy(
        update={
            "claims": [
                claim.model_copy(
                    update={
                        "allowed_label_codes": sorted(
                            {
                                target
                                for code in claim.allowed_label_codes
                                for target in (
                                    {code}
                                    if code in targets
                                    else aliases.get(code, set())
                                )
                                if claim.claim_id in targets[target].allowed_claim_ids
                            }
                        )
                    }
                )
                for claim in claims.claims
            ]
        }
    )
