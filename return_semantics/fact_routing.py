from __future__ import annotations

from collections.abc import Iterator

from return_semantics.schemas import ExtractedFact, LabelDefinition, TaxonomyConfig
from return_semantics.taxonomy_hierarchy import label_path, label_path_codes


def _branch_catalog(taxonomy: TaxonomyConfig) -> dict[str, dict]:
    branches: dict[str, dict] = {}
    for label in taxonomy.labels:
        path = label_path(taxonomy, label.code)
        code = (
            label_path_codes(taxonomy, label.code)[0]
            if taxonomy.structure_version == 2
            else label.group or label.code
        )
        branch = branches.setdefault(
            code, {"name": path[0], "labels": [], "topics": []}
        )
        branch["labels"].append(label.code)
        if label.name not in branch["topics"]:
            branch["topics"].append(label.name)
    return branches


def _compatible_fallback_codes(
    fact: ExtractedFact, fallback_labels: list[LabelDefinition]
) -> Iterator[str]:
    return (
        label.code
        for label in fallback_labels
        if fact.sentiment in label.allowed_sentiments
    )


def _allowed_labels_by_fact(
    facts: list[ExtractedFact], taxonomy: TaxonomyConfig
) -> dict[str, list[str]]:
    branches = _branch_catalog(taxonomy)
    allowed: dict[str, list[str]] = {}
    labels_by_code = {label.code: label for label in taxonomy.labels}
    fallback_labels = [
        labels_by_code[code] for code in taxonomy.validation_rules.fallback_label_codes
    ]
    for fact in facts:
        if any((code not in branches for code in fact.candidate_branch_codes)):
            raise ValueError("事实路由包含未知分类分支")
        allowed[fact.fact_id] = list(
            dict.fromkeys(
                (
                    code
                    for branch in fact.candidate_branch_codes
                    for code in branches[branch]["labels"]
                )
            )
        )
        if fact.product_ref.startswith("OTHER:"):
            allowed[fact.fact_id] = []
        else:
            allowed[fact.fact_id] = list(
                dict.fromkeys(
                    [
                        *allowed[fact.fact_id],
                        *_compatible_fallback_codes(fact, fallback_labels),
                    ]
                )
            )
    return allowed


def _normalize_fact_branch_codes(
    facts: list[ExtractedFact], taxonomy: TaxonomyConfig
) -> list[ExtractedFact]:
    """将唯一对应的分支名称或标签主题归一为分支编码。"""
    branches = _branch_catalog(taxonomy)
    aliases: dict[str, set[str]] = {}
    for code, branch in branches.items():
        for alias in (branch["name"], *branch["topics"]):
            aliases.setdefault(alias, set()).add(code)

    normalized = []
    for fact in facts:
        codes = []
        for value in fact.candidate_branch_codes:
            matches = aliases.get(value, set())
            code = next(iter(matches)) if len(matches) == 1 else value
            if code not in codes:
                codes.append(code)
        normalized.append(fact.model_copy(update={"candidate_branch_codes": codes}))
    return normalized
