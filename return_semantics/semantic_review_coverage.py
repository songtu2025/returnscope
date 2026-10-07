from __future__ import annotations

import re
from collections import Counter

from return_semantics.semantic_review_items import (
    ANALYSIS_FAILURE,
    MAPPED,
    NO_TAG_NEEDED,
    TAXONOMY_GAP,
    TRUE_AMBIGUITY,
    _text,
)


def _covered_source_mask(source_text: str, evidence: list[str]) -> list[bool]:
    covered = [False] * len(source_text)
    for span in dict.fromkeys(item.strip() for item in evidence if item.strip()):
        words = re.split(r"\s+", span)
        pattern = r"\s+".join(re.escape(word) for word in words)
        for match in re.finditer(pattern, source_text, flags=re.IGNORECASE):
            covered[match.start() : match.end()] = [True] * (
                match.end() - match.start()
            )
    return covered


def _unexplained_fragments(source_text: str, evidence: list[str]) -> list[str]:
    if not source_text.strip():
        return []
    covered = _covered_source_mask(source_text, evidence)
    remainder = "".join(
        " " if is_covered else char
        for char, is_covered in zip(source_text, covered, strict=True)
    )
    fragments = []
    for fragment in re.split(r"[\r\n.!?;,:。！？；，：]+", remainder):
        normalized = " ".join(fragment.split()).strip("-_/|()[]{}'“”‘’")
        if normalized and any(character.isalnum() for character in normalized):
            fragments.append(normalized)
    return fragments


def _coverage_evidence(items: list[dict[str, object]]) -> list[str]:
    evidence: list[str] = []
    for item in items:
        raw_evidence = item.pop("_coverage_evidence", [])
        if isinstance(raw_evidence, list):
            evidence.extend(str(value) for value in raw_evidence if str(value))
    return evidence


def _coverage_summary(
    items: list[dict[str, object]], unexplained: list[str]
) -> dict[str, object]:
    counts = Counter(_text(item["disposition"]) for item in items)
    return {
        "total": len(items),
        "mapped": counts[MAPPED],
        "no_tag_needed": counts[NO_TAG_NEEDED],
        "taxonomy_gap": counts[TAXONOMY_GAP],
        "true_ambiguity": counts[TRUE_AMBIGUITY],
        "analysis_failure": counts[ANALYSIS_FAILURE],
        "unexplained_fragment_count": len(unexplained),
        "complete": not unexplained
        and not any(
            counts[disposition]
            for disposition in (TAXONOMY_GAP, TRUE_AMBIGUITY, ANALYSIS_FAILURE)
        ),
    }
