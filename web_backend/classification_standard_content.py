from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Callable

from pydantic import ValidationError

from return_semantics.capabilities import CapabilityRegistry, CategoryCapability
from return_semantics.schemas import TaxonomyConfig
from return_semantics.taxonomy import load_taxonomy_alignment
from web_backend.classification_standard_issues import label_field_issues
from web_backend.database import Database


class ClassificationStandardContentMixin:
    database: Database
    _capability_from_snapshot: Callable[[dict[str, Any]], CategoryCapability]
    combined_taxonomy: Callable[..., TaxonomyConfig]

    def _snapshot_from_content(
        self,
        source: dict[str, Any],
        content: dict[str, Any],
    ) -> dict[str, Any]:
        snapshot = deepcopy(source)
        existing_labels = {
            str(label["code"]): label for label in source["taxonomy"]["labels"]
        }
        snapshot["name"] = str(content["name"]).strip()
        snapshot["variants"] = [
            {
                "category_a": str(item["category_a"]).strip(),
                "category_b": str(item["category_b"]).strip(),
                "attributes": {
                    str(key).strip(): str(value).strip()
                    for key, value in item.get("attributes", {}).items()
                    if str(key).strip()
                },
            }
            for item in content["variants"]
        ]
        taxonomy = snapshot["taxonomy"]
        if content.get("structure_version", 1) == 2:
            taxonomy["structure_version"] = 2
            taxonomy["categories"] = deepcopy(content.get("categories", []))
        elif "structure_version" in taxonomy:
            taxonomy["structure_version"] = 1
            taxonomy.pop("categories", None)
        if content.get("import_sources") or "import_sources" in snapshot:
            snapshot["import_sources"] = deepcopy(content.get("import_sources", []))
        taxonomy["recognition_profile"] = content.get(
            "recognition_profile", taxonomy.get("recognition_profile", "legacy_v3")
        )
        taxonomy["product_context"] = str(content["product_context"]).strip()
        taxonomy["instructions"] = [
            str(value).strip()
            for value in content["instructions"]
            if str(value).strip()
        ]
        taxonomy["allowed_parts"] = [
            str(value).strip().upper()
            for value in content["allowed_parts"]
            if str(value).strip()
        ]
        taxonomy["validation_rules"] = deepcopy(
            content.get(
                "validation_rules",
                taxonomy.get("validation_rules", {}),
            )
        )
        taxonomy["labels"] = []
        for item in content["labels"]:
            code = str(item["code"]).strip()
            if taxonomy.get("structure_version", 1) == 1:
                code = code.upper()
            previous = existing_labels.get(code, {})
            taxonomy["labels"].append(
                {
                    "code": code,
                    "name": str(item["name"]).strip(),
                    "group": str(item.get("group", "")).strip(),
                    **(
                        {"parent_code": item.get("parent_code")}
                        if taxonomy.get("structure_version") == 2
                        else {}
                    ),
                    "description": str(item.get("description", "")).strip(),
                    "exclusions": list(
                        item.get("exclusions", previous.get("exclusions", []))
                    ),
                    "examples": deepcopy(
                        item.get("examples", previous.get("examples", []))
                    ),
                    "keywords": [
                        str(value).strip()
                        for value in item.get("keywords", previous.get("keywords", []))
                        if str(value).strip()
                    ],
                    "allowed_sentiments": [
                        str(value).strip().upper()
                        for value in item["allowed_sentiments"]
                    ],
                    "allowed_claim_ids": list(
                        item["allowed_claim_ids"]
                        if item.get("allowed_claim_ids") is not None
                        else previous.get("allowed_claim_ids", [])
                    ),
                }
            )
        if taxonomy.get("structure_version") == 2:
            # 草稿允许暂存未完成的树，合法结构才更新派生分组。
            try:
                parsed = TaxonomyConfig.model_validate(taxonomy)
            except ValidationError:
                pass
            else:
                for label, definition in zip(
                    taxonomy["labels"], parsed.labels, strict=True
                ):
                    label["group"] = definition.group
        return snapshot

    def _validate_candidate(
        self,
        standard_id: str,
        candidate: dict[str, Any],
        base: dict[str, Any],
    ) -> dict[str, Any]:
        blocking: list[str] = []
        warnings: list[str] = []
        taxonomy = candidate.get("taxonomy", {})
        issues = label_field_issues(taxonomy)
        blocking.extend(issue["message"] for issue in issues)
        blocking.extend(self._taxonomy_policy_blocking(taxonomy))
        blocking.extend(self._candidate_content_blocking(candidate, taxonomy))
        blocking.extend(self._registry_compatibility_blocking(standard_id, candidate))
        diff_blocking, diff_warnings = self._candidate_change_validation(
            base,
            candidate,
        )
        blocking.extend(diff_blocking)
        warnings.extend(diff_warnings)
        explained = {issue["message"] for issue in issues}
        issues.extend(
            {
                "kind": "invalid_rule"
                if "校验规则" in message
                else "invalid_structure",
                "message": message,
                "field": "validation_rules" if "校验规则" in message else None,
            }
            for message in dict.fromkeys(blocking)
            if message not in explained
        )
        return {
            "blocking": list(dict.fromkeys(blocking)),
            "warnings": warnings,
            "issues": issues,
        }

    @staticmethod
    def _taxonomy_policy_blocking(taxonomy: dict[str, Any]) -> list[str]:
        blocking: list[str] = []
        groups = taxonomy.get("validation_rules", {}).get("allowed_groups", [])
        if taxonomy.get("structure_version") == 2:
            nodes = [*taxonomy.get("categories", []), *taxonomy.get("labels", [])]
            sibling_names = [
                (node.get("parent_code"), node.get("name")) for node in nodes
            ]
            if len(sibling_names) != len(set(sibling_names)):
                blocking.append("同一父节点下的分类和标签不能重名")
        if (
            taxonomy.get("structure_version", 1) == 1
            and groups
            and groups != load_taxonomy_alignment()["groups"]
        ):
            blocking.append("统一标准必须使用规定的七个业务分组")
        return blocking

    @staticmethod
    def _candidate_content_blocking(
        candidate: dict[str, Any],
        taxonomy: dict[str, Any],
    ) -> list[str]:
        variants = candidate.get("variants", [])
        labels = taxonomy.get("labels", [])
        categories = [
            (str(item.get("category_a", "")), str(item.get("category_b", "")))
            for item in variants
        ]
        label_codes = [str(item.get("code", "")) for item in labels]
        blocking = [
            message
            for invalid, message in (
                (not str(candidate.get("name", "")).strip(), "标准名称不能为空"),
                (
                    not str(taxonomy.get("product_context", "")).strip(),
                    "适用商品说明不能为空",
                ),
                (not taxonomy.get("instructions"), "至少需要一条分类规则"),
                (not variants, "至少需要一个适用品类"),
                (not labels, "至少需要一个问题标签"),
            )
            if invalid
        ]
        blocking.extend(
            f"第 {index} 个品类的品类 A 和品类 B 不能为空"
            for index, (category_a, category_b) in enumerate(categories, start=1)
            if not category_a.strip() or not category_b.strip()
        )
        blocking.extend(
            message
            for invalid, message in (
                (
                    len(categories) != len(set(categories)),
                    "同一标准内存在重复品类映射",
                ),
                (
                    len(label_codes) != len(set(label_codes)),
                    "同一标准内存在重复标签编码",
                ),
                (
                    "UNSPECIFIED" not in taxonomy.get("allowed_parts", []),
                    "证据部位必须保留“未指定部位”",
                ),
            )
            if invalid
        )
        return blocking

    def _registry_compatibility_blocking(
        self,
        standard_id: str,
        candidate: dict[str, Any],
    ) -> list[str]:
        try:
            candidate_capability = self._capability_from_snapshot(candidate)
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            return [f"标准结构无效：{self._validation_message(exc)}"]
        try:
            capabilities = [candidate_capability]
            with self.database.connect() as connection:
                rows = connection.execute(
                    """
                    SELECT v.snapshot_json
                    FROM classification_standards s
                    JOIN classification_standard_versions v
                      ON v.id = s.current_version_id
                    WHERE s.status = 'active' AND s.id != ?
                    """,
                    (standard_id,),
                ).fetchall()
            capabilities.extend(
                self._capability_from_snapshot(json.loads(row["snapshot_json"]))
                for row in rows
            )
            registry = CapabilityRegistry(
                version="classification-standard-draft-validation",
                capabilities=tuple(capabilities),
            )
            registry.combined_taxonomy()
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            return [f"与已发布标准冲突：{self._validation_message(exc)}"]
        return []

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

    @staticmethod
    def _validation_message(exc: Exception) -> str:
        if isinstance(exc, ValidationError) and exc.errors():
            error = exc.errors()[0]
            path = ".".join(str(value) for value in error["loc"])
            return f"{path} {error['msg']}".strip()
        return str(exc)

    @staticmethod
    def _editable_content(snapshot: dict[str, Any]) -> dict[str, Any]:
        taxonomy = snapshot["taxonomy"]
        groups: dict[str, str] = {}
        if taxonomy.get("structure_version") == 2:
            try:
                parsed = TaxonomyConfig.model_validate(taxonomy)
            except ValidationError:
                groups = {}
            else:
                groups = {label.code: label.group for label in parsed.labels}
        return {
            "name": snapshot["name"],
            "structure_version": taxonomy.get("structure_version", 1),
            "categories": deepcopy(taxonomy.get("categories", [])),
            "import_sources": deepcopy(snapshot.get("import_sources", [])),
            "recognition_profile": taxonomy.get("recognition_profile", "legacy_v3"),
            "product_context": taxonomy["product_context"],
            "instructions": list(taxonomy["instructions"]),
            "allowed_parts": list(taxonomy["allowed_parts"]),
            "validation_rules": deepcopy(taxonomy.get("validation_rules", {})),
            "variants": deepcopy(snapshot["variants"]),
            "labels": [
                {
                    "code": label["code"],
                    "name": label["name"],
                    "group": groups.get(label["code"], label.get("group", "")),
                    "parent_code": label.get("parent_code"),
                    "description": label.get("description", ""),
                    "keywords": list(label.get("keywords", [])),
                    "exclusions": list(label.get("exclusions", [])),
                    "examples": deepcopy(label.get("examples", [])),
                    "allowed_sentiments": list(label["allowed_sentiments"]),
                    "allowed_claim_ids": list(label.get("allowed_claim_ids", [])),
                }
                for label in taxonomy["labels"]
            ],
        }

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
