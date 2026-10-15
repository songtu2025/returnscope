"""当前人工修正与历史记录共用的语义校验、标签投影。"""

from __future__ import annotations

from typing import Any

from return_semantics.schemas import ValidatedClassification

HUMAN_REVIEW_CLASSIFICATION_FIELDS = (
    "human_review_assessment",
    "human_semantic_reviews",
    "human_added_semantic_items",
    "coverage_review",
)


class ReviewPublicationContentMixin:
    @staticmethod
    def _validate_reviewed_classification(
        classification: dict[str, Any],
    ) -> tuple[ValidatedClassification, dict[str, Any]]:
        core = dict(classification)
        core.pop("semantic_review", None)
        human_fields = {
            field: core.pop(field)
            for field in HUMAN_REVIEW_CLASSIFICATION_FIELDS
            if field in core
        }
        for field in ("human_review_assessment", "coverage_review"):
            value = human_fields.get(field)
            if value is not None and not isinstance(value, dict):
                raise ValueError("人工复核评估数据格式无效")
        for field in ("human_semantic_reviews", "human_added_semantic_items"):
            value = human_fields.get(field)
            if value is not None and not isinstance(value, list):
                raise ValueError("人工语义核验数据格式无效")
        return ValidatedClassification.model_validate(core), human_fields

    @staticmethod
    def _derive_unit_labels(
        key: str, validated: ValidatedClassification, label_map: dict[str, Any]
    ) -> list[dict[str, Any]]:
        labels: list[dict[str, Any]] = []
        for kind, codes in (
            ("problem", validated.problem_label_codes),
            ("positive", validated.positive_label_codes),
            ("primary", validated.primary_label_codes),
        ):
            for code in sorted(set(codes)):
                label = label_map.get(code)
                labels.append(
                    {
                        "classification_key": key,
                        "label_kind": kind,
                        "label_code": code,
                        "label_name": label.name if label else None,
                        "label_group": label.group if label else None,
                    }
                )
        return labels
