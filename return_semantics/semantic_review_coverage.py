from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache

from return_semantics.semantic_review_items import (
    ANALYSIS_FAILURE,
    MAPPED,
    NO_TAG_NEEDED,
    TAXONOMY_GAP,
    TRUE_AMBIGUITY,
    _text,
)

_pattern_compiler: ContextVar[Callable[[str, int], re.Pattern[str]] | None] = (
    ContextVar("evidence_pattern_compiler", default=None)
)
_FRAGMENT_BOUNDARY = re.compile(r"[\x00\r\n.!?;,:。！？；，：]+")
_FRAGMENT_CONNECTORS = frozenset(
    "and but or also that however then therefore consequently so while "
    "because since with y o pero también aunque".split()
)
_HTML_FRAGMENT = re.compile(r"(?:(?:<br\s*/?>|&(?:amp|nbsp);?)\s*)+", re.IGNORECASE)


def _compile_evidence_pattern(span: str, flags: int) -> re.Pattern[str]:
    """保留原有证据转义、变长空白和大小写匹配规则。"""
    words = re.split(r"\s+", span)
    pattern = r"\s+".join(re.escape(word) for word in words)
    return re.compile(pattern, flags=flags)


@contextmanager
def reuse_evidence_patterns() -> Iterator[None]:
    """仅在当前导出准备阶段复用编译结果，离开即释放证据文本。"""
    compiler = lru_cache(maxsize=8192)(_compile_evidence_pattern)
    token = _pattern_compiler.set(compiler)
    try:
        yield
    finally:
        _pattern_compiler.reset(token)
        compiler.cache_clear()


def _covered_source_mask(source_text: str, evidence: list[str]) -> list[bool]:
    covered = [False] * len(source_text)
    compile_pattern = _pattern_compiler.get() or _compile_evidence_pattern
    for span in dict.fromkeys(item.strip() for item in evidence if item.strip()):
        pattern = compile_pattern(span, re.IGNORECASE)
        for match in pattern.finditer(source_text):
            covered[match.start() : match.end()] = [True] * (
                match.end() - match.start()
            )
    return covered


def _unexplained_fragments(source_text: str, evidence: list[str]) -> list[str]:
    if not source_text.strip():
        return []
    covered = _covered_source_mask(source_text, evidence)
    # 已覆盖的字符是边界，不能把证据两侧的原文合成一个片段。
    remainder = "".join(
        "\x00" if is_covered else char
        for char, is_covered in zip(source_text, covered, strict=True)
    )
    fragments = []
    for value in _FRAGMENT_BOUNDARY.split(remainder):
        fragment = value.strip().strip("-_/|()[]{}'“”‘’").strip()
        if not any(character.isalnum() for character in fragment):
            continue
        if _HTML_FRAGMENT.fullmatch(fragment):
            continue
        if set(fragment.casefold().split()) <= _FRAGMENT_CONNECTORS:
            continue
        fragments.append(fragment)
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
