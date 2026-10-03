from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from return_semantics.capabilities import CapabilityRegistry, CategoryCapability
from return_semantics.taxonomy import load_taxonomy_alignment
from web_backend.classification_standard_issues import label_field_issues
from web_backend.database import Database


class StandardCandidateValidationMixin:
    _candidate_change_validation: Callable[..., tuple[list[str], list[str]]]
    _capability_from_snapshot: Callable[[dict[str, Any]], CategoryCapability]
    database: Database

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

    @staticmethod
    def _validation_message(exc: Exception) -> str:
        if isinstance(exc, ValidationError) and exc.errors():
            error = exc.errors()[0]
            path = ".".join(str(value) for value in error["loc"])
            return f"{path} {error['msg']}".strip()
        return str(exc)
