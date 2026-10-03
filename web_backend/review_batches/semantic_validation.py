from __future__ import annotations

import re
from typing import Any, cast

from return_semantics.semantic_review import (
    build_semantic_review_view,
)
from web_backend.review_batches.editing_context import _ReviewEditingContext


class _ReviewSemanticValidation(_ReviewEditingContext):
    def _validate_semantic_review_details(
        self,
        *,
        result_version_id: str,
        classification: dict[str, Any],
        comment: str,
        semantic_item_reviews: list[dict[str, Any]] | None,
        added_semantic_items: list[dict[str, Any]] | None,
    ) -> None:
        taxonomy = self.standard_service.taxonomy_config_for_result_version(
            result_version_id
        )
        review_view = build_semantic_review_view(classification, comment, taxonomy)
        semantic_items = cast(
            list[dict[str, object]],
            review_view["semantic_items"],
        )
        unexplained_fragments = cast(
            list[str],
            review_view["unexplained_fragments"],
        )
        item_by_id = {
            str(item["item_id"]): item
            for item in semantic_items
            if isinstance(item, dict)
        }
        valid_item_ids = set(item_by_id)
        valid_item_ids.update(
            f"unexplained-{index}"
            for index, _fragment in enumerate(unexplained_fragments)
        )
        valid_label_codes = {label.code for label in taxonomy.labels}
        self._validate_semantic_item_reviews(
            semantic_item_reviews, item_by_id, valid_item_ids, valid_label_codes
        )
        self._validate_added_semantic_items(
            added_semantic_items, comment, valid_label_codes
        )

    @staticmethod
    def _validate_semantic_item_reviews(
        semantic_item_reviews: list[dict[str, Any]] | None,
        item_by_id: dict[str, dict[str, object]],
        valid_item_ids: set[str],
        valid_label_codes: set[str],
    ) -> None:
        for review in semantic_item_reviews or []:
            item_id = str(review.get("semantic_item_id") or "").strip()
            if item_id not in valid_item_ids:
                raise ValueError("选择的语义核验项不存在")
            item = item_by_id.get(item_id)
            if item is not None and item.get("business_review_required") is False:
                raise ValueError("系统诊断项不能由业务复核修改")
            action = str(review.get("action") or "").strip()
            if action not in {"change_label", "remove", "no_tag_needed"}:
                raise ValueError("语义核验处理动作不合法")
            if action == "change_label":
                label_code = str(review.get("label_code") or "").strip()
                if label_code not in valid_label_codes:
                    raise ValueError("选择的语义标签不存在")

    def _validate_added_semantic_items(
        self,
        added_semantic_items: list[dict[str, Any]] | None,
        comment: str,
        valid_label_codes: set[str],
    ) -> None:
        for added in added_semantic_items or []:
            label_code = str(added.get("label_code") or "").strip()
            if label_code not in valid_label_codes:
                raise ValueError("选择的语义标签不存在")
            evidence_text = str(added.get("evidence_text") or "").strip()
            if not self._evidence_exists_in_comment(evidence_text, comment):
                raise ValueError("人工补充项的证据必须来自当前用户反馈")

    @staticmethod
    def _evidence_exists_in_comment(evidence_text: str, comment: str) -> bool:
        words = evidence_text.split()
        if not words:
            return False
        pattern = r"\s+".join(re.escape(word) for word in words)
        return re.search(pattern, comment, flags=re.IGNORECASE) is not None
