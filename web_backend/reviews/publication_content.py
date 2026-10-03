"""校验人工复核分类并组装派生结果内容。"""

from __future__ import annotations

from typing import Any

from return_semantics.schemas import ValidatedClassification
from web_backend.common import json_value
from web_backend.review_contracts import _CompletedReviewChanges, _DerivedResultContent

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
    def _build_derived_result_content(
        connection: Any,
        batch: Any,
        changes: _CompletedReviewChanges,
        label_map: dict[str, Any],
    ) -> _DerivedResultContent:
        base_units = connection.execute(
            """
            SELECT * FROM classification_units
            WHERE result_version_id = ? ORDER BY classification_key
            """,
            (batch["base_result_version_id"],),
        ).fetchall()
        base_labels: dict[str, list[dict[str, Any]]] = {}
        for label_row in connection.execute(
            """
            SELECT classification_key, label_kind, label_code,
                   label_name, label_group
            FROM classification_unit_labels
            WHERE result_version_id = ?
            ORDER BY classification_key, label_kind, label_code
            """,
            (batch["base_result_version_id"],),
        ).fetchall():
            base_labels.setdefault(
                str(label_row["classification_key"]),
                [],
            ).append(dict(label_row))
        units: list[dict[str, Any]] = []
        labels: list[dict[str, Any]] = []
        unit_quality: dict[str, str] = {}
        for row in base_units:
            key = str(row["classification_key"])
            classification = changes.revisions.get(
                key,
                json_value(row["classification_json"], {}),
            )
            validated, human_fields = (
                ReviewPublicationContentMixin._validate_reviewed_classification(
                    classification
                )
            )
            serialized = validated.model_dump(mode="json")
            serialized.update(human_fields)
            quality_status = (
                "excluded"
                if key in changes.excluded_keys
                else "ready"
                if key in changes.revisions
                else str(row["quality_status"])
            )
            unit_quality[key] = quality_status
            units.append(
                {
                    "classification_key": key,
                    "reason": row["reason"],
                    "comment": row["comment"],
                    "classification": serialized,
                    "problem_labels": list(validated.problem_label_codes),
                    "processing_status": validated.status.value,
                    "quality_status": quality_status,
                    "record_count": int(row["record_count"]),
                    "model_name": validated.model_name,
                    "prompt_version": validated.prompt_version,
                    "taxonomy_version": validated.taxonomy_version,
                }
            )
            if key in changes.excluded_keys:
                continue
            if key not in changes.revisions:
                labels.extend(base_labels.get(key, []))
                continue
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
        base_records = connection.execute(
            """
            SELECT * FROM classification_result_records
            WHERE result_version_id = ? ORDER BY source_row, id
            """,
            (batch["base_result_version_id"],),
        ).fetchall()
        records = [
            {
                "classification_key": str(row["classification_key"]),
                "source_row": int(row["source_row"]),
                "source_origin_id": row["source_origin_id"],
                "return_date": row["return_date"],
                "order_id": row["order_id"],
                "store_site": row["store_site"],
                "listing": row["listing"],
                "product_name": row["product_name"],
                "source_sku": row["source_sku"],
                "matched_msku": row["matched_msku"],
                "product_sku": row["product_sku"],
                "asin": row["asin"],
                "fnsku": row["fnsku"],
                "category_a": row["category_a"],
                "category_b": row["category_b"],
                "reason": row["reason"],
                "comment": row["comment"],
                "product_match_status": row["product_match_status"],
                "quality_status": unit_quality[str(row["classification_key"])],
            }
            for row in base_records
        ]
        return _DerivedResultContent(units=units, labels=labels, records=records)
