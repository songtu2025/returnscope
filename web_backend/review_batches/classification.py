from __future__ import annotations

from typing import Any

from web_backend.review_batches.editing_context import _ReviewEditingContext
from web_backend.review_batches.result_indexes import project_review_labels


class _ReviewClassification(_ReviewEditingContext):
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
