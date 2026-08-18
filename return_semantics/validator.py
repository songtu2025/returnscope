from __future__ import annotations

from collections.abc import Iterable

from return_semantics.schemas import (
    AssertionCode,
    ClaimRelation,
    ListingClaimsConfig,
    ModelClassification,
    ProcessingStatus,
    SentimentCode,
    TaxonomyConfig,
    ValidatedClassification,
)
from return_semantics.semantic_guardrails import normalize_semantic_unit

OPPOSITE_REASON_LABELS = {
    "APPAREL_TOO_SMALL": {
        "FIT_TOO_LARGE",
        "FIT_TOO_LONG",
        "FIT_TOO_LOOSE_WIDE",
    },
    "APPAREL_TOO_LARGE": {
        "FIT_TOO_SMALL",
        "FIT_TOO_SHORT",
        "FIT_TOO_TIGHT_NARROW",
    },
}
CONFLICTING_LABELS = [
    {"FIT_TOO_SMALL", "FIT_TOO_LARGE"},
    {"FIT_TOO_SHORT", "FIT_TOO_LONG"},
    {"FIT_TOO_TIGHT_NARROW", "FIT_TOO_LOOSE_WIDE"},
]


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))


def validate_classification(
    classification_key: str,
    comment: str,
    reason: str,
    model_result: ModelClassification,
    taxonomy: TaxonomyConfig,
    claims: ListingClaimsConfig,
    model_name: str,
    prompt_version: str,
) -> ValidatedClassification:
    labels = {label.code: label for label in taxonomy.labels}
    allowed_parts = set(taxonomy.allowed_parts)
    claim_map = {claim.claim_id: claim for claim in claims.claims}
    hard_reasons: list[str] = []
    soft_reasons: list[str] = list(model_result.review_reasons)
    unknown_semantics = list(model_result.unknown_semantics)
    guardrail_removed_codes: set[str] = set()

    valid_units = []
    for unit in model_result.semantic_units:
        label = labels.get(unit.label_code)
        if label is None:
            hard_reasons.append(f"未知标签: {unit.label_code}")
            continue
        if unit.evidence not in comment:
            hard_reasons.append(f"证据不在原评论中: {unit.label_code}")
            continue
        if unit.sentiment not in label.allowed_sentiments:
            hard_reasons.append(f"标签情感方向无效: {unit.label_code}")
            continue
        if unit.part not in allowed_parts:
            hard_reasons.append(f"部位不适用于当前品类: {unit.part.value}")
            continue
        if unit.assertion != AssertionCode.AFFIRMED:
            soft_reasons.append(f"语义并非已确认事实: {unit.label_code}")
            continue

        original_label_code = unit.label_code
        unit, unknown = normalize_semantic_unit(unit)
        if unknown is not None:
            unknown_semantics.append(unknown)
            guardrail_removed_codes.add(original_label_code)
            continue
        if unit is None:
            continue

        if unit.claim_relation == ClaimRelation.NONE:
            if unit.claim_id is not None:
                hard_reasons.append(f"无承诺关系却提供了承诺编号: {unit.label_code}")
                continue
        else:
            claim = claim_map.get(unit.claim_id or "")
            if claim is None:
                hard_reasons.append(f"承诺编号无效: {unit.claim_id}")
                continue
            if unit.label_code not in claim.allowed_label_codes:
                hard_reasons.append(
                    f"标签与承诺不匹配: {unit.label_code}, {unit.claim_id}"
                )
                continue
            if unit.claim_id not in label.allowed_claim_ids:
                hard_reasons.append(
                    f"标签未允许该承诺: {unit.label_code}, {unit.claim_id}"
                )
                continue
            if (
                unit.sentiment == SentimentCode.POSITIVE
                and unit.claim_relation == ClaimRelation.CONTRADICTS
            ):
                hard_reasons.append(f"正面语义不能反驳承诺: {unit.label_code}")
                continue
            if (
                unit.sentiment == SentimentCode.NEGATIVE
                and unit.claim_relation == ClaimRelation.SUPPORTS
            ):
                hard_reasons.append(f"负面语义不能支持承诺: {unit.label_code}")
                continue

        if unit.implicit:
            soft_reasons.append(f"存在隐含语义: {unit.label_code}")
        valid_units.append(unit)

    for unknown in unknown_semantics:
        if unknown.evidence not in comment:
            hard_reasons.append("未知语义证据不在原评论中")

    problem_codes = _unique(
        unit.label_code
        for unit in valid_units
        if unit.sentiment == SentimentCode.NEGATIVE
        or (
            unit.sentiment == SentimentCode.NEUTRAL
            and labels[unit.label_code].group == "其他原因"
        )
    )
    positive_codes = _unique(
        unit.label_code
        for unit in valid_units
        if unit.sentiment == SentimentCode.POSITIVE
    )
    primary_codes = _unique(model_result.primary_label_codes)

    invalid_primary = set(primary_codes).difference(problem_codes)
    hard_invalid_primary = invalid_primary.difference(guardrail_removed_codes)
    if hard_invalid_primary:
        hard_reasons.append(f"主因不属于问题标签: {sorted(hard_invalid_primary)}")
    if invalid_primary:
        primary_codes = [code for code in primary_codes if code in problem_codes]
    if len(problem_codes) == 1 and not primary_codes:
        primary_codes = problem_codes.copy()
    if len(problem_codes) > 1 and not primary_codes:
        soft_reasons.append("多个问题但主因不明确")

    problem_set = set(problem_codes)
    if problem_set.intersection(OPPOSITE_REASON_LABELS.get(reason, set())):
        soft_reasons.append("Amazon 原因与评论方向冲突")
    for pair in CONFLICTING_LABELS:
        if pair.issubset(problem_set):
            soft_reasons.append(f"评论包含相反标签: {sorted(pair)}")

    if model_result.needs_review:
        soft_reasons.append("模型要求复核")
    if not valid_units and not unknown_semantics:
        soft_reasons.append("没有可确认的语义标签")
    if positive_codes and not problem_codes:
        soft_reasons.append("只有正面信息，无法确认退货原因")

    hard_reasons = _unique(hard_reasons)
    soft_reasons = _unique(soft_reasons)
    if hard_reasons:
        status = ProcessingStatus.MANUAL_REVIEW
    elif unknown_semantics:
        status = ProcessingStatus.UNKNOWN_SEMANTIC
    elif soft_reasons:
        status = ProcessingStatus.SECONDARY_REVIEW
    else:
        status = ProcessingStatus.AUTO_APPROVED

    return ValidatedClassification(
        classification_key=classification_key,
        semantic_units=valid_units,
        unknown_semantics=unknown_semantics,
        problem_label_codes=problem_codes,
        positive_label_codes=positive_codes,
        primary_label_codes=primary_codes,
        status=status,
        review_reasons=hard_reasons
        + soft_reasons
        + [f"未知语义: {item.reason}" for item in unknown_semantics],
        model_name=model_name,
        prompt_version=prompt_version,
        taxonomy_version=taxonomy.version,
    )
