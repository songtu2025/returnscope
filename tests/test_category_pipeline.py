from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from return_semantics.capabilities import (
    CapabilityRegistry,
    load_capability_registry,
    resolve_model_policy,
)
from return_semantics.category_pipeline import classify_category_segments
from return_semantics.data import ReturnDataset
from return_semantics.pipeline import PipelineRun
from return_semantics.schemas import (
    ListingClaimsConfig,
    ProcessingStatus,
    ValidatedClassification,
)
from return_semantics.task_plan import build_category_execution_plan

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def registry():
    return load_capability_registry(
        PROJECT_ROOT / "config" / "category_capabilities.json"
    )


@pytest.mark.parametrize(
    ("category_a", "category_b", "agent_family"),
    [
        ("遮阳帽", "儿童渔夫帽", "帽类智能体"),
        ("眼镜", "儿童眼镜", "眼镜智能体"),
        ("水鞋", "薄底水鞋", "鞋履智能体"),
        ("手套", "滑雪手套", "手套智能体"),
    ],
)
def test_four_agent_families_route_deterministically(
    registry,
    category_a: str,
    category_b: str,
    agent_family: str,
) -> None:
    capability = registry.resolve(category_a, category_b)

    assert capability is not None
    assert capability.agent_family == agent_family


def test_eyewear_variants_keep_confirmed_age_scope(registry) -> None:
    infant = registry.variant("眼镜", "婴儿眼镜")
    child = registry.variant("眼镜", "儿童眼镜")
    cycling = registry.variant("眼镜", "骑行眼镜")

    assert infant is not None and infant.attributes == {"age_range": "0-2岁"}
    assert child is not None and child.attributes == {"age_range": "3-8岁"}
    assert cycling is not None and cycling.attributes == {"audience": "主要成人"}
    assert registry.resolve("眼镜", "时尚眼镜") is None


def _dataset(rows: list[dict[str, str]]) -> ReturnDataset:
    unique_comments = pd.DataFrame(rows)
    records = unique_comments.loc[:, ["classification_key"]].copy()
    return ReturnDataset(
        records=records,
        unique_comments=unique_comments,
        mskus=frozenset(),
    )


def _validated(key: str, taxonomy_version: str) -> ValidatedClassification:
    return ValidatedClassification(
        classification_key=key,
        semantic_units=[],
        unknown_semantics=[],
        problem_label_codes=[],
        positive_label_codes=[],
        primary_label_codes=[],
        status=ProcessingStatus.AUTO_APPROVED,
        review_reasons=[],
        model_name="fake-model",
        prompt_version="test",
        taxonomy_version=taxonomy_version,
    )


def test_mixed_task_loads_each_family_taxonomy_and_excludes_unknown(
    monkeypatch,
    registry,
) -> None:
    dataset = _dataset(
        [
            {
                "classification_key": "hat",
                "reason": "reason",
                "comment_normalized": "hat comment",
                "category_a": "遮阳帽",
                "category_b": "儿童渔夫帽",
            },
            {
                "classification_key": "eye",
                "reason": "reason",
                "comment_normalized": "eye comment",
                "category_a": "眼镜",
                "category_b": "儿童眼镜",
            },
            {
                "classification_key": "shoe",
                "reason": "reason",
                "comment_normalized": "shoe comment",
                "category_a": "水鞋",
                "category_b": "薄底水鞋",
            },
            {
                "classification_key": "glove",
                "reason": "reason",
                "comment_normalized": "glove comment",
                "category_a": "手套",
                "category_b": "滑雪手套",
            },
            {
                "classification_key": "unknown",
                "reason": "reason",
                "comment_normalized": "unknown comment",
                "category_a": "瑜伽球",
                "category_b": "瑜伽球",
            },
        ]
    )
    loaded_taxonomies: list[str] = []

    def fake_classify_comments(**kwargs) -> PipelineRun:
        taxonomy = kwargs["taxonomy"]
        selected = kwargs["unique_comments"]
        loaded_taxonomies.append(taxonomy.version)
        results = {
            row.classification_key: _validated(
                row.classification_key,
                taxonomy.version,
            )
            for row in selected.itertuples(index=False)
        }
        return PipelineRun(
            classifications=results,
            usage={"input_tokens": len(selected)},
            usage_by_model={"fake-model": {"input_tokens": len(selected)}},
            cache_hits=1,
            cache_hits_by_model={"fake-model": 1},
            model_calls=len(selected),
            model_calls_by_model={"fake-model": len(selected)},
            request_metrics={"requests": len(selected)},
            routing={"primary": len(selected)},
        )

    monkeypatch.setattr(
        "return_semantics.category_pipeline.classify_comments",
        fake_classify_comments,
    )

    result = classify_category_segments(
        dataset=dataset,
        registry=registry,
        client=object(),
        cache=object(),
    )

    assert loaded_taxonomies == [
        "headwear-2026-08-10-v1",
        "eyewear-2026-08-10-v1",
        "water-shoes-2026-08-05-v1",
        "gloves-2026-08-10-v1",
    ]
    assert result.pipeline.model_calls == 4
    assert result.pipeline.cache_hits == 4
    assert "unknown" not in result.pipeline.classifications
    assert len(result.segments) == 4
    assert {segment["agent_family"] for segment in result.segments} == {
        "帽类智能体",
        "眼镜智能体",
        "鞋履智能体",
        "手套智能体",
    }
    for segment in result.segments:
        assert "record_count" in segment
        assert "model_calls" in segment
        assert "cache_hits" in segment
        assert "status" in segment


def test_unknown_category_never_calls_model(monkeypatch, registry) -> None:
    dataset = _dataset(
        [
            {
                "classification_key": "unknown",
                "reason": "reason",
                "comment_normalized": "unknown comment",
                "category_a": "单筒",
                "category_b": "单筒",
            }
        ]
    )

    def fail_if_called(**_kwargs) -> PipelineRun:
        raise AssertionError("未知品类不应调用模型")

    monkeypatch.setattr(
        "return_semantics.category_pipeline.classify_comments",
        fail_if_called,
    )

    result = classify_category_segments(
        dataset=dataset,
        registry=registry,
        client=object(),
        cache=object(),
    )

    assert result.pipeline.model_calls == 0
    assert result.pipeline.classifications == {}
    assert result.segments == []


def test_existing_water_shoe_uses_original_taxonomy(registry) -> None:
    capability = registry.resolve("水鞋", "儿童溯溪水鞋")

    assert capability is not None
    taxonomy = registry.load_taxonomy(capability)
    assert capability.agent_family == "鞋履智能体"
    assert taxonomy.version == "water-shoes-2026-08-05-v1"
    assert taxonomy.labels[0].code == "FIT_TOO_LARGE"


def test_four_families_resolve_versioned_model_roles_and_fallback(registry) -> None:
    config = {
        "primary_model": "primary-model",
        "primary_effort": "medium",
        "cheap_model": "cheap-model",
        "cheap_effort": "low",
        "secondary_model": "review-model",
        "secondary_effort": "high",
    }
    expected_roles = {
        "headwear": ("cheap", "primary"),
        "eyewear": ("primary", "secondary"),
        "footwear": ("cheap", "secondary"),
        "gloves": ("primary", "primary"),
    }
    for capability in registry.capabilities:
        resolved = resolve_model_policy(capability, config)
        first_role, review_role = expected_roles[capability.key]
        assert resolved["version"] == capability.model_policy.version
        assert resolved["actual"]["first_pass"]["role"] == first_role
        assert resolved["actual"]["review"]["role"] == review_role

    fallback_config = {**config, "cheap_model": None, "secondary_model": None}
    footwear = next(item for item in registry.capabilities if item.key == "footwear")
    fallback = resolve_model_policy(footwear, fallback_config)
    assert fallback["actual"]["first_pass"]["model"] == "primary-model"
    assert fallback["actual"]["first_pass"]["fallback_from"] == "cheap"
    assert fallback["actual"]["review"]["model"] == "primary-model"
    assert fallback["actual"]["review"]["fallback_from"] == "secondary"


def test_policy_and_claims_versions_change_plan_hash(registry) -> None:
    dataset = _dataset(
        [
            {
                "classification_key": "shoe",
                "reason": "reason",
                "comment_normalized": "shoe comment",
                "category_a": "水鞋",
                "category_b": "薄底水鞋",
            }
        ]
    )
    config = {
        "primary_model": "primary-model",
        "primary_effort": "medium",
        "cheap_model": None,
        "cheap_effort": None,
        "secondary_model": None,
        "secondary_effort": None,
    }

    class FixedClaimsResolver:
        def __init__(self, version: str) -> None:
            self.version = version

        def resolve(self, *_args, **_kwargs) -> ListingClaimsConfig:
            return ListingClaimsConfig(version=self.version, claims=[])

    base = build_category_execution_plan(
        dataset,
        registry,
        model_config=config,
        claims_resolver=FixedClaimsResolver("claims-v1"),
    )
    changed_claims = build_category_execution_plan(
        dataset,
        registry,
        model_config=config,
        claims_resolver=FixedClaimsResolver("claims-v2"),
    )
    capabilities = tuple(
        replace(
            item,
            model_policy=replace(item.model_policy, version="policy-v2"),
        )
        if item.key == "footwear"
        else item
        for item in registry.capabilities
    )
    changed_registry = CapabilityRegistry(registry.version, capabilities)
    changed_policy = build_category_execution_plan(
        dataset,
        changed_registry,
        model_config=config,
        claims_resolver=FixedClaimsResolver("claims-v1"),
    )

    assert base.with_hash({})["plan_hash"] != changed_claims.with_hash({})["plan_hash"]
    assert base.with_hash({})["plan_hash"] != changed_policy.with_hash({})["plan_hash"]
