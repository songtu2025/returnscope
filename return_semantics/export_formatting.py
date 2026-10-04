from __future__ import annotations

from return_semantics.schemas import TaxonomyConfig, ValidatedClassification
from return_semantics.taxonomy_hierarchy import label_path, label_path_codes


def _format_labels(codes: list[str], label_names: dict[str, str]) -> str:
    return " | ".join(f"{code}:{label_names.get(code, '')}" for code in codes)


def _path_columns(taxonomy: TaxonomyConfig, code: str) -> dict[str, str]:
    path = label_path(taxonomy, code)
    return {
        "完整路径": " → ".join(path),
        "标签编码路径": " → ".join(label_path_codes(taxonomy, code)),
        **{f"第{index}级标签": name for index, name in enumerate(path, 1)},
    }


def _display_key(classification_key: str) -> str:
    return "".join(
        character if ord(character) >= 32 else " " for character in classification_key
    )


def _format_relations(result: ValidatedClassification) -> str:
    return " | ".join(
        f"{relation.relation_type.value}:"
        f"{','.join(relation.fact_ids)}:{relation.reason}"
        for relation in result.semantic_relations
    )
