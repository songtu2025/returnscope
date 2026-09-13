from __future__ import annotations

import pytest

from return_semantics import prompt
from return_semantics.fact_pipeline import (
    coverage_audit_messages,
    extraction_messages,
)
from return_semantics.pipeline import build_cache_key


def _taxonomy_with_profile(taxonomy, profile: str):
    candidate = taxonomy.model_copy(deep=True)
    candidate.recognition_profile = profile
    return candidate


def test_extraction_prompt_preserves_atomic_and_statement_boundaries(taxonomy) -> None:
    candidate = _taxonomy_with_profile(taxonomy, "fact_v2")

    instruction = extraction_messages("review", candidate)[0]["content"]

    for boundary in (
        "可独立为真或为假为拆分标准",
        "不同属性、业务维度、对象、事件、条件结果或statement_type时分别抽取",
        "限制、让步和转折分句",
        "EXPERIENCE必须包含具体使用、试验、购买或服务事件",
        "EVALUATION是对属性、外观、触感或偏好的主观判断",
        "REQUEST不是schema中的statement_type",
        "处理请求不得伪装成EXPERIENCE、EVALUATION或PRODUCT_CLAIM",
        "评论者实际收到、观察或使用商品形成的事实必须与引用宣称分离",
        "reference_basis=LISTING",
    ):
        assert boundary in instruction


def test_coverage_prompt_rechecks_omitted_clauses_and_source_boundaries(
    taxonomy,
) -> None:
    candidate = _taxonomy_with_profile(taxonomy, "fact_v2")

    instruction = coverage_audit_messages("review", [], candidate)[0]["content"]

    for boundary in (
        "限制、让步和转折分句",
        "可独立为真或为假的命题必须补齐",
        "实际事件或结果才是EXPERIENCE",
        "主观属性判断是EVALUATION",
        "未经验证的是PRODUCT_CLAIM",
        "REQUEST不是schema类型",
        "listing引用与评论者实际收到、观察或使用的事实必须分离",
    ):
        assert boundary in instruction


@pytest.mark.parametrize(
    ("profile", "expected_version"),
    [
        ("legacy_v3", "category-semantic-v5"),
        ("keyword_free_v1", "category-keyword-free-v3"),
        ("semantic_v1", "category-semantic-evidence-v3"),
    ],
)
def test_non_fact_v2_prompt_versions_are_unchanged(
    taxonomy,
    profile: str,
    expected_version: str,
) -> None:
    candidate = _taxonomy_with_profile(taxonomy, profile)

    assert prompt.prompt_version(candidate) == expected_version


def test_fact_v2_v33_invalidates_fingerprint_and_cache_key(
    taxonomy,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = _taxonomy_with_profile(taxonomy, "fact_v2")
    current_version = prompt.prompt_version(candidate)
    current_fingerprint = prompt.recognition_fingerprint(candidate)
    with monkeypatch.context() as context:
        context.setattr(
            prompt,
            "prompt_version",
            lambda _taxonomy: "category-fact-v2-v32",
        )
        previous_fingerprint = prompt.recognition_fingerprint(candidate)

    cache_arguments = {
        "comment": "The listing says waterproof, but the gloves leaked.",
        "model_name": "test-model",
        "provider_name": "test-provider",
        "taxonomy_version": candidate.version,
        "claims_version": "test-claims",
    }
    previous_key = build_cache_key(
        effective_prompt_version="category-fact-v2-v32",
        recognition_key=previous_fingerprint,
        **cache_arguments,
    )
    current_key = build_cache_key(
        effective_prompt_version=current_version,
        recognition_key=current_fingerprint,
        **cache_arguments,
    )

    assert current_version == "category-fact-v2-v33"
    assert current_fingerprint != previous_fingerprint
    assert current_key != previous_key
