from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from pydantic import ValidationError

from return_semantics.schemas import TaxonomyConfig
from web_backend.classification_standards.candidate_validation import (
    StandardCandidateValidationMixin,
)
from web_backend.classification_standards.content_comparison import (
    StandardContentComparisonMixin,
)


class ClassificationStandardContentMixin(
    StandardCandidateValidationMixin, StandardContentComparisonMixin
):
    def _snapshot_from_content(
        self, source: dict[str, Any], content: dict[str, Any]
    ) -> dict[str, Any]:
        snapshot = deepcopy(source)
        existing_labels = {
            str(label["code"]): label for label in source["taxonomy"]["labels"]
        }
        snapshot["name"] = str(content["name"]).strip()
        snapshot["variants"] = self._content_variants(content)
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
        self._apply_review_role(snapshot, content.get("review_role"))
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
            content.get("validation_rules", taxonomy.get("validation_rules", {}))
        )
        self._apply_content_labels(taxonomy, content, existing_labels)
        self._update_derived_groups(taxonomy)
        return snapshot

    @classmethod
    def _apply_review_role(
        cls,
        snapshot: dict[str, Any],
        review_role: str | None,
    ) -> None:
        if review_role is None or review_role == snapshot["model_policy"].get(
            "review_role"
        ):
            return
        snapshot["model_policy"]["review_role"] = review_role
        snapshot["model_policy"]["version"] = cls._model_policy_version(snapshot)

    @staticmethod
    def _model_policy_version(snapshot: dict[str, Any]) -> str:
        policy = snapshot["model_policy"]
        identity = json.dumps(
            {
                "first_pass_role": policy["first_pass_role"],
                "review_role": policy.get("review_role"),
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
        return f"{snapshot['standard_key']}-model-policy-{digest}"

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
            "review_role": snapshot.get("model_policy", {}).get("review_role"),
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

    @staticmethod
    def _content_variants(content: dict[str, Any]) -> list[dict[str, Any]]:
        return [
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

    @staticmethod
    def _apply_content_labels(
        taxonomy: dict[str, Any],
        content: dict[str, Any],
        existing_labels: dict[str, Any],
    ) -> None:
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

    @staticmethod
    def _update_derived_groups(taxonomy: dict[str, Any]) -> None:
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
