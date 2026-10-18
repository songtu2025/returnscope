from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor

import pytest

from return_semantics import semantic_review_coverage as coverage


@pytest.mark.parametrize(
    "text,evidence",
    [
        ("", []),
        ("A+B [x]. A+B [x]", ["A+B [x]", " A+B [x] "]),
        ("Hello\t\nWORLD! Hello world", ["hello world"]),
        ("İ ı ſ K 中文😀", ["i", "s", "k", "中文😀"]),
        ("首行\n第二行. missing", ["首行 第二行", " "]),
        ("aaaa", ["aa", "aaa", "不存在"]),
    ],
)
def test_cached_matching_keeps_original_mask(text, evidence):
    expected = [False] * len(text)
    for span in dict.fromkeys(item.strip() for item in evidence if item.strip()):
        pattern = r"\s+".join(re.escape(word) for word in re.split(r"\s+", span))
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            expected[match.start() : match.end()] = [True] * (
                match.end() - match.start()
            )
    assert coverage._covered_source_mask(text, evidence) == expected
    with coverage.reuse_evidence_patterns():
        assert coverage._covered_source_mask(text, evidence) == expected
        assert coverage._covered_source_mask(text, evidence) == expected


def test_compiler_is_bounded_and_cleared_after_nested_failure():
    assert coverage._pattern_compiler.get() is None
    with coverage.reuse_evidence_patterns():
        outer = coverage._pattern_compiler.get()
        assert outer("a", 0) is not outer("a", re.IGNORECASE)
        assert outer("a", 0) is outer("a", 0)
        with pytest.raises(ValueError), coverage.reuse_evidence_patterns():
            inner = coverage._pattern_compiler.get()
            inner("only-inner", 0)
            raise ValueError("合成异常")
        assert inner.cache_info().currsize == 0
        assert coverage._pattern_compiler.get() is outer
        capacity = outer.cache_info().maxsize
        for index in range(capacity + 1):
            outer(str(index), 0)
        assert outer.cache_info().currsize == capacity
    assert outer.cache_info().currsize == 0
    assert coverage._pattern_compiler.get() is None


def test_export_context_does_not_leak_to_another_thread():
    with coverage.reuse_evidence_patterns(), ThreadPoolExecutor(1) as pool:
        assert pool.submit(coverage._pattern_compiler.get).result() is None


def test_changed_text_is_rematched_and_new_export_has_no_old_cache():
    with coverage.reuse_evidence_patterns():
        compiler = coverage._pattern_compiler.get()
        assert coverage._unexplained_fragments("known. old", ["known"]) == ["old"]
        assert coverage._unexplained_fragments("known. new", ["known"]) == ["new"]
        assert compiler.cache_info().hits == 1
    with coverage.reuse_evidence_patterns():
        assert coverage._pattern_compiler.get().cache_info().currsize == 0
