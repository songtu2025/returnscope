from __future__ import annotations

from copy import deepcopy
from typing import Any, cast

from return_semantics.semantic_review import (
    build_semantic_review_view,
)
from web_backend.review_batches.editing_context import _ReviewEditingContext
from web_backend.review_label_corrections import (
    apply_semantic_review_changes,
    project_review_labels,
)


class _ReviewClassification(_ReviewEditingContext):
    def _resolve_batch_classification(
        self,
        classification: dict[str, Any],
        comment: str,
        result_version_id: str,
        label_code: str | None,
    ) -> dict[str, Any]:
        pending = [
            item
            for field in ("human_semantic_reviews", "human_added_semantic_items")
            for item in classification.get(field, [])
            if not item.get("applied")
        ]
        if not pending:
            return self._apply_resolution(
                classification, comment, label_code, result_version_id
            )
        classification = self._apply_untargeted_label(
            classification, comment, label_code, result_version_id
        )
        taxonomy = self.standard_service.taxonomy_config_for_result_version(
            result_version_id
        )
        projected = apply_semantic_review_changes(classification, taxonomy, comment)
        self._validate_reviewed_classification(projected)
        # 草稿保留原项身份，发布时再应用处置，避免编辑记录和正式结果重复投影。
        return {**classification, "status": "MANUAL_RESOLVED", "review_reasons": []}

    def _apply_untargeted_label(
        self,
        classification: dict[str, Any],
        comment: str,
        label_code: str | None,
        result_version_id: str,
    ) -> dict[str, Any]:
        units = classification.get("semantic_units", [])
        if not label_code or not units:
            return classification
        view = build_semantic_review_view({"semantic_units": units[:1]}, "")
        first_ids = {
            str(item["item_id"])
            for item in cast(list[dict[str, Any]], view["semantic_items"])
        }
        first_ids.update(f"fact:{fact_id}" for fact_id in units[0].get("fact_ids", []))
        # 明确的逐项处置优先；整条选择继续作用于未被调整的首项。
        if any(
            item["semantic_item_id"] in first_ids and not item.get("applied")
            for item in classification.get("human_semantic_reviews", [])
        ):
            return classification
        updated = self._apply_resolution(
            classification, comment, label_code, result_version_id
        )
        updated["unknown_semantics"] = classification.get("unknown_semantics", [])
        return updated

    @staticmethod
    def _apply_human_review_details(
        classification: dict[str, Any],
        *,
        actor_id: str,
        assessed_at: str,
        review_assessment: dict[str, str | None] | None,
        semantic_item_reviews: list[dict[str, Any]] | None,
        added_semantic_items: list[dict[str, Any]] | None,
        coverage_status: str | None,
    ) -> dict[str, Any]:
        assessment = {
            key: value
            for key, value in (review_assessment or {}).items()
            if value is not None
        }
        if not any(
            (
                assessment,
                semantic_item_reviews is not None,
                added_semantic_items is not None,
                coverage_status is not None,
            )
        ):
            return classification

        result = deepcopy(classification)
        result.pop("semantic_review", None)
        reviewer = {"assessed_by": actor_id, "assessed_at": assessed_at}
        if assessment:
            result["human_review_assessment"] = {**assessment, **reviewer}
        if semantic_item_reviews is not None:
            result["human_semantic_reviews"] = [
                {**item, **reviewer} for item in semantic_item_reviews
            ]
        if added_semantic_items is not None:
            result["human_added_semantic_items"] = [
                {**item, **reviewer} for item in added_semantic_items
            ]
        if coverage_status is not None:
            result["coverage_review"] = {"status": coverage_status, **reviewer}
        return result

    def _apply_resolution(
        self,
        classification: dict[str, Any],
        comment: str,
        label_code: str | None,
        result_version_id: str | None = None,
    ) -> dict[str, Any]:
        taxonomy = (
            self.standard_service.taxonomy_config_for_result_version(result_version_id)
            if result_version_id
            else self.standard_service.combined_taxonomy()
        )
        label_codes = {label.code for label in taxonomy.labels}
        selected = (label_code or "").strip()
        updated = dict(classification)
        if selected:
            if selected not in label_codes:
                raise ValueError("选择的语义标签不存在")
            units = [dict(item) for item in updated.get("semantic_units", [])]
            if units:
                previous_label = str(units[0].get("label_code", ""))
                units[0]["label_code"] = selected
            else:
                previous_label = ""
                units = [
                    {
                        "subject": "PRODUCT",
                        "label_code": selected,
                        "opinion": comment,
                        "sentiment": "NEGATIVE",
                        "assertion": "AFFIRMED",
                        "part": "UNSPECIFIED",
                        "evidence": comment,
                        "implicit": False,
                        "claim_relation": "NONE",
                        "claim_id": None,
                    }
                ]
            updated["semantic_units"] = units
            updated["unknown_semantics"] = []
            problem_codes, positive_codes, negative_codes = self._project_review_labels(
                units,
                list(updated.get("problem_label_codes", [])),
                previous_label,
                selected,
            )
            updated["problem_label_codes"] = problem_codes
            updated["positive_label_codes"] = positive_codes
            updated["primary_label_codes"] = [selected]
            summary = dict(updated.get("comment_summary", {}))
            summary["positive_label_codes"] = positive_codes
            summary["negative_label_codes"] = negative_codes
            updated["comment_summary"] = summary
        if not updated.get("semantic_units") and updated.get("unknown_semantics"):
            raise ValueError("未知语义必须选择一个标签后才能完成复核")
        updated["status"] = "MANUAL_RESOLVED"
        updated["review_reasons"] = []
        self._validate_reviewed_classification(updated)
        return updated

    _project_review_labels = staticmethod(project_review_labels)
