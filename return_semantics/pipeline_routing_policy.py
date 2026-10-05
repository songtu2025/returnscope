from __future__ import annotations

import hashlib
import re

from return_semantics.schemas import (
    ClaimRelation,
    ProcessingStatus,
    ValidatedClassification,
)

_SEMANTIC_RISK_PATTERNS = (
    re.compile(r"[|;/?&,]"),
    re.compile(r"[.!]\s+\S"),
    re.compile(
        r"\b(?:and|or|but|however|although|though|because|if|unless|"
        r"while|except|yet|also)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:no|not|never|neither|nor|without|cannot|can't|don't|"
        r"doesn't|didn't|isn't|wasn't|weren't|won't|wouldn't|"
        r"couldn't|shouldn't|barely|hardly)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:need|needed|want|wanted|expected|expecting|wish|"
        r"should|would)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:than|unlike|compared|previous|another|other|different|"
        r"maybe|perhaps|seems?|unsure|uncertain)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:size|sized|sizing|order|ordered)\s+(?:up|down)\b",
        re.IGNORECASE,
    ),
)


def has_input_semantic_risk(comment: str) -> bool:
    return any(pattern.search(comment) for pattern in _SEMANTIC_RISK_PATTERNS)


def can_accept_cheap_result(result: ValidatedClassification) -> bool:
    if result.status != ProcessingStatus.AUTO_APPROVED:
        return False
    if result.unknown_semantics:
        return False
    if len(result.semantic_units) != 1:
        return False
    if len(result.problem_label_codes) != 1:
        return False
    unit = result.semantic_units[0]
    return (
        not unit.implicit
        and unit.claim_relation == ClaimRelation.NONE
        and unit.claim_id is None
    )


def should_audit_cheap_model(comment: str, percent: int) -> bool:
    if percent <= 0:
        return False
    if percent >= 100:
        return True
    digest = hashlib.sha256(comment.lower().encode("utf-8")).digest()
    bucket = int.from_bytes(digest[:4], "big") % 10_000
    return bucket < percent * 100
