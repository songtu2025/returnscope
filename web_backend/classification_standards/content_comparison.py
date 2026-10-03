from __future__ import annotations

from collections.abc import Callable
from typing import Any


class StandardContentComparisonMixin:
    _editable_content: Callable[..., dict[str, Any]]

    @classmethod
    def _candidate_change_validation(
        cls,
        base: dict[str, Any],
        candidate: dict[str, Any],
    ) -> tuple[list[str], list[str]]:
        blocking: list[str] = []
        warnings: list[str] = []
        diff = cls._diff_snapshots(base, candidate)
        if not diff["has_changes"]:
            blocking.append("草稿与当前已发布版本没有差异")
        if diff["semantic_label_changes"]:
            codes = "、".join(diff["semantic_label_changes"])
            blocking.append(
                f"已发布标签不能同码改义：{codes}；请停用旧标签并创建新编码"
            )
        if diff["removed_categories"]:
            warnings.append(
                f"将移除 {len(diff['removed_categories'])} 个适用品类，新任务不再匹配这些品类"
            )
        if diff["removed_labels"]:
            warnings.append(
                f"将停用 {len(diff['removed_labels'])} 个标签，历史结果仍保留原标签"
            )
        nonsemantic_changes = sorted(
            set(diff["modified_labels"]) - set(diff["semantic_label_changes"])
        )
        if nonsemantic_changes:
            warnings.append(
                f"补充了 {len(nonsemantic_changes)} 个已发布标签的搜索别名或判定说明"
            )
        return blocking, warnings

    @classmethod
    def _diff_snapshots(
        cls,
        base: dict[str, Any],
        candidate: dict[str, Any],
    ) -> dict[str, Any]:
        base_content = cls._editable_content(base)
        candidate_content = cls._editable_content(candidate)
        base_categories = {
            (item["category_a"], item["category_b"])
            for item in base_content["variants"]
        }
        candidate_categories = {
            (item["category_a"], item["category_b"])
            for item in candidate_content["variants"]
        }
        base_labels = {item["code"]: item for item in base_content["labels"]}
        candidate_labels = {item["code"]: item for item in candidate_content["labels"]}
        shared_codes = base_labels.keys() & candidate_labels.keys()
        return {
            "has_changes": base_content != candidate_content,
            "hierarchy_changed": (
                base_content["structure_version"]
                != candidate_content["structure_version"]
                or base_content["categories"] != candidate_content["categories"]
                or any(
                    base_labels[code]["parent_code"]
                    != candidate_labels[code]["parent_code"]
                    for code in shared_codes
                )
            ),
            "added_categories": sorted(candidate_categories - base_categories),
            "removed_categories": sorted(base_categories - candidate_categories),
            "added_labels": sorted(candidate_labels.keys() - base_labels.keys()),
            "removed_labels": sorted(base_labels.keys() - candidate_labels.keys()),
            "modified_labels": sorted(
                code
                for code in shared_codes
                if base_labels[code] != candidate_labels[code]
            ),
            "semantic_label_changes": sorted(
                code
                for code in shared_codes
                if any(
                    base_labels[code][field] != candidate_labels[code][field]
                    for field in (
                        ("description", "allowed_sentiments")
                        if candidate_content["structure_version"] == 2
                        else ("name", "group", "description", "allowed_sentiments")
                    )
                )
            ),
            "rules_changed": (
                base_content["recognition_profile"]
                != candidate_content["recognition_profile"]
                or base_content["review_role"] != candidate_content["review_role"]
                or base_content["instructions"] != candidate_content["instructions"]
                or base_content["allowed_parts"] != candidate_content["allowed_parts"]
                or base_content["validation_rules"]
                != candidate_content["validation_rules"]
            ),
            "description_changed": (
                base_content["name"] != candidate_content["name"]
                or base_content["product_context"]
                != candidate_content["product_context"]
            ),
        }
